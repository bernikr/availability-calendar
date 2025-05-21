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

VERSION = "0.2.2"

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
    c = Calendar()
    for e in get_events(CONFIG.calendars[cal]):
        c.add_component(e)
    return Response(c.to_ical(), media_type="text/calendar")


def get_events(config: CalendarConfig) -> list[Event]:
    events = []
    for source in config.sources:
        ical = requests.get(source.url, timeout=5)
        cal = Calendar().from_ical(ical.text)
        source_events = recurring_ical_events.of(cal).between(
            datetime.datetime.now(tz=TZ).date(),
            datetime.datetime.now(tz=TZ).date() + datetime.timedelta(days=config.days_ahead),
        )
        for e in source_events:
            if e.get("TRANSP", "OPAQUE") == "OPAQUE":
                ne = Event()
                ne.add("DTSTART", e["DTSTART"])
                ne.add("DTEND", e["DTEND"])
                for key in source.include:
                    if key in e:
                        ne.add(key, e[key])
                if "SUMMARY" not in ne:
                    ne.add("SUMMARY", source.event_name)
                events.append(ne)
    return events


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")  # noqa: S104
