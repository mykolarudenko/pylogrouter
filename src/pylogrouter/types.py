from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

LoggerLevel = Literal["DEBUG", "INFO"]
LogNature = Literal["INFO", "WARNING", "ERROR"]
HtmlTheme = Literal["dark", "light"]

LEVEL_DEBUG: LoggerLevel = "DEBUG"
LEVEL_INFO: LoggerLevel = "INFO"

NATURE_INFO: LogNature = "INFO"
NATURE_WARNING: LogNature = "WARNING"
NATURE_ERROR: LogNature = "ERROR"

THEME_DARK: HtmlTheme = "dark"
THEME_LIGHT: HtmlTheme = "light"


@dataclass(frozen=True)
class LogRecord:
    message: str
    level: LoggerLevel
    nature: LogNature
    timestamp: datetime
