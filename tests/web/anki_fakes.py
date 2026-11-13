"""Shared AnkiWeb fakes for the web tests: credentials and setup steps."""

import httpx

PASSWORD = "correct-horse"
TOKEN = "hkey-secret-token"


async def builtin(api: httpx.AsyncClient) -> dict:
    response = await api.put("/api/anki/backend", json={"backend": "collection"})
    assert response.status_code == 200, response.text
    return response.json()


async def login(api: httpx.AsyncClient, password: str = PASSWORD) -> httpx.Response:
    return await api.post(
        "/api/anki/login", json={"email": " User@Example.com ", "password": password}
    )
