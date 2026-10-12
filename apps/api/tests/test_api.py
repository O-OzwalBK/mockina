from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_read_root():
    """GET / answers with HTTP 200 and the body {"status": "healthy"}."""

    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
