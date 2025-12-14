import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_me(client: AsyncClient):
    email = f"user-{uuid.uuid4()}@example.com"
    password = "secret123"

    # Register
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == email
    assert "id" in data
    assert "created_at" in data

    # Login
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    token = resp.json()
    assert token["token_type"] == "bearer"
    assert token["access_token"]

    # Me
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == email
    assert me["id"] == data["id"]
