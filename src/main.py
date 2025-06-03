import asyncio
import datetime
import os
from pathlib import Path
from typing import Annotated, overload

import aiohttp
import pytz
import recurring_ical_events
import yaml
from cachetools import TTLCache
from cachetools_async import cached
from fastapi import Cookie, FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from icalendar import Calendar, Event
from pydantic import AliasGenerator, BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

VERSION = "0.6.0"

TZ = pytz.timezone(os.getenv("TZ", "Europe/Vienna"))
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", Path(__file__).parent.parent / "config.yaml"))


app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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


class ConfigBaseModel(BaseModel):
    model_config = {"extra": "forbid"}

    def __hash__(self) -> int:
        return hash(self.model_dump_json)


class SourceConfig(ConfigBaseModel):
    url: str
    include: list[str] = []
    event_name: str = "Busy"
    hide_if_overlapped: bool = False
    tentative: bool = False
    properties: dict[str, str] = {}


class CalendarConfig(ConfigBaseModel):
    sources: list[SourceConfig]
    key: Annotated[list[str] | None, BeforeValidator(ensure_list)] = None
    days_ahead: int = 28


class Config(ConfigBaseModel):
    calendars: dict[str, CalendarConfig]


CONFIG = Config.model_validate(yaml.safe_load(CONFIG_FILE.read_text()))


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": VERSION}


class SessionCookie(BaseModel):
    saved_keys: dict[str, str] = {}


class FullCalendarEvent(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
        ),
    )

    start: datetime.datetime | datetime.date
    end: datetime.datetime | datetime.date
    title: str
    class_names: list[str]


def to_fullcalendar_event(e: Event) -> FullCalendarEvent:
    css_classes: list[str] = []

    if e.get("STATUS", "") == "TENTATIVE":
        css_classes.append("tentative")

    return FullCalendarEvent(
        start=e.start,
        end=e.end,
        title=e.get("SUMMARY", ""),
        class_names=css_classes,
    )


@app.get("/{cal}.json")
async def json_feed(
    cal: str,
    start: datetime.datetime,
    end: datetime.datetime,
    session: Annotated[str, Cookie()] = "{}",
) -> Response:
    if cal not in CONFIG.calendars:
        return Response("Not Found", status_code=404)
    keys = CONFIG.calendars[cal].key
    cookie = SessionCookie.model_validate_json(session)
    if keys is not None and cookie.saved_keys.get(cal, "") not in keys:
        return Response("Unauthorized", status_code=401)
    cookie = SessionCookie.model_validate_json(session)
    c = await get_calendar(CONFIG.calendars[cal])
    events: list[Event] = recurring_ical_events.of(c).between(start, end)  # type: ignore
    return JSONResponse(content=[to_fullcalendar_event(e).model_dump(mode="json", by_alias=True) for e in events])


@app.get("/{cal}.ics")
async def get_ical(cal: str, key: str = "") -> Response:
    if cal not in CONFIG.calendars:
        return Response("Not Found", status_code=404)
    keys = CONFIG.calendars[cal].key
    if keys is not None and key not in keys:
        return Response("Unauthorized", status_code=401)
    c = await get_calendar(CONFIG.calendars[cal])
    return Response(c.to_ical(), media_type="text/calendar")


@app.get("/{cal}")
async def cal_view(
    request: Request,
    cal: str,
    key: str = "",
    session: Annotated[str, Cookie()] = "{}",
) -> Response:
    if cal not in CONFIG.calendars:
        return Response("Not Found", status_code=404)
    cookie = SessionCookie.model_validate_json(session)
    keys = CONFIG.calendars[cal].key
    if keys is not None and (key or cookie.saved_keys.get(cal, "")) not in keys:
        return Response("Unauthorized", status_code=401)
    if key:
        cookie.saved_keys[cal] = key
        response = RedirectResponse(url=f"/{cal}")
        response.set_cookie("session", cookie.model_dump_json())
        return response

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={"cal": cal, "tz": TZ.zone},
    )


async def fetch_data(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as response:
        return await response.text()


def create_event(e: Event, source: SourceConfig) -> Event:
    ne = Event()
    ne.start = e.start
    ne.end = e.end

    if source.tentative:
        ne.add("STATUS", "TENTATIVE")

    for k, v in source.properties.items():
        ne.add(k, v)

    for k in source.include:
        if k in e and k not in ne:
            ne.add(k, e[k])

    if "SUMMARY" not in ne:
        ne.add("SUMMARY", source.event_name)

    return ne


@cached(cache=TTLCache(maxsize=10, ttl=15 * 60))
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

        c.add_component(create_event(e, source))
    return c


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, log_level="info", reload=True)  # noqa: S104
