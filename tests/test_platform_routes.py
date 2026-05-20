"""
tests/test_platform_routes.py
-------------------------------
Integration tests for Platform Intelligence API endpoints.
Uses FastAPI's TestClient with mocked DB and platform functions
so no real PostgreSQL connection is required.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# =============================================================================
# Health check (smoke test that app starts with platform routes)
# =============================================================================

class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# =============================================================================
# Platform route availability (ensure routes are registered)
# =============================================================================

class TestPlatformRoutesRegistered:
    def test_openapi_includes_platform_pipeline(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/platform/pipeline/trigger" in paths

    def test_openapi_includes_platform_profile(self, client):
        response = client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/platform/profile" in paths

    def test_openapi_includes_platform_suggestions(self, client):
        response = client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/platform/suggestions" in paths

    def test_openapi_includes_anomaly_detect(self, client):
        response = client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/platform/anomaly/detect" in paths

    def test_openapi_includes_drift_detect(self, client):
        response = client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/platform/drift/detect" in paths


# =============================================================================
# Request model validation
# =============================================================================

class TestPlatformRequestValidation:
    def test_trigger_pipeline_rejects_empty_table_name(self, client):
        """table_name must not be empty."""
        response = client.post(
            "/platform/pipeline/trigger",
            json={"table_name": ""},
        )
        assert response.status_code == 422

    def test_profile_rejects_invalid_row_limit(self, client):
        """row_limit must be ≥ 1."""
        response = client.post(
            "/platform/profile",
            json={"table_name": "business_data.employees", "row_limit": 0},
        )
        assert response.status_code == 422

    def test_anomaly_detect_rejects_unknown_method(self, client):
        """method must be one of the three valid options."""
        response = client.post(
            "/platform/anomaly/detect",
            json={
                "table_name": "business_data.employees",
                "columns": ["salary"],
                "method": "magic_method",
            },
        )
        assert response.status_code == 422

    def test_drift_detect_rejects_empty_columns(self, client):
        """columns list must not be empty."""
        response = client.post(
            "/platform/drift/detect",
            json={
                "reference_table": "business_data.employees",
                "current_table": "business_data.students",
                "columns": [],
            },
        )
        assert response.status_code == 422

    def test_suggestions_rejects_invalid_backend(self, client):
        """backend must be 'heuristic' or 'gemini'."""
        response = client.post(
            "/platform/suggestions",
            json={"table_name": "t", "backend": "openai"},
        )
        assert response.status_code == 422
