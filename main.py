import datetime
import os
from pathlib import Path

import pytz
import recurring_ical_events
import requests
import yaml
from fastapi import FastAPI, Response
from icalendar import Calendar, Event
from pydantic import BaseModel

TZ = pytz.timezone(os.getenv("TZ", "Europe/Vienna"))
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", "config.yaml"))


app = FastAPI()


class SourceConfig(BaseModel):
    url: str


class CalendarConfig(BaseModel):
    sources: list[SourceConfig]


class Config(BaseModel):
    calendars: dict[str, CalendarConfig]


CONFIG = Config.model_validate(yaml.safe_load(CONFIG_FILE.read_text()))


@app.get("/{cal}")
def get_ical(cal: str) -> Response:
    if cal not in CONFIG.calendars:
        return Response("Calendar not found", status_code=404)
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
            datetime.datetime.now(tz=TZ).date() + datetime.timedelta(days=7),
        )
        for e in source_events:
            if e["TRANSP"] == "OPAQUE":
                ne = Event()
                ne.add("summary", "Busy")
                ne.add("dtstart", e["DTSTART"])
                ne.add("dtend", e["DTEND"])
                events.append(ne)
    return events


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")  # noqa: S104
