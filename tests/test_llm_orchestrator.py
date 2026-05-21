import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.llm.orchestrator import generate_batch_summary
from app.models.responses import AIEnrichment

class MockSettings:
    llm_enabled = False
    llm_model = "test-model"

@pytest.mark.asyncio
@patch("app.services.llm.orchestrator.get_settings")
async def test_generate_batch_summary_disabled(mock_get_settings):
    mock_get_settings.return_value = MockSettings()
    result = await generate_batch_summary(1)
    assert result is None

@pytest.mark.asyncio
@patch("app.services.llm.orchestrator.get_settings")
@patch("app.services.llm.orchestrator.get_existing_summary", new_callable=AsyncMock)
@patch("app.services.llm.orchestrator._fetch_batch_context", new_callable=AsyncMock)
@patch("app.services.llm.orchestrator.GroqProvider.generate_json", new_callable=AsyncMock)
@patch("app.services.llm.orchestrator._persist_summary", new_callable=AsyncMock)
@patch("app.services.llm.orchestrator._get_historical_human_correction", new_callable=AsyncMock)
async def test_generate_batch_summary_success(
    mock_historical, mock_persist, mock_generate, mock_fetch, mock_existing, mock_get_settings
):
    mock_settings = MockSettings()
    mock_settings.llm_enabled = True
    mock_get_settings.return_value = mock_settings
    
    mock_existing.return_value = None
    mock_fetch.return_value = {
        "batch_id": 1,
        "rule_id": 1,
        "rule_name": "Test Rule",
        "severity": "high",
        "violation_count": 10,
        "sample_rows": [{"id": 1}],
        "trend_summary": "Test trend"
    }
    mock_historical.return_value = None

    mock_generate.return_value = {
        "summary": "AI summary",
        "root_causes": ["cause 1"],
        "suggested_fixes": ["fix 1"],
        "business_impact": "impact",
        "confidence": "high",
    }
    
    result = await generate_batch_summary(1)
    
    assert result is not None
    assert isinstance(result, AIEnrichment)
    assert result.ai_summary == "AI summary"
    assert result.root_causes == ["cause 1"]
    assert result.suggested_fixes == ["fix 1"]
    mock_persist.assert_called_once()
