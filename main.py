import datetime
import os
from pathlib import Path
from typing import Annotated, Any

import pytz
import recurring_ical_events
import requests
import yaml
from fastapi import FastAPI, Response
from icalendar import Calendar, Event
from pydantic import BaseModel, BeforeValidator

VERSION = "0.3.0"

TZ = pytz.timezone(os.getenv("TZ", "Europe/Vienna"))
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", "config.yaml"))


app = FastAPI()


def ensure_list(value: Any) -> list[Any] | None:  # noqa: ANN401
    if value is None:
        return None
    if not isinstance(value, list):
        return [value]
    return value


class SourceConfig(BaseModel):
    url: str
    include: list[str] = []
    event_name: str = "Busy"
    hide_if_overlapped: bool = False


class CalendarConfig(BaseModel):
    sources: list[SourceConfig]
    key: Annotated[list[str] | None, BeforeValidator(ensure_list)] = None
    days_ahead: int = 28


class Config(BaseModel):
    calendars: dict[str, CalendarConfig]


CONFIG = Config.model_validate(yaml.safe_load(CONFIG_FILE.read_text()))


@app.get("/{cal}.ics")
def get_ical(cal: str, key: str = "") -> Response:
    if cal not in CONFIG.calendars:
        return Response("Not Found", status_code=404)
    keys = CONFIG.calendars[cal].key
    if keys is not None and key not in keys:
        return Response("Unauthorized", status_code=401)
    c = get_calendar(CONFIG.calendars[cal])
    return Response(c.to_ical(), media_type="text/calendar")


def get_calendar(config: CalendarConfig) -> Calendar:
    c = Calendar()
    for source in config.sources:
        ical = requests.get(source.url, timeout=5)
        cal = Calendar().from_ical(ical.text)
        source_events: list[Event] = recurring_ical_events.of(cal).between(
            datetime.datetime.now(tz=TZ).date(),
            datetime.datetime.now(tz=TZ).date() + datetime.timedelta(days=config.days_ahead),
        )  # type: ignore
        for e in source_events:
            if e.get("TRANSP", "OPAQUE") != "OPAQUE":
                continue

            if source.hide_if_overlapped:
                overlaps: list[Event] = recurring_ical_events.of(c).between(
                    e.start,
                    e.end,
                )  # type: ignore
                if any(e2.start < e.start and e2.end > e.end for e2 in overlaps):
                    continue

            ne = Event()
            ne.start = e.start
            ne.end = e.end
            for k in source.include:
                if k in e:
                    ne.add(k, e[k])
            if "SUMMARY" not in ne:
                ne.add("SUMMARY", source.event_name)
            c.add_component(ne)
    return c


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, log_level="info", reload=True)  # noqa: S104
