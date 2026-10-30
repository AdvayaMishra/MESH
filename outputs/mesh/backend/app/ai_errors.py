from fastapi import HTTPException


class ProviderNotDispatched(HTTPException):
    """Trusted adapter proof that no model HTTP request was sent."""

    def __init__(self):
        super().__init__(503, "AI request was not dispatched")
