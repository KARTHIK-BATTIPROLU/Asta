import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.services.memory.extractor import process_session_extraction, ExtractionSchema, InsightSchema, EmotionSchema

@pytest.mark.asyncio
async def test_step_3_extraction():
    # Step 3: session ends -> extraction runs -> schema-valid insights produced
    
    # Mock db_manager to return a fake transcript
    with patch("backend.app.db.database.db_manager") as mock_db:
        mock_db.db.__getitem__.return_value.find_one = AsyncMock(return_value={
            "session_id": "test_session",
            "turns": [
                {"role": "user", "text": "I really love learning about quantum physics."},
                {"role": "asta", "text": "That is fascinating."},
            ]
        })
        
        # Mock the LLM to avoid real network call to Groq
        with patch("backend.app.services.memory.extractor.llm_factory.get_model") as mock_get_model:
            mock_llm = MagicMock()
            mock_structured_llm = AsyncMock()
            
            mock_llm.with_structured_output.return_value = mock_structured_llm
            
            # Return a valid schema instance directly
            mock_structured_llm.ainvoke.return_value = ExtractionSchema(
                insights=[
                    InsightSchema(
                        text="User loves quantum physics",
                        kind="preference",
                        entities=["quantum physics"],
                        confidence=0.9,
                        evidence="I really love learning about quantum physics."
                    )
                ],
                priority_signals=[],
                contradictions=[],
                emotional_state=EmotionSchema(overall="curious", notable_moments=[]),
                open_loops=[]
            )
            
            mock_get_model.return_value = mock_llm
            
            # Mock generate_embedding, graph_ltm, memory_handler
            with patch("backend.app.services.memory.extractor._generate_embedding", new_callable=AsyncMock) as mock_embed:
                mock_embed.return_value = [0.1]*1536
                with patch("backend.app.services.memory.extractor.graph_ltm.add_episode", new_callable=AsyncMock) as mock_store_graph:
                    with patch("backend.app.services.memory.extractor.memory_handler.store_insight", new_callable=AsyncMock) as mock_store_mongo:
                        
                        # Setup graph_ltm state
                        from backend.app.services.memory.extractor import graph_ltm
                        graph_ltm.is_initialized = True
                        
                        # Run the extraction
                        await process_session_extraction(session_id="test_session")
                        
                        # Ensure it tried to store them
                        mock_store_mongo.assert_called_once()
                        mock_store_graph.assert_called_once()
                        
                        # Verify the passed data
                        args, kwargs = mock_store_mongo.call_args
                        assert kwargs["text"] == "User loves quantum physics"
                        assert kwargs["kind"] == "preference"
