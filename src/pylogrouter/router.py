from __future__ import annotations

from datetime import datetime
from threading import RLock
import time
from typing import Iterable

from .errors import HtmlSanitizationError, UnsafeLogTargetError
from .facilities import ConsoleFacility, FileFacility, HtmlFileFacility, LogFacility
from .types import (
    THEME_DARK,
    THEME_LIGHT,
    HtmlTheme,
    LEVEL_DEBUG,
    LEVEL_INFO,
    NATURE_ERROR,
    NATURE_INFO,
    NATURE_WARNING,
    LoggerLevel,
    LogNature,
    LogRecord,
)
_LEVEL_PRIORITY: dict[LoggerLevel, int] = {
    LEVEL_DEBUG: 10,
    LEVEL_INFO: 20,
}
_DEFAULT_MAX_MESSAGE_LENGTH = 32_768
_DEFAULT_MAX_MESSAGE_LINES = 500
_DEFAULT_MAX_LINE_LENGTH = 4_096
_DEFAULT_MAX_LOG_HANDLES_PER_CALL = 64
_DEFAULT_COLORIZE_TIMEOUT_MS = 15
_DEFAULT_MAX_HTML_DOCUMENT_BYTES = 10 * 1024 * 1024
_DEFAULT_MAX_HTML_TITLE_LENGTH = 256
_DEFAULT_MAX_WRITES_PER_SECOND = 200
_DEFAULT_THROTTLE_WINDOW_SECONDS = 1
_DEFAULT_PLAIN_LOG_MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024


