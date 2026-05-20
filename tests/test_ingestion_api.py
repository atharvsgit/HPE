"""
tests/test_ingestion_api.py
===========================
Unit tests for the new ingestion orchestration routes.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ingestion.services.ingestion_service import PipelineResult, IngestionServiceError


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_pipeline_result():
    return PipelineResult(
        status="success",
        batch_id="batch_mock123",
        dataset_name="test_data",
        row_count=10,
        parquet_path="/tmp/data_lake/test_data/batch_mock123.parquet",
        profile_path="/tmp/data_lake/profiling/test_data_batch_mock123/latest/profile.json",
        contract_path="/tmp/data_lake/contracts/test_data/contract_v1.0.0.json",
        ready_for_validation=True,
        duplicate_count=0,
        execution_time_ms=100,
        stage_timings={}
    )


class TestUploadCSVRoute:
    def test_invalid_file_type(self, client):
        response = client.post(
            "/ingestion/datasets/upload/csv",
            params={"dataset_name": "test_data"},
            files={"file": ("test.txt", b"some content", "text/plain")}
        )
        assert response.status_code == 415
        assert "Invalid file format" in response.json()["detail"]

    @patch("app.api.ingestion_routes.run_in_threadpool")
    @patch("app.api.ingestion_routes.ValidationTriggerService.trigger_validation")
    def test_successful_upload(self, mock_trigger, mock_run, client, mock_pipeline_result):
        mock_run.return_value = mock_pipeline_result

        response = client.post(
            "/ingestion/datasets/upload/csv",
            params={"dataset_name": "test_data"},
            files={"file": ("data.csv", b"col1,col2\n1,2", "text/csv")}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["batch_id"] == "batch_mock123"
        assert data["row_count"] == 10
        assert data["ready_for_validation"] is True

    @patch("app.api.ingestion_routes.run_in_threadpool")
    def test_pipeline_error_returns_422(self, mock_run, client):
        mock_run.side_effect = IngestionServiceError(stage="csv_load", message="bad data")

        response = client.post(
            "/ingestion/datasets/upload/csv",
            params={"dataset_name": "test_data"},
            files={"file": ("data.csv", b"col1,col2\n1,2", "text/csv")}
        )

        assert response.status_code == 422
        assert "[stage=csv_load] bad data" in response.json()["detail"]

    @patch("app.api.ingestion_routes.run_in_threadpool")
    def test_unexpected_error_returns_500(self, mock_run, client):
        mock_run.side_effect = RuntimeError("System failure")

        response = client.post(
            "/ingestion/datasets/upload/csv",
            params={"dataset_name": "test_data"},
            files={"file": ("data.csv", b"col1,col2\n1,2", "text/csv")}
        )

        assert response.status_code == 500
        assert "System failure" in response.json()["detail"]


class TestProfileRoute:
    def test_profile_not_found(self, client):
        response = client.get("/ingestion/datasets/profile/nonexistent_dataset")
        assert response.status_code == 404
        assert "Profile not found" in response.json()["detail"]

    def test_get_profile_success(self, client, tmp_path, monkeypatch):
        # Mock PROFILING_DIR
        monkeypatch.setenv("PROFILING_DIR", str(tmp_path))
        
        # Create a fake profile
        profile_dir = tmp_path / "test_dataset_batch123" / "latest"
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_file = profile_dir / "profile.json"
        
        fake_profile = {"dataset_name": "test_dataset", "row_count": 100}
        with open(profile_file, "w") as f:
            json.dump(fake_profile, f)

        response = client.get("/ingestion/datasets/profile/test_dataset")
        assert response.status_code == 200
        assert response.json()["row_count"] == 100


class TestContractRoute:
    def test_contract_not_found(self, client):
        response = client.get("/ingestion/datasets/contracts/nonexistent_dataset")
        assert response.status_code == 404
        assert "Contract not found" in response.json()["detail"]

    def test_get_contract_success(self, client, tmp_path, monkeypatch):
        # Mock CONTRACTS_DIR
        monkeypatch.setenv("CONTRACTS_DIR", str(tmp_path))
        
        # Create a fake contract
        contract_dir = tmp_path / "test_dataset"
        contract_dir.mkdir(parents=True, exist_ok=True)
        contract_file = contract_dir / "contract_v1.0.0.json"
        
        fake_contract = {"dataset_name": "test_dataset", "version": "1.0.0"}
        with open(contract_file, "w") as f:
            json.dump(fake_contract, f)

        response = client.get("/ingestion/datasets/contracts/test_dataset")
        assert response.status_code == 200
        assert response.json()["version"] == "1.0.0"
