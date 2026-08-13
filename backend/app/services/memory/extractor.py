import logging
import json
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

from langchain_core.prompts import PromptTemplate
from backend.app.core.llm_factory import llm_factory

from backend.app.db.memory_handler import memory_handler
from backend.app.services.memory.graph_ltm import graph_ltm

logger = logging.getLogger("Extractor")

class InsightSchema(BaseModel):
    kind: str
    text: str
    entities: List[str]
    confidence: float
    evidence: str

class PrioritySchema(BaseModel):
    priority: str
    direction: str
    stated_or_behaved: str
    strength: float

class ContradictionSchema(BaseModel):
    said: str
    did_or_said_earlier: str
    severity: int

class EmotionSchema(BaseModel):
    overall: str
    notable_moments: List[str]

class ExtractionSchema(BaseModel):
    insights: List[InsightSchema]
    priority_signals: List[PrioritySchema]
    contradictions: List[ContradictionSchema]
    emotional_state: EmotionSchema
    open_loops: List[str]

async def _generate_embedding(text: str) -> List[float]:
    """Generates an embedding using the module-level cached SentenceTransformer."""
    try:
        from memory.embeddings import embed
        return await asyncio.to_thread(embed, text)
    except Exception as e:
        logger.error(f"[Extractor] Failed to generate embedding: {e}")
        return []

async def process_session_extraction(session_id: str):
    """
    1. Fetch the session transcript.
    2. Pass to LLM using session_extraction.md.
    3. Validate output with ExtractionSchema.
    4. Store in Mongo (insights collection).
    5. Pass to Graphiti L2.
    """
    from backend.app.db.database import db_manager
    if db_manager.db is None:
        logger.error("[Extractor] Database not connected.")
        return
        
    sessions = db_manager.db["sessions"]
    session = await sessions.find_one({"session_id": session_id})
    if not session:
        logger.error(f"[Extractor] Session {session_id} not found.")
        return
        
    if session.get("private") in ["no_extract", "no_trace"]:
        logger.info(f"[Extractor] Session {session_id} is private, skipping extraction.")
        return

    # Build transcript (support both turns[] and legacy messages[])
    turns = session.get("turns") or [
        {"role": m.get("role", "user"), "text": m.get("content", m.get("text", ""))}
        for m in session.get("messages", [])
    ]
    if not turns:
        logger.info(f"[Extractor] Session {session_id} has no turns, skipping.")
        return
        
    transcript = "\n".join([f"{t.get('role', 'user')}: {t.get('text', '')}" for t in turns])
    
    # Load prompt
    prompt_path = Path("prompts/session_extraction.md")
    if not prompt_path.exists():
        logger.error("[Extractor] Prompts file missing.")
        return
        
    with open(prompt_path, "r") as f:
        prompt_text = f.read()

    # In a real app we'd fetch priority weights dynamically
    weights = "DSA: 0.8, Jogging: 0.5" 
    
    prompt = PromptTemplate(
        template=prompt_text,
        input_variables=["transcript", "weights"],
        template_format="jinja2"
    )
    
    # Render the prompt
    formatted_prompt = prompt.format(transcript=transcript, weights=weights)
    
    try:
        # LLM extraction. Groq's structured-output calls have been observed to
        # return a fully-empty schema for a plainly extractable transcript on
        # ~2 of 3 identical calls even at temperature=0 -- an inference-layer
        # flakiness, not a prompt or determinism bug we can tune away. Retry a
        # couple of times before accepting an all-empty result as final.
        max_attempts = 3
        result = None
        for attempt in range(1, max_attempts + 1):
            llm = llm_factory.get_model("extraction")
            # Ensure we use structured output or simple json mode
            try:
                model = llm.with_structured_output(ExtractionSchema)
                result = await model.ainvoke(formatted_prompt)
            except Exception as structure_err:
                logger.warning(f"[Extractor] Structured output failed, falling back to JSON parser: {structure_err}")
                # Fallback for models without strict structured output (e.g. Groq llama3)
                raw_result = await llm.ainvoke(formatted_prompt)
                result_json = raw_result.content
                # Clean up markdown code blocks if present
                if "```json" in result_json:
                    result_json = result_json.split("```json")[1].split("```")[0].strip()
                result_dict = json.loads(result_json)
                result = ExtractionSchema(**result_dict)

            is_empty = not (
                result.insights or result.priority_signals
                or result.contradictions or result.open_loops
            )
            if not is_empty or attempt == max_attempts:
                if is_empty and attempt == max_attempts:
                    logger.warning(
                        f"[Extractor] All-empty extraction for session {session_id} "
                        f"after {max_attempts} attempts; accepting as final."
                    )
                break
            logger.warning(
                f"[Extractor] Empty extraction for session {session_id} on attempt "
                f"{attempt}/{max_attempts}; retrying."
            )

        # We got valid Pydantic extraction
        insights = result.insights
        
        graphiti_insights = []
        for insight in insights:
            # 1. Generate embedding
            emb = await _generate_embedding(insight.text)
            
            # 2. Store in Mongo `insights`
            await memory_handler.store_insight(
                session_id=session_id,
                kind=insight.kind,
                text=insight.text,
                entities=insight.entities,
                confidence=insight.confidence,
                embedding=emb,
                pinned=False
            )
            graphiti_insights.append(insight.text)
            
        # 3. Add to Graphiti L2
        if graph_ltm.is_initialized and graphiti_insights:
            combined_text = "\n".join(graphiti_insights)
            await graph_ltm.add_episode(session_id, combined_text)
            
        logger.info(f"[Extractor] Extracted {len(insights)} insights for session {session_id}.")
            
    except Exception as e:
        logger.error(f"[Extractor] Extraction failed: {e}")
        raise e
