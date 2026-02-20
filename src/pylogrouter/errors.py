class LogRouterError(RuntimeError):
    """Base error for pylogrouter."""


class FacilityValidationError(ValueError):
    """Raised when facility configuration is invalid."""


class HtmlSanitizationError(LogRouterError):
    """Raised when strict HTML sanitization/validation detects unsafe content."""


class UnsafeLogTargetError(LogRouterError):
    """Raised when log target path is unsafe (symlink/special file/etc)."""
