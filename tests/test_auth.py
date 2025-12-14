import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/register", json={"email": email, "password": password})


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.mark.asyncio(loop_scope="session")
async def test_register_login_me_success(client: AsyncClient):
    email = f"user-{uuid.uuid4()}@example.com"
    password = "secret123"

    resp = await _register(client, email, password)
    assert resp.status_code == HTTPStatus.CREATED
    created = resp.json()

    resp = await _login(client, email, password)
    assert resp.status_code == HTTPStatus.OK
    token = resp.json()["access_token"]

    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == HTTPStatus.OK
    me = resp.json()
    assert me["email"] == email
    assert me["id"] == created["id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_register_duplicate_email(client: AsyncClient):
    email = f"user-{uuid.uuid4()}@example.com"
    password = "secret123"

    resp1 = await _register(client, email, password)
    assert resp1.status_code == HTTPStatus.CREATED

    resp2 = await _register(client, email, password)
    assert resp2.status_code == HTTPStatus.BAD_REQUEST
    assert resp2.json()["detail"] == "Email already registered"


@pytest.mark.asyncio(loop_scope="session")
async def test_login_wrong_password(client: AsyncClient):
    email = f"user-{uuid.uuid4()}@example.com"
    password = "secret123"
    await _register(client, email, password)

    resp = await _login(client, email, "badpass")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    assert resp.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio(loop_scope="session")
async def test_login_unknown_user(client: AsyncClient):
    resp = await _login(client, "nobody@example.com", "doesntmatter")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    assert resp.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio(loop_scope="session")
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
