import asyncio
import datetime
import re

import aiohttp
import recurring_ical_events  # type: ignore[import-untyped]
from cachetools import TTLCache
from cachetools_async import cached
from icalendar import Calendar, Component, Event

from config import TZ, CalendarConfig, SourceConfig


@cached(cache=TTLCache(maxsize=20, ttl=30))
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


def as_datetime(dt: datetime.datetime | datetime.date) -> datetime.datetime:
    if isinstance(dt, datetime.datetime):
        return dt
    return datetime.datetime.combine(dt, datetime.time(0, 0, 0), tzinfo=TZ)


def is_all_day(e: Event) -> bool:
    return not isinstance(e.start, datetime.datetime)


def events_between(cal: Component, start: datetime.date, end: datetime.date) -> list[Event]:
    return [e for e in recurring_ical_events.of(cal).between(start, end) if isinstance(e, Event)]


@cached(cache=TTLCache(maxsize=10, ttl=15 * 60))
async def get_calendar(config: CalendarConfig) -> Calendar:
    c = Calendar()
    c.add("REFRESH-INTERVAL;VALUE=DURATION", "PT15M")
    async with aiohttp.ClientSession() as session:
        icals = await asyncio.gather(*(fetch_data(session, source.url) for source in config.sources))

    events: list[tuple[Event, SourceConfig]] = []
    for ical, source in zip(icals, config.sources, strict=True):
        cal = Calendar().from_ical(ical)
        source_events = events_between(
            cal,
            datetime.datetime.now(tz=TZ),
            datetime.datetime.now(tz=TZ) + datetime.timedelta(days=config.days_ahead),
        )
        events.extend((e, source) for e in source_events)

    for e, source in sorted(events, key=lambda e: (as_datetime(e[0].start), -e[0].duration.total_seconds())):
        if source.filter.name_regex and not re.search(source.filter.name_regex, e.get("SUMMARY", "")):
            continue

        if e.get("TRANSP", "OPAQUE") != "OPAQUE":
            continue

        if source.hide_if_overlapped and not is_all_day(e):
            overlaps = events_between(c, e.start, e.end)
            if any(e2.start <= e.start and e2.end >= e.end for e2 in overlaps if not is_all_day(e2)):
                continue

        c.add_component(create_event(e, source))
    return c
