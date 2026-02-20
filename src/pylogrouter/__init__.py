from collections.abc import Iterable

from .errors import HtmlSanitizationError, UnsafeLogTargetError
from .router import LoggerRouter, get_logger
from .types import (
    HtmlTheme,
    LEVEL_DEBUG,
    LEVEL_INFO,
    NATURE_ERROR,
    NATURE_INFO,
    NATURE_WARNING,
    THEME_DARK,
    THEME_LIGHT,
    LoggerLevel,
    LogNature,
    LogRecord,
)
from .version import __version__

logger = get_logger()

# Backward-compatible aliases for migrated application code
LVL_DBG = LEVEL_DEBUG
LVL_INF = LEVEL_INFO
CLS_INF = NATURE_INFO
CLS_WRN = NATURE_WARNING
CLS_ERR = NATURE_ERROR
FCL_CON = "console"
FCL_APP = "app"


def configure_logger(level: LoggerLevel, color: bool, suppress_logger_greeting: bool = True) -> LoggerRouter:
    return LoggerRouter(
        logger_level=level,
        logger_color=color,
        suppress_logger_greeting=suppress_logger_greeting,
    )


def set_debug(enabled: bool) -> None:
    router = get_logger()
    router.set_level(LEVEL_DEBUG if enabled else LEVEL_INFO)


def logit(
    message: str,
    level: LoggerLevel = LEVEL_DEBUG,
    nature: LogNature = NATURE_INFO,
    facilities: Iterable[str] | None = None,
) -> None:
    get_logger().log(message=message, level=level, nature=nature, handles=facilities)


__all__ = [
    "LoggerRouter",
    "get_logger",
    "logger",
    "LoggerLevel",
    "LogNature",
    "HtmlTheme",
    "LogRecord",
    "LEVEL_DEBUG",
    "LEVEL_INFO",
    "NATURE_INFO",
    "NATURE_WARNING",
    "NATURE_ERROR",
    "THEME_DARK",
    "THEME_LIGHT",
    "logit",
    "configure_logger",
    "set_debug",
    "LVL_DBG",
    "LVL_INF",
    "CLS_INF",
    "CLS_WRN",
    "CLS_ERR",
    "FCL_CON",
    "FCL_APP",
    "HtmlSanitizationError",
    "UnsafeLogTargetError",
    "__version__",
]
