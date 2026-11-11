"""同源托管时，浏览器直接打开/刷新 Vue 路由仍应得到前端页面。"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def hosted_client(client, tmp_path, monkeypatch):
    from app import main

    root = tmp_path / "project"
    dist = root / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<html><div id="app">课迹</div></html>', encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('course-review');", encoding="utf-8")
    monkeypatch.setattr(main, "PROJECT_ROOT", root)
    application = main.create_app()
    with TestClient(application) as browser:
        from tests.conftest import sign_in

        sign_in(browser)
        yield browser


@pytest.mark.parametrize("path", ["/", "/login", "/login?redirect=%2Fscreen", "/screen", "/screen?view=library", "/videos/43b4b091-630e-4819-8f56-f20b9120c099?t=62"])
def test_frontend_routes_survive_refresh(hosted_client, path):
    response = hosted_client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="app"' in response.text


@pytest.mark.parametrize("path", ["/api/no-such-route", "/assets/missing.js", "/.env.local", "/missing.css"])
def test_missing_api_or_assets_do_not_receive_html(hosted_client, path):
    response = hosted_client.get(path)
    assert response.status_code == 404
    assert 'id="app"' not in response.text


def test_hosting_keeps_assets_and_api_routes(hosted_client):
    assert hosted_client.get("/assets/app.js").text == "console.log('course-review');"
    response = hosted_client.get("/api/videos")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert hosted_client.head("/screen").status_code == 200
    assert hosted_client.post("/screen").status_code == 405
