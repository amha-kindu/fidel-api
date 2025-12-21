import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient


async def register_and_login(client: AsyncClient):
    email = f"user-{uuid.uuid4()}@example.com"
    password = "secret123"
    register_resp = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register_resp.status_code == HTTPStatus.CREATED
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == HTTPStatus.OK
    token = login_resp.json()["access_token"]
    return email, token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_conversation_crud_flow(client: AsyncClient):
    email, token = await register_and_login(client)

    # create
    create_resp = await client.post(
        "/api/v1/chats",
        json={"title": "First chat"},
        headers=auth_header(token),
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    conv = create_resp.json()
    assert conv["title"] == "First chat"
    assert conv["user_id"]
    assert conv["id"]

    # get
    get_resp = await client.get(
        f"/api/v1/chats/{conv['id']}",
        headers=auth_header(token),
    )
    assert get_resp.status_code == HTTPStatus.OK
    payload = get_resp.json()
    assert payload["items"] == []
    assert payload["total"] == 0

    # list
    list_resp = await client.get("/api/v1/chats", headers=auth_header(token))
    assert list_resp.status_code == HTTPStatus.OK
    list_payload = list_resp.json()
    items = list_payload["items"]
    assert any(item["id"] == conv["id"] for item in items)
    assert list_payload["total"] >= 1

    # delete
    delete_resp = await client.delete(
        f"/api/v1/chats/{conv['id']}",
        headers=auth_header(token),
    )
    assert delete_resp.status_code == HTTPStatus.NO_CONTENT

    # now 404
    get_resp = await client.get(
        f"/api/v1/chats/{conv['id']}",
        headers=auth_header(token),
    )
    assert get_resp.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_conversations_pagination_and_order(client: AsyncClient):
    _, token = await register_and_login(client)
    titles = ["Conv A", "Conv B", "Conv C"]
    for title in titles:
        resp = await client.post(
            "/api/v1/chats",
            json={"title": title},
            headers=auth_header(token),
        )
        assert resp.status_code == HTTPStatus.CREATED

    list_resp = await client.get("/api/v1/chats?limit=2", headers=auth_header(token))
    assert list_resp.status_code == HTTPStatus.OK
    list_payload = list_resp.json()
    items = list_payload["items"]
    assert len(items) == 2
    assert list_payload["total"] >= 3

    # ensure sorted desc by created_at (latest first)
    created_times = [item["created_at"] for item in items]
    assert created_times == sorted(created_times, reverse=True)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_conversation_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/chats", json={"title": "Nope"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    resp = await client.get("/api/v1/chats")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    resp = await client.get("/api/v1/chats/some-id", headers=auth_header("bad"))
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_conversation_access_is_user_scoped(client: AsyncClient):
    _, token_user1 = await register_and_login(client)
    _, token_user2 = await register_and_login(client)

    create_resp = await client.post(
        "/api/v1/chats",
        json={"title": "User1 convo"},
        headers=auth_header(token_user1),
    )
    conv_id = create_resp.json()["id"]

    # user2 cannot see it
    get_resp = await client.get(
        f"/api/v1/chats/{conv_id}",
        headers=auth_header(token_user2),
    )
    assert get_resp.status_code == HTTPStatus.NOT_FOUND

    delete_resp = await client.delete(
        f"/api/v1/chats/{conv_id}",
        headers=auth_header(token_user2),
    )
    assert delete_resp.status_code == HTTPStatus.NOT_FOUND
