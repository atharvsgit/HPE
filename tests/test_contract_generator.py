import json
import polars as pl
from app.ingestion.contracts.contract_generator import ContractGenerator, run_contract_generator

def test_contract_generation_structure():
    schema = {"id": pl.Int64, "name": pl.Utf8, "revenue": pl.Float64}
    
    profiling_metadata = {
        "columns": {
            "id": {"null_percentage": 0.0, "min": 1, "max": 100},
            "name": {"null_percentage": 10.0},
            "revenue": {"null_percentage": 0.0, "min": 5.0, "max": 50.0}
        }
    }
    
    generator = ContractGenerator()
    contract = generator.generate(
        dataset_name="test_dataset",
        schema=schema,
        profiling_metadata=profiling_metadata,
        version="2.0.0",
        incremental_strategy="upsert",
        watermark_column="id"
    )
    
    # Check basics
    assert contract["dataset_name"] == "test_dataset"
    assert contract["version"] == "2.0.0"
    assert contract["incremental_configuration"]["strategy"] == "upsert"
    assert contract["incremental_configuration"]["watermark_column"] == "id"
    assert contract["access_paths"]["parquet"] == "/data/lake/test_dataset/"
    
    # Check schema serialization
    fields = contract["schema"]["fields"]
    assert len(fields) == 3
    
    id_field = next(f for f in fields if f["name"] == "id")
    assert id_field["logical_type"] == "Int64"
    assert not id_field["nullable"]  # null_percentage = 0.0
    
    name_field = next(f for f in fields if f["name"] == "name")
    assert name_field["nullable"]  # null_percentage = 10.0
    
    # Check baselines
    baselines = contract["quality_baselines"]
    assert baselines["id"]["observed_min"] == 1
    assert baselines["id"]["observed_max"] == 100
    assert baselines["id"]["max_null_percentage_allowed"] == 5.0
    assert baselines["name"]["max_null_percentage_allowed"] == 10.0


def test_contract_save(tmp_path):
    schema = {"uid": pl.String}
    profile = {"columns": {"uid": {"null_percentage": 0.0}}}
    
    contract = run_contract_generator(
        dataset_name="metrics_t",
        schema=schema,
        profiling_metadata=profile,
        output_base_dir=str(tmp_path)
    )
    
    # Output File Verification
    expected_path = tmp_path / "metrics_t" / f"contract_v{contract['version']}.json"
    assert expected_path.exists()
    
    with open(expected_path, "r") as f:
        data = json.load(f)
        assert data["dataset_name"] == "metrics_t"
        assert data["schema"]["fields"][0]["name"] == "uid"
