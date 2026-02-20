from __future__ import annotations

import html
import os
import re
import stat
import sys
import time
from functools import cache
from html.parser import HTMLParser
from pathlib import Path
from string import Template
from typing import Protocol

from .errors import HtmlSanitizationError, UnsafeLogTargetError
from .types import LEVEL_DEBUG, NATURE_ERROR, THEME_DARK, THEME_LIGHT, HtmlTheme, LogRecord

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]+$")

_ANSI_RESET = "\033[0m"
_ANSI_WHITE = "\033[97m"
_ANSI_LIGHT_GRAY = "\033[37m"
_ANSI_GREEN = "\033[92m"
_ANSI_YELLOW = "\033[93m"
_ANSI_CYAN = "\033[96m"
_ANSI_PINK = "\033[95m"
_ANSI_RED = "\033[91m"
_ANSI_TIME_CONTENT = "\033[94m"

_PUNCTUATION_CHARS = set(".,+-=<>:;[]{}")
_MAX_HANDLE_LENGTH = 64

_HTML_TEMPLATE_MARKER = "<!-- PYLOGROUTER_STREAM_ENTRIES -->"

_TEMPLATES_DIR = Path(__file__).with_name("templates")
_HTML_TEMPLATE_FILE = _TEMPLATES_DIR / "log_document.html"

_ALLOWED_HTML_ROW_TAGS = {"div", "pre", "span"}
_ALLOWED_HTML_ROW_CLASSES = {
    "log-row",
    "log-line-no",
    "log-time",
    "log-date",
    "log-clock",
    "badge-info",
    "badge-debug",
    "badge-warning",
    "badge-error",
    "syn-base",
    "syn-quote-mark",
    "syn-quote-content",
    "syn-number",
    "syn-punct",
    "syn-lhs",
}
_BIDI_CONTROL_CODEPOINTS = {
    0x061C,
    0x200E,
    0x200F,
    0x202A,
    0x202B,
    0x202C,
    0x202D,
    0x202E,
    0x2066,
    0x2067,
    0x2068,
    0x2069,
}


@cache
def _load_html_document_template() -> Template:
    raw = _HTML_TEMPLATE_FILE.read_text(encoding="utf-8")
    return Template(raw)


# Embedded Pico-inspired stylesheet (no CDN).
# Uses Pico-like CSS variables so dark/light theme can be adjusted via variables.
_PICO_EMBEDDED_CSS = """
body {
  --pico-font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  --pico-font-size: 16px;
  --pico-line-height: 1.5;
  --pico-border-radius: 0.25rem;
}

body.theme-light {
  --pico-color: #1f2937;
  --pico-muted-color: #64748b;
  --pico-background-color: #f8fafc;
  --pico-card-background-color: #ffffff;
  --pico-border-color: #e2e8f0;
  --pico-primary: #2563eb;

  --pico-ins-color: #0f766e;
  --pico-del-color: #dc2626;
  --pico-code-color: #334155;
  --pico-form-element-color: #111827;
  --pico-secondary: #6b7280;
  --log-row-divider: color-mix(in srgb, var(--pico-background-color) 94%, #000000);
}

body.theme-dark {
    --pico-color: #e2e8f0;
    --pico-muted-color: #94a3b8;
    --pico-background-color: #0b1220;
    --pico-card-background-color: #111827;
    --pico-border-color: #1f2937;
    --pico-primary: #60a5fa;

    --pico-ins-color: #2dd4bf;
    --pico-del-color: #f87171;
    --pico-code-color: #cbd5e1;
    --pico-form-element-color: #f8fafc;
    --pico-secondary: #9ca3af;
    --log-row-divider: color-mix(in srgb, var(--pico-background-color) 88%, #ffffff);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 0.35rem 0.65rem;
  font-family: var(--pico-font-family);
  font-size: var(--pico-font-size);
  line-height: var(--pico-line-height);
  color: var(--pico-color);
  background: var(--pico-background-color);
}

main {
  width: 100%;
  margin: 0;
}

header {
  margin-bottom: 0.75rem;
}

article {
  background: var(--pico-card-background-color);
  border: 1px solid var(--pico-border-color);
  border-radius: var(--pico-border-radius);
  padding: 0.45rem;
}

.log-stream {
  display: block;
}

.log-row {
  display: grid;
  grid-template-columns: 7ch 20ch 2ch 1fr;
  column-gap: 0.75rem;
  align-items: start;
  min-width: 0;
  padding: 0.2rem 0.25rem;
  border-radius: calc(var(--pico-border-radius) / 2);
  border-bottom: 1px solid var(--log-row-divider);
}

.log-row:hover {
  background: color-mix(in srgb, var(--pico-primary) 8%, transparent);
}

.log-line-no {
  color: var(--pico-muted-color);
  text-align: right;
}

.log-time {
  color: var(--pico-secondary);
}

.log-date {
  color: var(--pico-primary);
}

.log-clock {
  color: var(--pico-ins-color);
}

.badge-info {
  color: var(--pico-ins-color);
}

.badge-debug {
  color: var(--pico-secondary);
}

.badge-warning {
  color: var(--pico-primary);
}

.badge-error {
  color: var(--pico-del-color);
}

pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  color: var(--pico-code-color);
}

.syn-base { color: var(--pico-code-color); }
.syn-quote-mark { color: var(--pico-ins-color); }
.syn-quote-content { color: var(--pico-primary); }
.syn-number { color: var(--pico-ins-color); }
.syn-punct { color: var(--pico-ins-color); }
.syn-lhs { color: var(--pico-del-color); }
"""


