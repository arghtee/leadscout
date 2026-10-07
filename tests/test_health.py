from fastapi.testclient import TestClient

from leadscout import __version__


def test_health_reports_ok_with_database(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__, "database": "ok"}