class LoggerRouter:
    LEVEL_DEBUG = LEVEL_DEBUG
    LEVEL_INFO = LEVEL_INFO
    NATURE_INFO = NATURE_INFO
    NATURE_WARNING = NATURE_WARNING
    NATURE_ERROR = NATURE_ERROR
    THEME_DARK = THEME_DARK
    THEME_LIGHT = THEME_LIGHT
    HANDLE_CONSOLE = "console"

    _instance: "LoggerRouter | None" = None
    _instance_lock = RLock()

    def __new__(
        cls,
        logger_level: LoggerLevel = LEVEL_INFO,
        logger_color: bool = True,
        suppress_logger_greeting: bool = True,
        max_message_length: int = _DEFAULT_MAX_MESSAGE_LENGTH,
        max_message_lines: int = _DEFAULT_MAX_MESSAGE_LINES,
        max_line_length: int = _DEFAULT_MAX_LINE_LENGTH,
        max_log_handles_per_call: int = _DEFAULT_MAX_LOG_HANDLES_PER_CALL,
        colorize_timeout_ms: int = _DEFAULT_COLORIZE_TIMEOUT_MS,
        max_html_document_bytes: int = _DEFAULT_MAX_HTML_DOCUMENT_BYTES,
        max_html_title_length: int = _DEFAULT_MAX_HTML_TITLE_LENGTH,
        max_writes_per_second: int = _DEFAULT_MAX_WRITES_PER_SECOND,
        throttle_window_seconds: int = _DEFAULT_THROTTLE_WINDOW_SECONDS,
        plain_log_max_file_size_bytes: int = _DEFAULT_PLAIN_LOG_MAX_FILE_SIZE_BYTES,
    ) -> "LoggerRouter":
        with cls._instance_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                cls._instance = instance
                instance._initialized = False
        return cls._instance

    def __init__(
        self,
        logger_level: LoggerLevel = LEVEL_INFO,
        logger_color: bool = True,
        suppress_logger_greeting: bool = True,
        max_message_length: int = _DEFAULT_MAX_MESSAGE_LENGTH,
        max_message_lines: int = _DEFAULT_MAX_MESSAGE_LINES,
        max_line_length: int = _DEFAULT_MAX_LINE_LENGTH,
        max_log_handles_per_call: int = _DEFAULT_MAX_LOG_HANDLES_PER_CALL,
        colorize_timeout_ms: int = _DEFAULT_COLORIZE_TIMEOUT_MS,
        max_html_document_bytes: int = _DEFAULT_MAX_HTML_DOCUMENT_BYTES,
        max_html_title_length: int = _DEFAULT_MAX_HTML_TITLE_LENGTH,
        max_writes_per_second: int = _DEFAULT_MAX_WRITES_PER_SECOND,
        throttle_window_seconds: int = _DEFAULT_THROTTLE_WINDOW_SECONDS,
        plain_log_max_file_size_bytes: int = _DEFAULT_PLAIN_LOG_MAX_FILE_SIZE_BYTES,
    ) -> None:
        """
        Initialize (or reconfigure) singleton logger router.

        Args:
            logger_level: Minimum level to emit ("DEBUG" or "INFO").
            logger_color: Enable ANSI color formatting for console output.
            suppress_logger_greeting: Deprecated parameter kept for backward compatibility.
        """
        with self._instance_lock:
            self._logger_level: LoggerLevel = self._validate_level(logger_level)
            self._suppress_logger_greeting = bool(suppress_logger_greeting)
            self._max_message_length = self._validate_positive(
                "max_message_length", max_message_length
            )
            self._max_message_lines = self._validate_positive(
                "max_message_lines", max_message_lines
            )
            self._max_line_length = self._validate_positive(
                "max_line_length", max_line_length
            )
            self._max_log_handles_per_call = self._validate_positive(
                "max_log_handles_per_call", max_log_handles_per_call
            )
            self._colorize_timeout_ms = self._validate_positive(
                "colorize_timeout_ms", colorize_timeout_ms
            )
            self._max_html_document_bytes = self._validate_positive(
                "max_html_document_bytes", max_html_document_bytes
            )
            self._max_html_title_length = self._validate_positive(
                "max_html_title_length", max_html_title_length
            )
            self._max_writes_per_second = self._validate_positive(
                "max_writes_per_second", max_writes_per_second
            )
            self._throttle_window_seconds = self._validate_positive(
                "throttle_window_seconds", throttle_window_seconds
            )
            self._plain_log_max_file_size_bytes = self._validate_positive(
                "plain_log_max_file_size_bytes", plain_log_max_file_size_bytes
            )
            if not hasattr(self, "_throttle_window_started_at"):
                self._throttle_window_started_at = 0.0
            if not hasattr(self, "_writes_in_current_window"):
                self._writes_in_current_window = 0
            if not hasattr(self, "_dropped_in_current_window"):
                self._dropped_in_current_window = 0
            if not hasattr(self, "_throttle_dropped_total"):
                self._throttle_dropped_total = 0
            if not hasattr(self, "_throttle_dropped_by_handle"):
                self._throttle_dropped_by_handle: dict[str, int] = {}
            if not hasattr(self, "_facilities"):
                self._facilities: dict[str, LogFacility] = {}
            if not hasattr(self, "_mock_index"):
                self._mock_index = 0
            if "console" not in self._facilities:
                self._facilities["console"] = ConsoleFacility(
                    color=logger_color,
                    max_line_length=self._max_line_length,
                    colorize_timeout_ms=self._colorize_timeout_ms,
                )
            else:
                console = self._facilities["console"]
                if isinstance(console, ConsoleFacility):
                    console.set_color(logger_color)
                    console.set_limits(
                        max_line_length=self._max_line_length,
                        colorize_timeout_ms=self._colorize_timeout_ms,
                    )
            if getattr(self, "_initialized", False):
                return
            self._initialized = True

    def set_level(self, logger_level: LoggerLevel) -> None:
        self._logger_level = self._validate_level(logger_level)

    def set_color(self, enabled: bool) -> None:
        console = self._facilities.get("console")
        if isinstance(console, ConsoleFacility):
            console.set_color(enabled)

    def add_log_file(
        self,
        log_handle: str,
        log_file_path: str,
        rotate_on_start: bool = False,
        rotations_to_keep: int = 0,
    ) -> bool:
        """
        Register plain-text file logging facility.

        Args:
            log_handle: Unique facility handle ([A-Za-z0-9_]+), e.g. "app".
            log_file_path: Target file path for plain-text logs.
            rotate_on_start: Rotate/truncate target file on startup.
            rotations_to_keep: Number of rotated files to preserve.
                Use 0 to truncate current file without creating rotated copies.
        """
        self._validate_facility_params(log_handle, rotations_to_keep)

        try:
            facility = FileFacility.create(
                log_handle=log_handle,
                log_file_path=log_file_path,
                rotate_on_start=rotate_on_start,
                rotations_to_keep=rotations_to_keep,
                max_file_size_bytes=self._plain_log_max_file_size_bytes,
            )
        except (ValueError, UnsafeLogTargetError):
            raise
        except Exception as exc:
            self._console_diagnostic(
                f"Failed to initialize file facility '{log_handle}' at '{log_file_path}': {exc}"
            )
            return False

        self._facilities[log_handle] = facility
        return True

    def add_html_log_file(
        self,
        log_handle: str,
        log_file_path: str,
        title: str,
        html_theme: HtmlTheme = THEME_DARK,
        html_auto_refresh_enabled: bool = False,
        html_auto_refresh_seconds: int = 10,
        rotate_on_start: bool = False,
        rotations_to_keep: int = 0,
    ) -> bool:
        """
        Register HTML logging facility.

        Args:
            log_handle: Unique facility handle ([A-Za-z0-9_]+), e.g. "html_log".
            log_file_path: Target path for HTML log document.
            title: Document title shown in HTML header.
            html_theme: HTML theme ("dark" or "light").
            html_auto_refresh_enabled: Enable meta refresh auto-reload for browser view.
            html_auto_refresh_seconds: Refresh interval in seconds when auto-refresh is enabled.
            rotate_on_start: Rotate/truncate target file on startup.
            rotations_to_keep: Number of rotated files to preserve.
                Use 0 to truncate current file without creating rotated copies.
        """
        self._validate_facility_params(log_handle, rotations_to_keep)
        theme = self._validate_html_theme(html_theme)
        refresh_seconds = self._validate_refresh_seconds(html_auto_refresh_seconds)
        if len(str(title)) > self._max_html_title_length:
            raise ValueError(
                f"title is too long (max {self._max_html_title_length} chars)."
            )

        try:
            facility = HtmlFileFacility.create(
                log_handle=log_handle,
                log_file_path=log_file_path,
                title=title,
                html_theme=theme,
                html_auto_refresh_enabled=bool(html_auto_refresh_enabled),
                html_auto_refresh_seconds=refresh_seconds,
                max_line_length=self._max_line_length,
                colorize_timeout_ms=self._colorize_timeout_ms,
                max_document_bytes=self._max_html_document_bytes,
                rotate_on_start=rotate_on_start,
                rotations_to_keep=rotations_to_keep,
            )
        except (ValueError, UnsafeLogTargetError):
            raise
        except Exception as exc:
            self._console_diagnostic(
                f"Failed to initialize HTML facility '{log_handle}' at '{log_file_path}': {exc}"
            )
            return False

        self._facilities[log_handle] = facility
        return True

    def debug(self, message: str, handles: Iterable[str] | None = None) -> None:
        self.log(message, LEVEL_DEBUG, NATURE_INFO, handles)

    def info(self, message: str, handles: Iterable[str] | None = None) -> None:
        self.log(message, LEVEL_INFO, NATURE_INFO, handles)

    def warning(self, message: str, handles: Iterable[str] | None = None) -> None:
        self.log(message, LEVEL_INFO, NATURE_WARNING, handles)

    def error(self, message: str, handles: Iterable[str] | None = None) -> None:
        self.log(message, LEVEL_INFO, NATURE_ERROR, handles)

    def log(
        self,
        message: str,
        level: LoggerLevel,
        nature: LogNature,
        handles: Iterable[str] | None = None,
    ) -> None:
        """
        Route message to selected facilities.

        Args:
            message: Log message text.
            level: Logging level ("DEBUG" or "INFO").
            nature: Message nature ("INFO", "WARNING", "ERROR").
            handles: Target facility handles. If None, all active facilities are used.
        """
        level = self._validate_level(level)
        nature = self._validate_nature(nature)
        if _LEVEL_PRIORITY[level] < _LEVEL_PRIORITY[self._logger_level]:
            return

        selected_handles = self._resolve_handles(handles)
        prepared_message = self._prepare_message(str(message))
        record = LogRecord(
            message=prepared_message,
            level=level,
            nature=nature,
            timestamp=datetime.now(),
        )
        for handle in selected_handles:
            if self._should_drop_write_due_to_throttle(handle):
                continue
            facility = self._facilities[handle]
            try:
                facility.write(record)
            except (HtmlSanitizationError, UnsafeLogTargetError) as exc:
                self._console_diagnostic(
                    f"Security incident in facility '{handle}': {exc}"
                )
            except Exception as exc:
                self._console_diagnostic(
                    f"Failed to write log into facility '{handle}': {exc}"
                )

    def _should_drop_write_due_to_throttle(self, handle: str) -> bool:
        now = time.monotonic()
        if self._throttle_window_started_at <= 0:
            self._throttle_window_started_at = now
        elapsed = now - self._throttle_window_started_at
        if elapsed >= self._throttle_window_seconds:
            if self._dropped_in_current_window > 0:
                self._console_diagnostic(
                    "Throttling activated: dropped "
                    f"{self._dropped_in_current_window} write(s) in last "
                    f"{self._throttle_window_seconds}s window."
                )
            self._throttle_window_started_at = now
            self._writes_in_current_window = 0
            self._dropped_in_current_window = 0
        if self._writes_in_current_window >= self._max_writes_per_second:
            self._dropped_in_current_window += 1
            self._throttle_dropped_total += 1
            self._throttle_dropped_by_handle[handle] = (
                self._throttle_dropped_by_handle.get(handle, 0) + 1
            )
            return True
        self._writes_in_current_window += 1
        return False

    def get_throttle_stats(self) -> dict[str, int | dict[str, int]]:
        return {
            "dropped_total": self._throttle_dropped_total,
            "dropped_by_handle": dict(self._throttle_dropped_by_handle),
        }

    def mock_logger_output(self) -> None:
        """Write sample records to all active facilities for visual preview."""
        mock_events: list[tuple[LoggerLevel, LogNature, str]] = [
            (
                LEVEL_DEBUG,
                NATURE_INFO,
                "TFMA gateway bootstrapped env='staging' region='eu-central-1' "
                "host='https://api.tfma.local' timeout_ms=4500",
            ),
            (
                LEVEL_INFO,
                NATURE_INFO,
                "TFMA request accepted: method='POST' endpoint='/v1/sessions' status=201 "
                "request_id='req_A11F20' tenant='acme_retail' elapsed_ms=84",
            ),
            (
                LEVEL_DEBUG,
                NATURE_INFO,
                "TFMA auth cache lookup: key='tenant:acme_retail:scope=orders.write' "
                "cache_hit=true ttl_sec=287",
            ),
            (
                LEVEL_INFO,
                NATURE_WARNING,
                "TFMA request throttled: endpoint='/v1/orders/search' status=429\n"
                "request_id='req_7F9A21' tenant_id='acme_eu_west' elapsed_ms=987\n"
                "action='sleep_and_retry' retry_after_ms=1200",
            ),
            (
                LEVEL_INFO,
                NATURE_INFO,
                "TFMA response accepted: endpoint='/v1/orders/search' status=200 items=128\n"
                "cursor='next_01HZX8W9' cache_hit=true parse_mode='strict-json'",
            ),
            (
                LEVEL_DEBUG,
                NATURE_INFO,
                "TFMA model inference metrics: model='risk-v2' feature_count=42 "
                "compute_ms=36 queue_depth=3",
            ),
            (
                LEVEL_INFO,
                NATURE_WARNING,
                "TFMA upstream latency elevated: upstream='ledger-core' p95_ms=812 "
                "p99_ms=1204 circuit_state='half-open'",
            ),
            (
                LEVEL_INFO,
                NATURE_ERROR,
                "TFMA upstream failure: endpoint='/v1/payments/settle' status=503 "
                "request_id='req_92BQ11' correlation_id='corr_3aa7' attempt=3",
            ),
            (
                LEVEL_DEBUG,
                NATURE_INFO,
                "TFMA fallback route disabled reason='strict_mode' feature_flag='disable_fallbacks' value=true",
            ),
            (
                LEVEL_INFO,
                NATURE_INFO,
                "TFMA health heartbeat: api_status='degraded' worker_pool='active' "
                "active_workers=12 queued_jobs=27",
            ),
        ]

        event = mock_events[self._mock_index % len(mock_events)]
        self._mock_index += 1
        self.log(message=event[2], level=event[0], nature=event[1], handles=None)

    def get_handles(self) -> list[str]:
        return list(self._facilities.keys())

    def log_available_facilities(self) -> None:
        facilities = "\n".join(
            f"- {self._facility_descriptor(handle, facility)}"
            for handle, facility in self._facilities.items()
        )
        self.info(f"Available logging facilities:\n{facilities}")

    @staticmethod
    def _facility_descriptor(handle: str, facility: LogFacility) -> str:
        if isinstance(facility, ConsoleFacility):
            return f"{handle}: stdout/stderr"
        if isinstance(facility, FileFacility):
            return f"{handle}: {facility.file_path.resolve()}"
        if isinstance(facility, HtmlFileFacility):
            refresh_part = (
                f", auto_refresh={facility.auto_refresh_seconds}s"
                if facility.auto_refresh_enabled
                else ", auto_refresh=off"
            )
            return (
                f"{handle}: file://{facility.file_path.resolve()} "
                f"(title='{facility.title}', theme='{facility.theme}'{refresh_part})"
            )
        return handle

    def _resolve_handles(self, handles: Iterable[str] | None) -> list[str]:
        if handles is None:
            return list(self._facilities.keys())
        selected = list(handles)
        if len(selected) > self._max_log_handles_per_call:
            raise ValueError(
                f"Too many log handles: {len(selected)} > {self._max_log_handles_per_call}"
            )
        unknown = [item for item in selected if item not in self._facilities]
        if unknown:
            raise ValueError(f"Unknown log handles: {', '.join(unknown)}")
        return selected

    def _prepare_message(self, message: str) -> str:
        normalized = message.replace("\r\n", "\n").replace("\r", "\n")
        if len(normalized) > self._max_message_length:
            normalized = (
                f"{normalized[: self._max_message_length]} "
                f"...[message clipped at {self._max_message_length} chars]"
            )
        lines = normalized.split("\n")
        if len(lines) > self._max_message_lines:
            dropped = len(lines) - self._max_message_lines
            lines = lines[: self._max_message_lines]
            lines.append(f"...[dropped {dropped} line(s)]")
        clipped_lines: list[str] = []
        for line in lines:
            if len(line) > self._max_line_length:
                clipped_lines.append(
                    f"{line[: self._max_line_length]} "
                    f"...[line clipped at {self._max_line_length} chars]"
                )
            else:
                clipped_lines.append(line)
        return "\n".join(clipped_lines)

    @staticmethod
    def _validate_level(level: str) -> LoggerLevel:
        normalized = str(level).strip().upper()
        if normalized not in _LEVEL_PRIORITY:
            raise ValueError(f"Unsupported logger level: {level}")
        return normalized  # type: ignore[return-value]

    @staticmethod
    def _validate_nature(nature: str) -> LogNature:
        normalized = str(nature).strip().upper()
        if normalized not in {NATURE_INFO, NATURE_WARNING, NATURE_ERROR}:
            raise ValueError(f"Unsupported log nature: {nature}")
        return normalized  # type: ignore[return-value]

    @staticmethod
    def _validate_html_theme(theme: str) -> HtmlTheme:
        normalized = str(theme).strip().lower()
        if normalized not in {THEME_DARK, THEME_LIGHT}:
            raise ValueError(f"Unsupported HTML theme: {theme}")
        return normalized  # type: ignore[return-value]

    @staticmethod
    def _validate_refresh_seconds(seconds: int) -> int:
        value = int(seconds)
        if value <= 0:
            raise ValueError("html_auto_refresh_seconds must be > 0.")
        return value

    @staticmethod
    def _validate_positive(name: str, value: int) -> int:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError(f"{name} must be > 0.")
        return parsed

    @staticmethod
    def _validate_facility_params(log_handle: str, rotations_to_keep: int) -> None:
        if log_handle == "console":
            raise ValueError("log_handle 'console' is reserved.")
        if rotations_to_keep < 0:
            raise ValueError("rotations_to_keep must be >= 0.")

    def _console_diagnostic(self, message: str) -> None:
        console = self._facilities.get("console")
        if not isinstance(console, ConsoleFacility):
            return
        console_record = LogRecord(
            message=message,
            level=LEVEL_INFO,
            nature=NATURE_ERROR,
            timestamp=datetime.now(),
        )
        console.write(console_record)


_global_logger: LoggerRouter | None = None


def get_logger() -> LoggerRouter:
    global _global_logger
    if _global_logger is None:
        _global_logger = LoggerRouter()
    return _global_logger
