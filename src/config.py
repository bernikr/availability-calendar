import os
import re
from pathlib import Path
from typing import Annotated, overload

import pytz
import yaml
from pydantic import BaseModel, BeforeValidator


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


class FilterConfig(ConfigBaseModel):
    name_regex: re.Pattern[str] | None = None


class SourceConfig(ConfigBaseModel):
    url: str
    include: list[str] = []
    event_name: str = "Busy"
    hide_if_overlapped: bool = False
    tentative: bool = False
    properties: dict[str, str] = {}
    filter: FilterConfig = FilterConfig()


class CalendarConfig(ConfigBaseModel):
    sources: list[SourceConfig]
    key: Annotated[list[str] | None, BeforeValidator(ensure_list)] = None
    days_ahead: int = 28


class Config(ConfigBaseModel):
    calendars: dict[str, CalendarConfig]


VERSION = "1.1.0"

TZ = pytz.timezone(os.getenv("TZ", "Europe/Vienna"))
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", Path(__file__).parent.parent / "config.yaml"))

CONFIG = Config.model_validate(yaml.safe_load(CONFIG_FILE.read_text()))
