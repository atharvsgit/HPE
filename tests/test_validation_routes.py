from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _trigger_payload(**overrides):
    payload = {
        "dataset_name": "uploaded_employees",
        "batch_id": "batch_123",
        "parquet_path": "/tmp/data_lake/uploaded_employees/batch_123.parquet",
        "profile_path": "/tmp/data_lake/profiling/uploaded_employees/profile.json",
    }
    payload.update(overrides)
    return payload


def test_validation_trigger_acknowledges_without_table_mapping(client):
    with (
        patch(
            "app.api.validation_routes.create_pipeline_run",
            new_callable=AsyncMock,
        ) as mock_create_run,
        patch(
            "app.api.validation_routes.run_full_pipeline",
            new_callable=AsyncMock,
        ) as mock_run_flow,
    ):
        response = client.post(
            "/api/v1/validation/trigger",
            json=_trigger_payload(),
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ACKNOWLEDGED"
    assert data["dataset_name"] == "uploaded_employees"
    assert data["batch_id"] == "batch_123"
    assert data["run_id"] is None
    assert data["table_name"] is None
    assert "no PostgreSQL table mapping" in data["message"]
    mock_create_run.assert_not_called()
    mock_run_flow.assert_not_called()


def test_validation_trigger_starts_pipeline_for_explicit_table(client):
    with (
        patch(
            "app.api.validation_routes.create_pipeline_run",
            new_callable=AsyncMock,
            return_value=42,
        ) as mock_create_run,
        patch(
            "app.api.validation_routes.run_full_pipeline",
            new_callable=AsyncMock,
        ) as mock_run_flow,
    ):
        response = client.post(
            "/api/v1/validation/trigger",
            json=_trigger_payload(table_name="business_data.employees"),
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "TRIGGERED"
    assert data["run_id"] == 42
    assert data["table_name"] == "business_data.employees"

    mock_create_run.assert_awaited_once()
    args, kwargs = mock_create_run.await_args
    assert args == ("business_data.employees",)
    assert kwargs["metadata"]["trigger"] == "ingestion"
    assert kwargs["metadata"]["batch_id"] == "batch_123"
    assert kwargs["metadata"]["parquet_path"].endswith("batch_123.parquet")
    mock_run_flow.assert_awaited_once_with(
        table_name="business_data.employees",
        run_id=42,
    )


def test_validation_trigger_infers_schema_qualified_dataset_as_table(client):
    with (
        patch(
            "app.api.validation_routes.create_pipeline_run",
            new_callable=AsyncMock,
            return_value=7,
        ) as mock_create_run,
        patch(
            "app.api.validation_routes.run_full_pipeline",
            new_callable=AsyncMock,
        ) as mock_run_flow,
    ):
        response = client.post(
            "/api/v1/validation/trigger",
            json=_trigger_payload(dataset_name="business_data.employees"),
        )

    assert response.status_code == 202
    assert response.json()["table_name"] == "business_data.employees"
    mock_create_run.assert_awaited_once()
    mock_run_flow.assert_awaited_once_with(
        table_name="business_data.employees",
        run_id=7,
    )
