from __future__ import annotations

from typing import Literal

QueryErrorCode = Literal["EMPTY_QUERY", "INVALID_COORDINATES"]


class QueryError(Exception):
    def __init__(self, code: QueryErrorCode, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
