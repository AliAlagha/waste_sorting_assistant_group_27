# Web UI and REST API
import io

import pytest

from webapp.app import create_app
from helpers import make_image


@pytest.fixture
def client(gateway):
    app = create_app(gateway, seed_demo_data=False)
    app.config["TESTING"] = True
    return app.test_client()


def login(client, username, password):
    token = client.post("/api/auth/login", json={"username": username, "password": password}).get_json()["token"]
    return {"Authorization": "Bearer " + token}


def test_every_role_sees_only_its_pages(client):
    for path in ["/", "/guide", "/login", "/register", "/api/docs"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/scan").status_code == 302                  # guest -> login page
    for user, password, allowed, refused in [
        ("anna", "anna123", ["/scan", "/history", "/bins", "/profile"], ["/dashboard", "/users"]),
        ("city", "city123", ["/dashboard", "/scan", "/history"], ["/users", "/system"]),
        ("root", "root123", ["/users", "/system", "/profile"], ["/dashboard"]),
    ]:
        client.post("/login", data={"username": user, "password": password})
        assert all(client.get(p).status_code == 200 for p in allowed), user
        assert all(client.get(p).status_code == 302 for p in refused), user
        client.get("/logout")


def test_rest_api_register_scan_history(client):
    assert client.post("/api/auth/register", json={"username": "ben", "password": "ben12345"}).status_code == 400  # no city
    assert client.post("/api/auth/register", json={"username": "ben", "password": "ben12345",
                                                   "region_name": "Bochum"}).status_code == 201
    headers = login(client, "ben", "ben12345")
    response = client.post("/api/scans", data={"image": (io.BytesIO(make_image()), "photo.png")}, headers=headers)
    assert response.status_code == 201 and response.get_json()["recommendation"]["bin_name"] == "Yellow bin"
    assert client.get("/api/scans/history", headers=headers).get_json()[0]["region_name"] == "Bochum"
    assert client.post("/api/scans", data={"image": (io.BytesIO(make_image()), "photo.png")}).status_code == 401


def test_dashboard_page_and_csv(client):
    client.post("/api/scans", data={"image": (io.BytesIO(make_image()), "photo.png")}, headers=login(client, "anna", "anna123"))
    client.post("/login", data={"username": "city", "password": "city123"})
    assert client.get("/dashboard").data.count(b"data:image/png;base64,iVBOR") == 4      # 4 charts
    csv = client.get("/dashboard/export.csv")
    assert csv.mimetype == "text/csv" and b"plastic" in csv.data


def test_form_input_is_kept_after_an_error(client):
    page = client.post("/register", data={"username": "anna", "password": "secret99", "region_name": "Essen"},
                       follow_redirects=True, headers={"Referer": "/register"})
    assert b"already taken" in page.data and b'value="anna"' in page.data
    assert b"secret99" not in page.data                             # passwords are never shown again


def test_address_lists_and_api_errors(client):
    assert client.get("/api/address/streets?q=Sonn").get_json() == ["Sonnenstr."]
    assert client.get("/api/address/numbers?street=Sonnenstr.").get_json() == ["94", "96", "96 a"]
    assert client.get("/api/nothing").get_json() == {"error": "page not found"}
