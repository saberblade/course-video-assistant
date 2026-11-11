"""账号、会话和视频只能由主人查看。"""

from tests.conftest import sign_in


def test_register_does_not_start_a_session(client):
    client.cookies.clear()
    response = client.post(
        "/api/auth/register",
        json={"username": "NewUser", "password": "password-1", "display_name": "新同学"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 201
    assert response.json()["username"] == "newuser"
    assert "session" not in response.cookies
    assert client.get("/api/auth/me").status_code == 401


def test_duplicate_username(client):
    response = client.post(
        "/api/auth/register",
        json={"username": "student_one", "password": "password-1", "display_name": "另一个"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USERNAME_TAKEN"


def test_bad_login_does_not_reveal_whether_the_user_exists(client):
    missing = client.post(
        "/api/auth/login",
        json={"username": "nobody_here", "password": "password-1"},
        headers={"Origin": "http://testserver"},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"username": "student_one", "password": "wrong-password"},
        headers={"Origin": "http://testserver"},
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["error"] == wrong.json()["error"]


def test_me_returns_csrf_and_logout_clears_the_session(client):
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.headers["cache-control"] == "no-store"
    assert me.json()["csrf_token"]
    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_anonymous_and_other_user_cannot_read_a_video(client, make_video):
    video_id = make_video("ready")
    client.cookies.clear()
    assert client.get("/api/videos").status_code == 401
    sign_in(client, "student_two", "password-2")
    assert client.get(f"/api/videos/{video_id}").status_code == 404
    assert client.get("/api/videos").json()["total"] == 0


def test_unowned_old_video_stays_hidden(client, make_video):
    video_id = make_video("ready", owner_id=None)
    assert client.get(f"/api/videos/{video_id}").status_code == 404
    assert client.get("/api/videos").json()["total"] == 0


def test_client_cannot_choose_an_owner(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "another_one",
            "password": "password-1",
            "display_name": "同学",
            "user_id": "43b4b091-630e-4819-8f56-f20b9120c099",
        },
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"
