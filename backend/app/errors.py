class LibraryError(Exception):
    """A business-rule violation that should be reported to the client."""

    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(LibraryError):
    status_code = 404


class Conflict(LibraryError):
    status_code = 409


class Forbidden(LibraryError):
    status_code = 403
