"""
FastAPI dependencies shared across routes.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


async def verify_api_key(
    x_api_key: str = Header(
        ...,
        description="API key for authentication. Must match the API_KEY environment variable.",
        alias="X-API-Key",
    ),
) -> str:
    """
    Validate the ``X-API-Key`` header against the ``API_KEY`` env var.

    Raises ``401 Unauthorized`` if the key is missing or incorrect.
    """
    expected = os.getenv("API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: API_KEY environment variable is not set.",
        )
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return x_api_key
