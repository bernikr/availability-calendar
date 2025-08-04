import datetime
from pathlib import Path
from typing import Annotated

import recurring_ical_events
from fastapi import APIRouter, Cookie, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from icalendar import Event
from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from config import CONFIG, TZ
from get_calendar import get_calendar

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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
        start=e.start.astimezone(tz=TZ) if isinstance(e.start, datetime.datetime) else e.start,
        end=e.end.astimezone(tz=TZ) if isinstance(e.end, datetime.datetime) else e.end,
        title=e.get("SUMMARY", ""),
        class_names=css_classes,
    )


@router.get("/{cal}.json")
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


@router.get("/{cal}")
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
        response.set_cookie(
            "session",
            cookie.model_dump_json(),
            max_age=60 * 60 * 24 * 400,  # 400 days is maximum lifetime for cookies
        )
        return response

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={"cal": cal, "tz": TZ.zone},
    )
