from __future__ import annotations

from pathlib import Path

import pytest

from pylogrouter import LoggerRouter
from pylogrouter.errors import HtmlSanitizationError, UnsafeLogTargetError
from pylogrouter.facilities import HtmlFileFacility, validate_rendered_row_or_raise
import pylogrouter.router as router_module


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    LoggerRouter._instance = None
    router_module._global_logger = None


def test_default_console_handle_exists() -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    assert "console" in router.get_handles()


def test_add_log_file_creates_parent_and_file(tmp_path: Path) -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    target = tmp_path / "a" / "b" / "app.log"
    ok = router.add_log_file("app", str(target), rotate_on_start=False, rotations_to_keep=0)
    assert ok is True
    assert target.exists()


def test_add_html_log_file_creates_document(tmp_path: Path) -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    target = tmp_path / "a" / "b" / "app.log.html"
    ok = router.add_html_log_file("app_html", str(target), title="Unit Test HTML Log")
    assert ok is True
    content = target.read_text(encoding="utf-8")
    assert "Unit Test HTML Log" in content
    assert "PYLOGROUTER_STREAM_ENTRIES" in content
    assert "</html>" not in content
    assert 'http-equiv="refresh"' not in content
    assert "frame-ancestors" not in content
    assert 'class="theme-dark"' in content


def test_add_html_log_file_with_light_theme_and_refresh(tmp_path: Path) -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    target = tmp_path / "a" / "b" / "app-light.log.html"
    ok = router.add_html_log_file(
        "app_html_light",
        str(target),
        title="Unit Test HTML Log Light",
        html_theme="light",
        html_auto_refresh_enabled=True,
        html_auto_refresh_seconds=3,
    )
    assert ok is True
    content = target.read_text(encoding="utf-8")
    assert 'class="theme-light"' in content
    assert 'http-equiv="refresh" content="3"' in content


def test_no_greeting_is_written_to_newly_added_facility(tmp_path: Path) -> None:
    target = tmp_path / "greeting.log"
    router = LoggerRouter(logger_level="DEBUG", suppress_logger_greeting=False)
    assert router.add_log_file("greeting_file", str(target))
    content = target.read_text(encoding="utf-8")
    assert "Python Log Router" not in content


def test_invalid_handle_raises() -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    with pytest.raises(ValueError):
        router.add_log_file("bad-handle", "./tmp.log")


def test_invalid_html_theme_raises() -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    with pytest.raises(ValueError):
        router.add_html_log_file("app_html", "./tmp.log.html", title="x", html_theme="neon")  # type: ignore[arg-type]


def test_invalid_html_refresh_seconds_raises() -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    with pytest.raises(ValueError):
        router.add_html_log_file(
            "app_html",
            "./tmp.log.html",
            title="x",
            html_auto_refresh_enabled=True,
            html_auto_refresh_seconds=0,
        )


def test_html_title_too_long_raises() -> None:
    router = LoggerRouter(suppress_logger_greeting=True, max_html_title_length=8)
    with pytest.raises(ValueError):
        router.add_html_log_file("app_html", "./tmp.log.html", title="0123456789")


def test_unknown_handle_raises_on_log_call() -> None:
    router = LoggerRouter(suppress_logger_greeting=True)
    with pytest.raises(ValueError):
        router.info("x", handles=["missing"])


def test_too_many_handles_raises_on_log_call(tmp_path: Path) -> None:
    router = LoggerRouter(suppress_logger_greeting=True, max_log_handles_per_call=1)
    router.add_log_file("app", str(tmp_path / "app.log"))
    with pytest.raises(ValueError):
        router.info("x", handles=["console", "app"])


