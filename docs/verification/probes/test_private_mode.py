import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.app.services.memory.extractor import process_session_extraction

@pytest.mark.asyncio
async def test_private_mode_no_extraction():
    # Verify that a session marked private skips extraction entirely
    
    with patch("backend.app.db.database.db_manager") as mock_db:
        mock_db.db.__getitem__.return_value.find_one = AsyncMock(return_value={
            "session_id": "secret_session",
            "private": "no_trace",
            "turns": [
                {"role": "user", "text": "This is a secret."},
                {"role": "asta", "text": "I will not remember this."}
            ]
        })
        
        with patch("backend.app.services.memory.extractor.llm_factory.get_model") as mock_get_model:
            with patch("backend.app.services.memory.extractor.memory_handler.store_insight", new_callable=AsyncMock) as mock_store:
                
                await process_session_extraction(session_id="secret_session")
                
                # Should NOT have called the LLM to extract
                mock_get_model.assert_not_called()
                
                # Should NOT have tried to store insights
                mock_store.assert_not_called()
