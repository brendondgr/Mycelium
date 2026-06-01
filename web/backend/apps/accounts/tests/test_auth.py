import pytest
from django.contrib.auth.models import User
from django.test import Client


@pytest.fixture
def api_client() -> Client:
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(
        username="researcher",
        password="safe-pass-123",
        email="researcher@example.com",
    )


@pytest.mark.django_db
def test_csrf_sets_cookie(api_client: Client) -> None:
    response = api_client.get("/api/auth/csrf/")

    assert response.status_code == 200
    assert "csrftoken" in api_client.cookies


@pytest.mark.django_db
def test_me_anonymous_returns_401(api_client: Client) -> None:
    response = api_client.get("/api/auth/me/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_and_me_flow(api_client: Client, user: User) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies["csrftoken"].value

    bad = api_client.post(
        "/api/auth/login/",
        data={"username": user.username, "password": "wrong"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad.status_code == 401
    assert api_client.get("/api/auth/me/").status_code == 401

    good = api_client.post(
        "/api/auth/login/",
        data={"username": user.username, "password": "safe-pass-123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert good.status_code == 200
    payload = good.json()
    assert payload["username"] == user.username
    assert payload["email"] == user.email

    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["id"] == user.pk


@pytest.mark.django_db
def test_login_missing_fields_returns_400(api_client: Client) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies["csrftoken"].value

    response = api_client.post(
        "/api/auth/login/",
        data={"username": "only-user"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_logout_clears_session(api_client: Client, user: User) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies["csrftoken"].value
    api_client.post(
        "/api/auth/login/",
        data={"username": user.username, "password": "safe-pass-123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    api_client.get("/api/auth/csrf/")
    logout_csrf = api_client.cookies["csrftoken"].value
    logout = api_client.post(
        "/api/auth/logout/",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=logout_csrf,
    )
    assert logout.status_code == 204
    assert api_client.get("/api/auth/me/").status_code == 401
