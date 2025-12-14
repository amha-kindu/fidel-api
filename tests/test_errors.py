import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers


def build_app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=418, detail="teapot")

    @app.get("/validation-error")
    async def validation_error(limit: int):
        return {"limit": limit}

    @app.get("/server-error")
    async def server_error():
        raise RuntimeError("boom")

    return app


@pytest.fixture
def test_app():
    return build_app()


@pytest.mark.unit
def test_http_exception_handler(test_app):
    client = TestClient(test_app)
    resp = client.get("/http-error")
    assert resp.status_code == 418
    assert resp.json() == {"detail": "teapot"}


@pytest.mark.unit
def test_validation_exception_handler(test_app):
    client = TestClient(test_app)
    resp = client.get("/validation-error")  # missing required query param
    assert resp.status_code == 422
    assert "detail" in resp.json()


@pytest.mark.unit
def test_unhandled_exception_handler(test_app):
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get("/server-error")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal Server Error"}
