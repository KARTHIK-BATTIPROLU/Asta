"""
ASTA Memory Layer - Entity Extractor
──────────────────────────────────

This module uses an LLM to extract typed entities from a conversation.
Called at session end, BEFORE saving to Neo4j/Pinecone.
"""

import json
import logging
from typing import List, Dict
from backend.app.core.llm_factory import acomplete
from memory.schema import Entity, ENTITY_TYPES

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are extracting structured information from a conversation transcript.

Extract all entities mentioned. An entity is:
- PROJECT: A specific project mentioned (e.g. "ASTA", "Metaverse app", "portfolio website")
- SKILL: A technical or personal skill (e.g. "Python", "DSA", "LangGraph", "public speaking")
- PERSON: A specific person mentioned (e.g. "Ravi", "my CTO", "professor")
- GOAL: A goal or aspiration mentioned (e.g. "grow community to 1000", "learn system design")
- TOPIC: A knowledge topic discussed (e.g. "transformer architecture", "Neo4j queries", "AI agents")
- DECISION: A decision made during the conversation (e.g. "decided to use Redis for caching")
- TASK: A specific task or action item (e.g. "implement the research graph", "call Ravi tomorrow")

Rules:
- Only extract entities that are CLEARLY mentioned, not implied
- For each entity, write a 1-sentence description based on how it was used in the conversation
- If unsure of type, use TOPIC
- Return ONLY valid JSON, no other text

Return format:
{
  "entities": [
    {"name": "ASTA", "entity_type": "PROJECT", "description": "Personal AI assistant being built by Karthik", "relation_to_user": "WORKING_ON", "confidence": 0.95},
    ...
  ],
  "summary": "3-5 bullet points summarizing the key points of this conversation",
  "primary_topic": "The single most important topic of this conversation"
}"""

class EntityExtractor:
    """
    LLM-based entity extraction from conversation transcripts.

    Routed through llm_factory (Groq primary, Gemini fallback) so a Groq
    rate-limit doesn't silently degrade every session summary to a
    placeholder string.
    """

    async def extract(self, messages: List[Dict], workflow_type: str) -> Dict:
        """
        Extract entities, summary, and primary topic from conversation.
        
        Args:
            messages: List of dicts {"role": "user"/"assistant", "content": str}
            workflow_type: Type of workflow (research, routine, etc.)
            
        Returns:
            Dict with "entities" (list of Entity objects), "summary" (str), "primary_topic" (str)
        """
        try:
            # Build transcript text - cap at 6000 chars to avoid token waste
            transcript = ""
            for m in messages:
                role = m.get("role", "unknown")
                content = str(m.get("content", ""))[:500]  # Cap each turn
                transcript += f"{role.upper()}: {content}\n"
            
            transcript = transcript[:6000]
            
            # Build full prompt
            full_prompt = f"{EXTRACTION_PROMPT}\n\nWorkflow type: {workflow_type}\n\nTranscript:\n{transcript}"
            
            # Call LLM (Groq primary, Gemini fallback via llm_factory)
            raw = (await acomplete("", full_prompt, task="generate", temperature=0.1, max_tokens=1500)).strip()
            
            # Clean JSON fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            
            # Parse JSON response
            parsed = json.loads(raw)
            
            # Convert entity dicts to Entity objects
            entities = []
            for e in parsed.get("entities", []):
                if e.get("name") and e.get("entity_type") in ENTITY_TYPES:
                    
                    # Sanitize relation string for Neo4j (uppercase, underscores only)
                    raw_rel = e.get("relation_to_user", "HAS")
                    clean_rel = "".join(c for c in raw_rel.upper() if c.isalnum() or c == "_")
                    if not clean_rel:
                        clean_rel = "HAS"
                        
                    entities.append(Entity(
                        name=e["name"],
                        entity_type=e.get("entity_type", "TOPIC"),
                        description=e.get("description", ""),
                        relation_to_user=clean_rel,
                        confidence=e.get("confidence", 0.8)
                    ))
            
            result = {
                "entities": entities,
                "summary": " ".join(parsed.get("summary", ["No summary generated."])) if isinstance(parsed.get("summary"), list) else parsed.get("summary", "No summary generated."),
                "primary_topic": parsed.get("primary_topic", "")
            }
            
            logger.info(f"Extracted {len(entities)} entities from {workflow_type} session")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Entity extraction JSON parse failed: {e}")
            return {
                "entities": [],
                "summary": "Extraction failed - JSON parse error.",
                "primary_topic": ""
            }
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {
                "entities": [],
                "summary": "Extraction failed - unknown error.",
                "primary_topic": ""
            }
    
    def spot_entities_in_text(self, text: str, known_entities: List[str]) -> List[str]:
        """
        Fast check: which known entities are mentioned in this text?
        Used by the prefetch engine mid-session.
        
        Does NOT call LLM - just does case-insensitive string matching.
        
        Args:
            text: Text to search in
            known_entities: List of known entity names
            
        Returns:
            List of matched entity names
        """
        try:
            # Guard against None/empty inputs
            if not text or not known_entities:
                return []
            
            text_lower = text.lower()
            matched = []
            
            for entity in known_entities:
                if entity and entity.lower() in text_lower:
                    matched.append(entity)
            
            return matched
            
        except Exception as e:
            logger.error(f"Failed to spot entities in text: {e}")
            return []

# Export singleton
entity_extractor = EntityExtractor()