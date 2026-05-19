import json
from pathlib import Path

import pytest
from app.ingestion.writers.success_marker import SuccessMarker, write_success_marker


def test_success_marker_creation(tmp_path):
    """Test generating standard _SUCCESS json files seamlessly."""
    batch_id = "batch_123"
    row_count = 1500
    
    result_path = write_success_marker(
        output_dir=tmp_path,
        batch_id=batch_id,
        row_count=row_count,
        schema_version="1.2.0"
    )
    
    assert result_path.exists()
    assert result_path.name == "_SUCCESS"
    
    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data["batch_id"] == batch_id
    assert data["row_count"] == row_count
    assert data["schema_version"] == "1.2.0"
    assert "completed_at" in data
    assert data["completed_at"].endswith("Z")


def test_success_marker_atomic_overwrite(tmp_path):
    """Test standard big-data behavior where overwrite of _SUCCESS indicates an updated partition state."""
    # Simulating first batch process pipeline finishing
    write_success_marker(tmp_path, "batch_1", 10)
    
    # Overwriting pipeline finishing right after explicitly overriding 
    write_success_marker(tmp_path, "batch_2", 20)
    
    success_file = tmp_path / "_SUCCESS"
    assert success_file.exists()
    
    # All transient .tmp variants MUST be atomically eliminated post-swaps
    temp_files = list(tmp_path.glob("*.tmp"))
    assert len(temp_files) == 0
    
    with open(success_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["batch_id"] == "batch_2"
        assert data["row_count"] == 20
