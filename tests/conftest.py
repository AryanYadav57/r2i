import pytest


@pytest.fixture(autouse=True)
def _no_real_api_keys(monkeypatch):
    """Tests never use keys from a developer's local .env."""
    for k in ("INFERENCE_CLOUD_API_KEY", "INFERENCE_CLOUD_ENDPOINT", "GOOGLE_MAPS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