class LogFacility(Protocol):
    handle: str

    def write(self, record: LogRecord) -> None:
        ...


def normalize_newlines(text: str) -> str:
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def split_console_lines(text: str) -> list[str]:
    normalized = normalize_newlines(text)
    return normalized.split("\n")


def flatten_message(text: str) -> str:
    normalized = normalize_newlines(text)
    return re.sub(r"\s*\n\s*", " ", normalized).strip()


def normalize_for_html(text: str) -> str:
    normalized = normalize_newlines(text)
    safe_chars: list[str] = []
    for char in normalized:
        codepoint = ord(char)
        is_c0_or_c1 = (0x00 <= codepoint <= 0x1F) or (0x7F <= codepoint <= 0x9F)
        if char in {"\n", "\t"}:
            safe_chars.append(char)
        elif is_c0_or_c1 or codepoint in _BIDI_CONTROL_CODEPOINTS:
            safe_chars.append("\uFFFD")
        else:
            safe_chars.append(char)
    return "".join(safe_chars)


def escape_html_strict(text: str) -> str:
    return html.escape(normalize_for_html(text), quote=True)


def normalize_for_terminal(text: str) -> str:
    normalized = normalize_newlines(text)
    safe_chars: list[str] = []
    for char in normalized:
        codepoint = ord(char)
        is_c0_or_c1 = (0x00 <= codepoint <= 0x1F) or (0x7F <= codepoint <= 0x9F)
        if char in {"\n", "\t"}:
            safe_chars.append(char)
        elif is_c0_or_c1:
            safe_chars.append("\uFFFD")
        else:
            safe_chars.append(char)
    return "".join(safe_chars)


class StrictHtmlFragmentValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._stack: list[str] = []
        self._saw_root = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _ALLOWED_HTML_ROW_TAGS:
            raise HtmlSanitizationError(f"Disallowed HTML tag: '{tag}'")
        if not self._saw_root:
            if tag != "div":
                raise HtmlSanitizationError("HTML row must start with a <div> root.")
            self._saw_root = True
        self._validate_attributes(tag, attrs)
        self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _ALLOWED_HTML_ROW_TAGS:
            raise HtmlSanitizationError(f"Disallowed closing HTML tag: '{tag}'")
        if not self._stack:
            raise HtmlSanitizationError("Unexpected closing tag in HTML fragment.")
        expected_tag = self._stack.pop()
        if expected_tag != tag:
            raise HtmlSanitizationError(
                f"Unbalanced HTML tags: expected '</{expected_tag}>' but got '</{tag}>'"
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raise HtmlSanitizationError(
            f"Self-closing HTML tag '<{tag}/>' is not allowed in log rows."
        )

    def handle_comment(self, data: str) -> None:
        raise HtmlSanitizationError("HTML comments are not allowed in log rows.")

    @staticmethod
    def _validate_attributes(tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for attr_name, attr_value in attrs:
            lowered_attr = attr_name.lower()
            if lowered_attr.startswith("on"):
                raise HtmlSanitizationError(
                    f"Event handler attribute '{attr_name}' is not allowed."
                )
            if lowered_attr != "class":
                raise HtmlSanitizationError(
                    f"Attribute '{attr_name}' is not allowed on '<{tag}>'."
                )
            if attr_value is None:
                raise HtmlSanitizationError("Empty class attribute is not allowed.")
            classes = [item for item in attr_value.split() if item]
            if not classes:
                raise HtmlSanitizationError("Class attribute must not be empty.")
            for class_name in classes:
                if class_name not in _ALLOWED_HTML_ROW_CLASSES:
                    raise HtmlSanitizationError(
                        f"Disallowed CSS class in HTML fragment: '{class_name}'"
                    )

    def validate_complete(self) -> None:
        if not self._saw_root:
            raise HtmlSanitizationError("HTML row validator did not find root tag.")
        if self._stack:
            raise HtmlSanitizationError("HTML row has unclosed tags.")


def validate_rendered_row_or_raise(row_html: str) -> None:
    validator = StrictHtmlFragmentValidator()
    validator.feed(row_html)
    validator.close()
    validator.validate_complete()


def assert_safe_log_target(path: Path) -> None:
    absolute_path = path if path.is_absolute() else (Path.cwd() / path)
    for parent in [absolute_path.parent, *absolute_path.parent.parents]:
        if parent.is_symlink():
            raise UnsafeLogTargetError(
                f"Unsafe log target parent path is symlink: '{parent}'"
            )

    try:
        path_lstat = os.lstat(absolute_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise UnsafeLogTargetError(
            f"Unable to inspect log target '{absolute_path}': {exc}"
        ) from exc

    if stat.S_ISLNK(path_lstat.st_mode):
        raise UnsafeLogTargetError(f"Unsafe log target is symlink: '{absolute_path}'")
    if not stat.S_ISREG(path_lstat.st_mode):
        raise UnsafeLogTargetError(
            f"Unsafe log target must be a regular file: '{absolute_path}'"
        )


class SyntaxColorizer:
    @staticmethod
    def _check_deadline(deadline: float | None) -> None:
        if deadline is not None and time.perf_counter() >= deadline:
            raise TimeoutError("Syntax colorization time budget exceeded.")

    @staticmethod
    def quoted_content_spans(
        text: str, deadline: float | None = None
    ) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        idx = 0
        while idx < len(text):
            SyntaxColorizer._check_deadline(deadline)
            quote = text[idx]
            if quote not in {'"', "'"}:
                idx += 1
                continue
            start = idx + 1
            cursor = start
            while cursor < len(text):
                SyntaxColorizer._check_deadline(deadline)
                char = text[cursor]
                if char == quote and (cursor == start or text[cursor - 1] != "\\"):
                    spans.append((start, cursor))
                    idx = cursor + 1
                    break
                cursor += 1
            else:
                idx += 1
        return spans

    @staticmethod
    def quote_mark_positions(
        text: str, deadline: float | None = None
    ) -> set[int]:
        positions: set[int] = set()
        idx = 0
        while idx < len(text):
            SyntaxColorizer._check_deadline(deadline)
            quote = text[idx]
            if quote not in {'"', "'"}:
                idx += 1
                continue
            start = idx
            cursor = idx + 1
            while cursor < len(text):
                SyntaxColorizer._check_deadline(deadline)
                char = text[cursor]
                if char == quote and text[cursor - 1] != "\\":
                    positions.add(start)
                    positions.add(cursor)
                    idx = cursor + 1
                    break
                cursor += 1
            else:
                idx += 1
        return positions

    @staticmethod
    def lhs_equals_spans(
        text: str, deadline: float | None = None
    ) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        idx = 0
        length = len(text)
        while idx < length:
            SyntaxColorizer._check_deadline(deadline)
            char = text[idx]
            if not (char.isalpha() or char == "_"):
                idx += 1
                continue
            start = idx
            idx += 1
            while idx < length and (text[idx].isalnum() or text[idx] == "_"):
                SyntaxColorizer._check_deadline(deadline)
                idx += 1
            end = idx
            lookahead = idx
            while lookahead < length and text[lookahead].isspace():
                lookahead += 1
            if lookahead < length and text[lookahead] == "=":
                spans.append((start, end))
        return spans

    @staticmethod
    def index_in_spans(index: int, spans: list[tuple[int, int]]) -> bool:
        for start, end in spans:
            if start <= index < end:
                return True
        return False

    @classmethod
    def token_class(
        cls,
        index: int,
        ch: str,
        quote_spans: list[tuple[int, int]],
        quote_marks: set[int],
        lhs_spans: list[tuple[int, int]],
    ) -> str:
        if index in quote_marks:
            return "quote-mark"
        if cls.index_in_spans(index, quote_spans):
            return "quote-content"
        if cls.index_in_spans(index, lhs_spans):
            return "lhs"
        if ch.isdigit():
            return "number"
        if ch in _PUNCTUATION_CHARS:
            return "punct"
        return "base"


class ConsoleFacility:
    handle = "console"

    def __init__(self, color: bool, max_line_length: int = 4096, colorize_timeout_ms: int = 15) -> None:
        self._color = color
        self._max_line_length = max_line_length
        self._colorize_timeout_ms = colorize_timeout_ms

    def set_color(self, enabled: bool) -> None:
        self._color = enabled

    def set_limits(self, max_line_length: int, colorize_timeout_ms: int) -> None:
        self._max_line_length = max_line_length
        self._colorize_timeout_ms = colorize_timeout_ms

    @staticmethod
    def _badge_icon(record: LogRecord) -> str:
        if record.nature == "ERROR":
            return "×"
        if record.level == "DEBUG" or record.nature == "WARNING":
            return "›"
        return "»"

    @staticmethod
    def _badge_color(record: LogRecord) -> str:
        if record.nature == "ERROR":
            return _ANSI_RED
        if record.level == LEVEL_DEBUG:
            return _ANSI_LIGHT_GRAY
        return _ANSI_GREEN

    @classmethod
    def _color_for_char(
        cls,
        index: int,
        ch: str,
        record: LogRecord,
        quote_spans: list[tuple[int, int]],
        quote_marks: set[int],
        lhs_spans: list[tuple[int, int]],
    ) -> str:
        base_color = _ANSI_LIGHT_GRAY if record.level == LEVEL_DEBUG else _ANSI_WHITE
        token = SyntaxColorizer.token_class(index, ch, quote_spans, quote_marks, lhs_spans)
        if token == "quote-mark":
            return _ANSI_GREEN
        if token == "quote-content":
            return _ANSI_YELLOW
        if token == "lhs":
            return _ANSI_PINK
        if token == "number":
            return _ANSI_CYAN
        if token == "punct":
            return _ANSI_GREEN
        return base_color

    @classmethod
    def _colorize_line(cls, line: str, record: LogRecord) -> str:
        return cls._colorize_line_with_budget(line, record, colorize_timeout_ms=15)

    @classmethod
    def _colorize_line_with_budget(
        cls, line: str, record: LogRecord, colorize_timeout_ms: int
    ) -> str:
        deadline = time.perf_counter() + (max(colorize_timeout_ms, 1) / 1000)
        try:
            quote_spans = SyntaxColorizer.quoted_content_spans(line, deadline=deadline)
            quote_marks = SyntaxColorizer.quote_mark_positions(line, deadline=deadline)
            lhs_spans = SyntaxColorizer.lhs_equals_spans(line, deadline=deadline)
        except TimeoutError:
            base_color = _ANSI_LIGHT_GRAY if record.level == LEVEL_DEBUG else _ANSI_WHITE
            return f"{base_color}{line}{_ANSI_RESET}"
        rendered: list[str] = []
        current_color: str | None = None
        for idx, ch in enumerate(line):
            if time.perf_counter() >= deadline:
                base_color = _ANSI_LIGHT_GRAY if record.level == LEVEL_DEBUG else _ANSI_WHITE
                return f"{base_color}{line}{_ANSI_RESET}"
            color = cls._color_for_char(idx, ch, record, quote_spans, quote_marks, lhs_spans)
            if color != current_color:
                rendered.append(color)
                current_color = color
            rendered.append(ch)
        rendered.append(_ANSI_RESET)
        return "".join(rendered)

    def write(self, record: LogRecord) -> None:
        time_text = record.timestamp.strftime("%H:%M:%S")
        icon = self._badge_icon(record)
        normalized_message = normalize_for_terminal(record.message)
        lines = split_console_lines(normalized_message)
        if not lines:
            lines = [""]
        clipped_lines = [
            line if len(line) <= self._max_line_length else f"{line[: self._max_line_length]} …[line clipped]"
            for line in lines
        ]

        out_lines: list[str] = []
        if not self._color:
            out_lines.append(f"[{time_text}] {icon} {clipped_lines[0]}")
            for line in clipped_lines[1:]:
                out_lines.append(f"\t{line}")
        else:
            colored_time = f"{_ANSI_GREEN}[{_ANSI_TIME_CONTENT}{time_text}{_ANSI_GREEN}]"
            colored_icon = f"{self._badge_color(record)}{icon}{_ANSI_RESET}"
            out_lines.append(
                f"{colored_time} {colored_icon} "
                f"{self._colorize_line_with_budget(clipped_lines[0], record, self._colorize_timeout_ms)}"
            )
            for line in clipped_lines[1:]:
                out_lines.append(
                    f"\t{self._colorize_line_with_budget(line, record, self._colorize_timeout_ms)}"
                )

        file_stream = sys.stderr if record.nature == NATURE_ERROR else sys.stdout
        print("\n".join(out_lines), file=file_stream, flush=True)


class FileFacility:
    def __init__(
        self, handle: str, file_path: Path, rotations_to_keep: int, max_file_size_bytes: int
    ) -> None:
        self.handle = handle
        self.file_path = file_path
        self.rotations_to_keep = rotations_to_keep
        self.max_file_size_bytes = max_file_size_bytes

    @staticmethod
    def validate_handle(handle: str) -> None:
        if len(handle) > _MAX_HANDLE_LENGTH:
            raise ValueError(f"log_handle is too long (max {_MAX_HANDLE_LENGTH} chars).")
        if not _HANDLE_RE.fullmatch(handle):
            raise ValueError("log_handle must be alphanumeric with optional underscores.")

    @staticmethod
    def _rotate_files(path: Path, keep: int) -> None:
        assert_safe_log_target(path)
        if keep <= 0:
            path.write_text("", encoding="utf-8")
            return

        oldest = path.with_name(f"{path.name}.{keep}")
        assert_safe_log_target(oldest)
        if oldest.exists():
            oldest.unlink()

        for idx in range(keep - 1, 0, -1):
            src = path.with_name(f"{path.name}.{idx}")
            dst = path.with_name(f"{path.name}.{idx + 1}")
            assert_safe_log_target(src)
            assert_safe_log_target(dst)
            if src.exists():
                src.replace(dst)

        if path.exists():
            assert_safe_log_target(path.with_name(f"{path.name}.1"))
            path.replace(path.with_name(f"{path.name}.1"))

        path.write_text("", encoding="utf-8")

    @classmethod
    def create(
        cls,
        log_handle: str,
        log_file_path: str | Path,
        rotate_on_start: bool,
        rotations_to_keep: int,
        max_file_size_bytes: int,
    ) -> "FileFacility":
        cls.validate_handle(log_handle)
        path = Path(log_file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert_safe_log_target(path)
        if rotate_on_start:
            cls._rotate_files(path, rotations_to_keep)
        if not path.exists():
            path.touch()
        assert_safe_log_target(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("")
        return cls(log_handle, path, rotations_to_keep, max_file_size_bytes)

    def write(self, record: LogRecord) -> None:
        assert_safe_log_target(self.file_path)
        timestamp = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        compact_message = flatten_message(record.message)
        line = f"[{timestamp}] [{record.nature}] {compact_message}\n"
        encoded_line = line.encode("utf-8")
        current_size = self.file_path.stat().st_size if self.file_path.exists() else 0
        if current_size + len(encoded_line) > self.max_file_size_bytes:
            self._rotate_files(self.file_path, self.rotations_to_keep)
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(line)


class HtmlFileFacility:
    def __init__(
        self,
        handle: str,
        file_path: Path,
        title: str,
        theme: HtmlTheme,
        auto_refresh_enabled: bool,
        auto_refresh_seconds: int,
        max_line_length: int,
        colorize_timeout_ms: int,
        max_document_bytes: int,
    ) -> None:
        self.handle = handle
        self.file_path = file_path
        self.title = title
        self.theme = theme
        self.auto_refresh_enabled = auto_refresh_enabled
        self.auto_refresh_seconds = auto_refresh_seconds
        self._max_line_length = max_line_length
        self._colorize_timeout_ms = colorize_timeout_ms
        self._max_document_bytes = max_document_bytes
        self._line_number = 0

    @classmethod
    def create(
        cls,
        log_handle: str,
        log_file_path: str | Path,
        title: str,
        html_theme: HtmlTheme,
        html_auto_refresh_enabled: bool,
        html_auto_refresh_seconds: int,
        max_line_length: int,
        colorize_timeout_ms: int,
        max_document_bytes: int,
        rotate_on_start: bool,
        rotations_to_keep: int,
    ) -> "HtmlFileFacility":
        FileFacility.validate_handle(log_handle)
        path = Path(log_file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert_safe_log_target(path)
        if rotate_on_start:
            FileFacility._rotate_files(path, rotations_to_keep)

        facility = cls(
            log_handle,
            path,
            title,
            theme=html_theme,
            auto_refresh_enabled=html_auto_refresh_enabled,
            auto_refresh_seconds=html_auto_refresh_seconds,
            max_line_length=max_line_length,
            colorize_timeout_ms=colorize_timeout_ms,
            max_document_bytes=max_document_bytes,
        )
        facility._ensure_document()
        facility._line_number = facility._detect_existing_line_count()
        return facility

    @staticmethod
    def _badge_icon(record: LogRecord) -> str:
        if record.nature == "ERROR":
            return "⛔"
        if record.level == "DEBUG" or record.nature == "WARNING":
            return "⚠️" if record.nature == "WARNING" else "🐞"
        return "ℹ️"

    @staticmethod
    def _badge_css_class(record: LogRecord) -> str:
        if record.nature == "ERROR":
            return "badge-error"
        if record.level == LEVEL_DEBUG:
            return "badge-debug"
        if record.nature == "WARNING":
            return "badge-warning"
        return "badge-info"

    @staticmethod
    def _syntax_class_to_html(token: str) -> str:
        return f"syn-{token}"

    def _render_html_message(self, message: str) -> str:
        lines = split_console_lines(normalize_for_html(message))
        if not lines:
            lines = [""]

        html_lines: list[str] = []
        for idx_line, raw_line in enumerate(lines):
            line = (
                raw_line
                if len(raw_line) <= self._max_line_length
                else f"{raw_line[: self._max_line_length]} …[line clipped]"
            )
            segments: list[str] = []
            if idx_line > 0:
                segments.append("\t")
            deadline = time.perf_counter() + (max(self._colorize_timeout_ms, 1) / 1000)
            try:
                quote_spans = SyntaxColorizer.quoted_content_spans(line, deadline=deadline)
                quote_marks = SyntaxColorizer.quote_mark_positions(line, deadline=deadline)
                lhs_spans = SyntaxColorizer.lhs_equals_spans(line, deadline=deadline)
                for idx, ch in enumerate(line):
                    if time.perf_counter() >= deadline:
                        raise TimeoutError("HTML syntax colorization budget exceeded.")
                    token = SyntaxColorizer.token_class(
                        idx, ch, quote_spans, quote_marks, lhs_spans
                    )
                    css_class = self._syntax_class_to_html(token)
                    segments.append(
                        f'<span class="{css_class}">{escape_html_strict(ch)}</span>'
                    )
            except TimeoutError:
                segments.append(escape_html_strict(line))
            html_lines.append("".join(segments))
        return "\n".join(html_lines)

    def _ensure_document(self) -> None:
        if self.file_path.exists() and self.file_path.stat().st_size > 0:
            return

        assert_safe_log_target(self.file_path)
        template = _load_html_document_template()
        safe_title = escape_html_strict(self.title)
        theme_class = (
            "theme-dark"
            if self.theme == THEME_DARK
            else "theme-light"
        )
        refresh_meta = (
            f'<meta http-equiv="refresh" content="{self.auto_refresh_seconds}" />'
            if self.auto_refresh_enabled
            else ""
        )
        doc = template.substitute(
            title=safe_title,
            stylesheet=_PICO_EMBEDDED_CSS,
            stream_marker=_HTML_TEMPLATE_MARKER,
            theme_class=theme_class,
            refresh_meta=refresh_meta,
        )
        self.file_path.write_text(doc, encoding="utf-8")

    def _detect_existing_line_count(self) -> int:
        if not self.file_path.exists():
            return 0
        content = self.file_path.read_text(encoding="utf-8")
        return content.count('<div class="log-row">')

    def write(self, record: LogRecord) -> None:
        self._ensure_document()
        assert_safe_log_target(self.file_path)
        timestamp = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        date_part, time_part = timestamp.split(" ", maxsplit=1)
        badge = self._badge_icon(record)
        badge_class = self._badge_css_class(record)
        rendered_message = self._render_html_message(record.message)
        self._line_number += 1
        line_no = f"{self._line_number:06d}"

        row = (
            '<div class="log-row">\n'
            f'  <div class="log-line-no"><pre>{escape_html_strict(line_no)}</pre></div>\n'
            '  <div class="log-time"><pre>'
            f'<span class="log-date">{escape_html_strict(date_part)}</span> '
            f'<span class="log-clock">{escape_html_strict(time_part)}</span>'
            '</pre></div>\n'
            f'  <div class="{badge_class}"><pre>{escape_html_strict(badge)}</pre></div>\n'
            f'  <div><pre>{rendered_message}</pre></div>\n'
            '</div>\n'
        )
        validate_rendered_row_or_raise(row)
        current_size = self.file_path.stat().st_size if self.file_path.exists() else 0
        next_size = current_size + len(row.encode("utf-8"))
        if next_size > self._max_document_bytes:
            raise HtmlSanitizationError(
                f"HTML log size limit exceeded ({next_size} > {self._max_document_bytes} bytes)."
            )
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(row)


def is_valid_handle(value: str) -> bool:
    return _HANDLE_RE.fullmatch(value) is not None
