from collections.abc import Callable

import httpx
import pytest

from immich_tg_bot.immich import ImmichClient


async def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> ImmichClient:
    client = ImmichClient("https://immich.example/api", "key")
    await client.aclose()
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_ping_uses_v3_endpoint_when_available() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200)

    client = await make_client(handler)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()

    assert requested_paths == ["/api/server/ping"]


@pytest.mark.asyncio
async def test_ping_falls_back_to_legacy_endpoint_on_not_found() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        status_code = 404 if request.url.path == "/api/server/ping" else 200
        return httpx.Response(status_code)

    client = await make_client(handler)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()

    assert requested_paths == ["/api/server/ping", "/api/server-info/ping"]


@pytest.mark.asyncio
async def test_ping_does_not_fall_back_for_other_errors() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(503)

    client = await make_client(handler)
    try:
        assert await client.ping() is False
    finally:
        await client.aclose()

    assert requested_paths == ["/api/server/ping"]
