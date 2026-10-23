"""Shared AI failure type so every provider reports the same frontend codes."""


class AIError(Exception):
    """AI call failure carrying a frontend-displayable code."""

    def __init__(self, code: str, message: str):
        self.code = code  # invalid_key / invalid_model / insufficient_balance / server_error / network_error / unknown
        self.message = message
        super().__init__(message)
