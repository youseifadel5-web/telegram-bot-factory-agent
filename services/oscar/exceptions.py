"""Oscar API exception hierarchy."""


class OscarAPIError(Exception):
    """Base Oscar API error."""

    def __init__(self, message: str = "", status: int = 0, payload=None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class OscarTimeoutError(OscarAPIError):
    pass


class OscarAuthError(OscarAPIError):
    pass


class OscarRateLimitError(OscarAPIError):
    pass


class OscarInvalidResponse(OscarAPIError):
    pass