def test_rotate_on_start_keep_zero_truncates(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    target.write_text("old", encoding="utf-8")
    router = LoggerRouter(suppress_logger_greeting=True)
    ok = router.add_log_file("app", str(target), rotate_on_start=True, rotations_to_keep=0)
    assert ok is True
    assert target.read_text(encoding="utf-8") == ""


def test_rotate_on_start_keep_n(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    target.write_text("newest", encoding="utf-8")
    (tmp_path / "app.log.1").write_text("older", encoding="utf-8")

    router = LoggerRouter(suppress_logger_greeting=True)
    ok = router.add_log_file("app", str(target), rotate_on_start=True, rotations_to_keep=2)
    assert ok is True
    assert (tmp_path / "app.log.2").read_text(encoding="utf-8") == "older"
    assert (tmp_path / "app.log.1").read_text(encoding="utf-8") == "newest"
    assert target.read_text(encoding="utf-8") == ""


def test_file_log_flattens_multiline_message(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_log_file("app", str(target))
    router.info("line1\nline2\r\nline3", handles=["app"])
    content = target.read_text(encoding="utf-8")
    assert "line1 line2 line3" in content


def test_router_message_length_limit_clips(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    router = LoggerRouter(suppress_logger_greeting=True, max_message_length=16)
    assert router.add_log_file("app", str(target))
    router.info("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", handles=["app"])
    content = target.read_text(encoding="utf-8")
    assert "message clipped at 16 chars" in content


def test_throttling_drops_excess_writes(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    router = LoggerRouter(
        suppress_logger_greeting=True,
        max_writes_per_second=1,
        throttle_window_seconds=60,
    )
    assert router.add_log_file("app", str(target))
    router.info("first", handles=["app"])
    router.info("second", handles=["app"])
    router.info("third", handles=["app"])
    content = target.read_text(encoding="utf-8")
    assert "first" in content
    assert "second" not in content
    assert "third" not in content
    stats = router.get_throttle_stats()
    assert stats["dropped_total"] == 2
    assert stats["dropped_by_handle"] == {"app": 2}


def test_plain_log_rotates_by_size(tmp_path: Path) -> None:
    target = tmp_path / "size.log"
    router = LoggerRouter(
        suppress_logger_greeting=True,
        plain_log_max_file_size_bytes=160,
    )
    assert router.add_log_file("app", str(target), rotate_on_start=False, rotations_to_keep=2)
    for idx in range(10):
        router.info(f"line-{idx} " + ("X" * 50), handles=["app"])
    rotated = tmp_path / "size.log.1"
    assert rotated.exists()
    assert rotated.stat().st_size > 0


def test_html_log_preserves_multiline_message(tmp_path: Path) -> None:
    target = tmp_path / "app.log.html"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_html_log_file("app_html", str(target), title="HTML")
    router.warning("line1\nline2='42'", handles=["app_html"])
    content = target.read_text(encoding="utf-8")
    assert '<span class="syn-base">l</span>' in content
    assert "syn-quote-content" in content
    assert "syn-number" in content
    assert 'class="log-date"' in content
    assert 'class="log-clock"' in content
    assert "syn-lhs { color: var(--pico-del-color); }" in content
    assert "border-bottom: 1px solid var(--log-row-divider);" in content


def test_mock_logger_output_writes_to_facilities(tmp_path: Path) -> None:
    text_log = tmp_path / "mockup.log"
    html_log = tmp_path / "mockup.log.html"
    router = LoggerRouter(logger_level="DEBUG", suppress_logger_greeting=True)
    assert router.add_log_file("mock_file", str(text_log))
    assert router.add_html_log_file("mock_html", str(html_log), title="Mock")
    router.mock_logger_output()
    assert text_log.exists() and text_log.stat().st_size > 0
    assert html_log.exists() and html_log.stat().st_size > 0


def test_html_log_escapes_script_payload(tmp_path: Path) -> None:
    target = tmp_path / "security.log.html"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_html_log_file("security_html", str(target), title="Security")
    router.info("<script>alert(1)</script>", handles=["security_html"])
    content = target.read_text(encoding="utf-8")
    assert "<script>" not in content
    assert '&lt;</span><span class="syn-base">s' in content


def test_html_log_escapes_attribute_injection_payload(tmp_path: Path) -> None:
    target = tmp_path / "security_attr.log.html"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_html_log_file("security_html", str(target), title="Security")
    router.info('"><img src=x onerror=alert(1)>', handles=["security_html"])
    content = target.read_text(encoding="utf-8")
    assert "<img" not in content
    assert "syn-lhs" in content


def test_html_log_payload_cannot_break_row_structure(tmp_path: Path) -> None:
    target = tmp_path / "security_row.log.html"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_html_log_file("security_html", str(target), title="Security")
    router.warning("</pre></div><script>alert(1)</script>", handles=["security_html"])
    content = target.read_text(encoding="utf-8")
    assert content.count('<div class="log-row">') == 1
    assert "<script>" not in content


def test_html_log_normalizes_control_and_bidi_characters(tmp_path: Path) -> None:
    target = tmp_path / "security_ctrl.log.html"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_html_log_file("security_html", str(target), title="Security")
    payload = "safe\x00text\u202edanger\nnext"
    router.info(payload, handles=["security_html"])
    content = target.read_text(encoding="utf-8")
    assert "\x00" not in content
    assert "\u202e" not in content
    assert "\uFFFD" in content


def test_html_row_validator_fails_fast_on_invalid_class() -> None:
    bad_row = (
        '<div class="log-row">\n'
        '  <div class="log-time"><pre>2026-01-01 00:00:00</pre></div>\n'
        '  <div class="badge-info"><pre>ℹ️</pre></div>\n'
        '  <div><pre><span class="evil-class">x</span></pre></div>\n'
        "</div>\n"
    )
    with pytest.raises(HtmlSanitizationError):
        validate_rendered_row_or_raise(bad_row)


def test_html_log_fail_fast_bubbles_up_on_tampered_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "tampered.log.html"
    router = LoggerRouter(suppress_logger_greeting=True)
    assert router.add_html_log_file("security_html", str(target), title="Security")
    before_content = target.read_text(encoding="utf-8")

    monkeypatch.setattr(
        HtmlFileFacility,
        "_syntax_class_to_html",
        staticmethod(lambda token: 'syn-base" onclick="alert(1)'),
    )
    router.info("tampered", handles=["security_html"])
    after_content = target.read_text(encoding="utf-8")
    assert after_content == before_content


def test_add_log_file_rejects_symlink_target(tmp_path: Path) -> None:
    real_target = tmp_path / "real.log"
    real_target.write_text("", encoding="utf-8")
    symlink_target = tmp_path / "symlink.log"
    symlink_target.symlink_to(real_target)

    router = LoggerRouter(suppress_logger_greeting=True)
    with pytest.raises(UnsafeLogTargetError):
        router.add_log_file("app", str(symlink_target), rotate_on_start=False, rotations_to_keep=0)


def test_rotate_rejects_unsafe_chain_file(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    target.write_text("newest", encoding="utf-8")
    unsafe_target = tmp_path / "app.log.1"
    unsafe_target.symlink_to(tmp_path / "outside.log")

    router = LoggerRouter(suppress_logger_greeting=True)
    with pytest.raises(UnsafeLogTargetError):
        router.add_log_file("app", str(target), rotate_on_start=True, rotations_to_keep=2)


def test_console_output_sanitizes_control_sequences(capsys: pytest.CaptureFixture[str]) -> None:
    router = LoggerRouter(logger_color=False, suppress_logger_greeting=True)
    router.info("safe \x1b[31mred\x1b[0m text", handles=["console"])
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "red" in out
