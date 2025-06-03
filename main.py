import asyncio
import datetime
import os
from pathlib import Path
from typing import Annotated, overload

import aiohttp
import pytz
import recurring_ical_events
import yaml
from fastapi import FastAPI, Response
from icalendar import Calendar, Event
from pydantic import BaseModel, BeforeValidator, model_validator

VERSION = "0.5.0"

TZ = pytz.timezone(os.getenv("TZ", "Europe/Vienna"))
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", "config.yaml"))


app = FastAPI()


@overload
def ensure_list[T](value: list[T]) -> list[T]: ...
@overload
def ensure_list(value: None) -> None: ...
@overload
def ensure_list[T](value: T) -> list[T] | None: ...
def ensure_list[T](value: list[T] | T) -> list[T] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    return [value]


class MyBaseModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _alert_extra_field[T](cls, values: dict[str, T]) -> dict[str, T]:
        if extra_fields := values.keys() - cls.model_fields.keys() - {v.alias for v in cls.model_fields.values()}:
            msg = f"Unexpected field(s): {', '.join(extra_fields)}"
            raise ValueError(msg)

        return values


class SourceConfig(MyBaseModel):
    url: str
    include: list[str] = []
    event_name: str = "Busy"
    hide_if_overlapped: bool = False
    properties: dict[str, str] = {}


class CalendarConfig(MyBaseModel):
    sources: list[SourceConfig]
    key: Annotated[list[str] | None, BeforeValidator(ensure_list)] = None
    days_ahead: int = 28


class Config(MyBaseModel):
    calendars: dict[str, CalendarConfig]


CONFIG = Config.model_validate(yaml.safe_load(CONFIG_FILE.read_text()))


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": VERSION}


@app.get("/{cal}.ics")
async def get_ical(cal: str, key: str = "") -> Response:
    if cal not in CONFIG.calendars:
        return Response("Not Found", status_code=404)
    keys = CONFIG.calendars[cal].key
    if keys is not None and key not in keys:
        return Response("Unauthorized", status_code=401)
    c = await get_calendar(CONFIG.calendars[cal])
    return Response(c.to_ical(), media_type="text/calendar")


async def fetch_data(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as response:
        return await response.text()


async def get_calendar(config: CalendarConfig) -> Calendar:
    c = Calendar()
    c.add("REFRESH-INTERVAL;VALUE=DURATION", "PT15M")
    async with aiohttp.ClientSession() as session:
        icals = await asyncio.gather(*(fetch_data(session, source.url) for source in config.sources))

    events: list[tuple[Event, SourceConfig]] = []
    for ical, source in zip(icals, config.sources, strict=True):
        cal = Calendar().from_ical(ical)
        source_events: list[Event] = recurring_ical_events.of(cal).between(
            datetime.datetime.now(tz=TZ).date(),
            datetime.datetime.now(tz=TZ).date() + datetime.timedelta(days=config.days_ahead),
        )  # type: ignore
        events.extend((e, source) for e in source_events)

    for e, source in sorted(events, key=lambda e: e[0].start):
        if e.get("TRANSP", "OPAQUE") != "OPAQUE":
            continue

        if source.hide_if_overlapped:
            overlaps: list[Event] = recurring_ical_events.of(c).between(
                e.start,
                e.end,
            )  # type: ignore
            if any(e2.start <= e.start and e2.end >= e.end for e2 in overlaps):
                continue

        ne = Event()
        ne.start = e.start
        ne.end = e.end

        for k, v in source.properties.items():
            ne.add(k, v)

        for k in source.include:
            if k in e and k not in ne:
                ne.add(k, e[k])

        if "SUMMARY" not in ne:
            ne.add("SUMMARY", source.event_name)

        c.add_component(ne)
    return c


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, log_level="info", reload=True)  # noqa: S104
