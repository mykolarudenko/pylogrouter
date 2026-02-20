import argparse
import time

from pylogrouter import LoggerRouter

LOGGER = LoggerRouter(
    logger_level=LoggerRouter.LEVEL_DEBUG,
    logger_color=True,
    # Optional safety overrides for this instance:
    max_message_length=24_000,
    max_message_lines=300,
    max_line_length=2_000,
    colorize_timeout_ms=10,
)


def configure_facilities() -> None:
    # Register plain text facility.
    # `add_log_file` creates missing parent directories by itself.
    file_added = LOGGER.add_log_file(
        log_handle="file_log",
        log_file_path="logs/pylogrouter.log",
        rotate_on_start=True,
        rotations_to_keep=0,
    )

    # Register HTML facility.
    # The HTML file is convenient for visual log inspection in browser.
    html_dark_added = LOGGER.add_html_log_file(
        log_handle="html_dark",
        log_file_path="logs/pylogrouter-dark.html",
        title="PyLogRouter Example Output (Dark Theme)",
        html_theme=LoggerRouter.THEME_DARK,
        html_auto_refresh_enabled=True,
        html_auto_refresh_seconds=3,
        rotate_on_start=True,
        rotations_to_keep=0,
    )

    html_light_added = LOGGER.add_html_log_file(
        log_handle="html_light",
        log_file_path="logs/pylogrouter-light.html",
        title="PyLogRouter Example Output (Light Theme)",
        html_theme=LoggerRouter.THEME_LIGHT,
        # Keep default refresh behavior (disabled), to show default usage.
        rotate_on_start=True,
        rotations_to_keep=0,
    )

    # Fail fast if any facility was not configured.
    if not file_added or not html_dark_added or not html_light_added:
        raise RuntimeError("Failed to configure one or more log facilities.")


def emit_demo_messages() -> None:
    # Print configured facilities so user can confirm routing targets.
    LOGGER.log_available_facilities()

    # Message routed to ALL active facilities because `handles` is omitted.
    LOGGER.info("Demo: this INFO message is routed to all facilities.")

    # Message routed only to selected facilities.
    LOGGER.warning(
        "Demo: this WARNING message is routed only to console and dark HTML log.",
        handles=[LoggerRouter.HANDLE_CONSOLE, "html_dark"],
    )

    # Explicit type example: set both level and nature manually.
    # Here we route an ERROR nature message with DEBUG level.
    LOGGER.log(
        message="Demo: explicit type example with level=DEBUG, nature=ERROR.",
        level=LoggerRouter.LEVEL_DEBUG,
        nature=LoggerRouter.NATURE_ERROR,
        handles=[LoggerRouter.HANDLE_CONSOLE, "file_log", "html_dark", "html_light"],
    )

    # Additional explicit type examples (INFO and WARNING) to show all natures.
    LOGGER.log(
        message="Demo: explicit type example with level=INFO, nature=INFO.",
        level=LoggerRouter.LEVEL_INFO,
        nature=LoggerRouter.NATURE_INFO,
    )
    LOGGER.log(
        message="Demo: explicit type example with level=INFO, nature=WARNING.",
        level=LoggerRouter.LEVEL_INFO,
        nature=LoggerRouter.NATURE_WARNING,
    )


def run_mock_stream(interval_seconds: int) -> None:
    # Continuous mock stream for UI/log-file preview.
    while True:
        LOGGER.mock_logger_output()
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="pylogrouter usage example")
    parser.add_argument(
        "--mock-stream",
        action="store_true",
        help="Run mock logger output in a loop",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Interval in seconds between mock messages",
    )
    args = parser.parse_args()

    configure_facilities()
    emit_demo_messages()

    if args.mock_stream:
        run_mock_stream(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
