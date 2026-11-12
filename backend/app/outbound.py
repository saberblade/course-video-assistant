"""Bound the complete HTTP exchange, including slow streaming and connection setup."""
from __future__ import annotations

import asyncio
import time

import httpx


def post_before(url: str, *, deadline: float, connect_timeout: float, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise httpx.ReadTimeout("Request deadline exhausted")

        async def exchange() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.post(
                    url,
                    timeout=httpx.Timeout(remaining, connect=min(connect_timeout, remaining)),
                    **kwargs,
                )

        try:
            return await asyncio.wait_for(exchange(), timeout=remaining)
        except TimeoutError as exc:
            raise httpx.ReadTimeout("Request deadline exhausted") from exc

    return asyncio.run(request())
