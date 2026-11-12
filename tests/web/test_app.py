from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ankinote import __version__
from ankinote.web.app import create_app


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=app></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return tmp_path


def test_health_reports_version(dist: Path) -> None:
    client = TestClient(create_app(dist))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_unknown_api_path_is_json_404_not_the_spa(dist: Path) -> None:
    client = TestClient(create_app(dist))

    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/", "/wizard", "/generate/word"])
def test_client_routes_serve_index(dist: Path, path: str) -> None:
    client = TestClient(create_app(dist))

    response = client.get(path)

    assert response.status_code == 200
    assert "<div id=app>" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_built_assets_are_served(dist: Path) -> None:
    client = TestClient(create_app(dist))

    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log(1)"


def test_missing_asset_is_404_not_index(dist: Path) -> None:
    client = TestClient(create_app(dist))

    assert client.get("/assets/missing.js").status_code == 404


def test_missing_build_explains_how_to_build(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "absent"))

    response = client.get("/")

    assert response.status_code == 503
    assert "make web-build" in response.text
