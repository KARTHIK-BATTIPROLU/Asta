"""
ASTA Awake Verification — multi-turn morning state machine.

Handles the morning alarm trigger:
- Manages snooze negotiation.
- Requires 2 coherent conversational turns to verify user is awake.
- Escalates if ignored.
"""

import time
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger("AwakeVerification")

VERIFICATION_TTL_SECONDS = 600  # Drop state after 10 mins

@dataclass
class AwakeState:
    session_id: str
    turn_count: int = 0
    snoozes_taken: int = 0
    is_awake: bool = False
    lat: Optional[float] = None
    lon: Optional[float] = None
    last_activity: float = field(default_factory=time.time)

    def touch(self):
        self.last_activity = time.time()

    def is_stale(self) -> bool:
        return (time.time() - self.last_activity) > VERIFICATION_TTL_SECONDS


_verification_state: Dict[str, AwakeState] = {}

def _drop_stale():
    for sid in list(_verification_state.keys()):
        if _verification_state[sid].is_stale():
            logger.info(f"[AwakeVerification] Dropping stale state for {sid[:8]}")
            del _verification_state[sid]

def has_active_verification(session_id: str) -> bool:
    _drop_stale()
    return session_id in _verification_state and not _verification_state[session_id].is_awake

def is_snooze_request(transcript: str) -> bool:
    text = transcript.lower()
    snooze_patterns = [
        r"snooze",
        r"\d+\s*(more\s*)?min(ute)?s?",
        r"five more",
        r"ten more",
        r"let me sleep",
        r"not now",
        r"tired"
    ]
    for pattern in snooze_patterns:
        if re.search(pattern, text):
            return True
    return False

def is_coherent_response(transcript: str) -> bool:
    # Basic heuristic: > 2 words is considered coherent
    words = [w for w in transcript.split() if w.strip()]
    if len(words) > 2:
        return True
    return False

async def start_verification(session_id: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, Any]:
    _drop_stale()
    st = AwakeState(session_id=session_id, lat=lat, lon=lon)
    _verification_state[session_id] = st
    st.touch()
    return {
        "status": "verifying",
        "prompt": "Good morning boss! I hope you slept well. It's time to get up. Are you awake?"
    }

async def advance_verification(session_id: str, transcript: str) -> Dict[str, Any]:
    _drop_stale()
    st = _verification_state.get(session_id)
    
    if not st:
        # If no active state, maybe it expired.
        return {"status": "error", "prompt": "Awake verification expired."}
    
    st.touch()
    
    # Check for snooze request first
    if is_snooze_request(transcript):
        if st.snoozes_taken == 0:
            st.snoozes_taken += 1
            # Reschedule local alarm via WS action
            return {
                "status": "snoozing",
                "prompt": "Alright, 10 more minutes. But this is your only snooze. I'll wake you up again shortly.",
                "action": "set_snooze",
                "minutes": 10
            }
        else:
            return {
                "status": "verifying",
                "prompt": "No way boss. You already had your snooze. You asked me to be strict. Time to get out of bed."
            }

    # Evaluate coherency
    if is_coherent_response(transcript):
        st.turn_count += 1
        
        if st.turn_count >= 2:
            st.is_awake = True
            lat_out = st.lat
            lon_out = st.lon
            _verification_state.pop(session_id, None)
            
            # Log exact wake time to L4 (Neo4j)
            try:
                from backend.app.core.registry import registry
                db = registry.get("db")
                if db and hasattr(db, "neo4j_driver"):
                    import asyncio
                    
                    async def log_wake():
                        async with db.neo4j_driver.session() as session:
                            await session.run(
                                "MATCH (u:Identity {name: 'KARTHIK'}) "
                                "CREATE (w:WakeEvent {timestamp: datetime(), method: 'voice_verification'}) "
                                "CREATE (u)-[:WOKE_UP]->(w)"
                            )
                    asyncio.create_task(log_wake())
            except Exception as e:
                logger.error(f"[AwakeVerification] Failed to log wake event to Neo4j: {e}")
            
            logger.info(f"[AwakeVerification] User verified awake for session {session_id}")
            
            return {
                "status": "awake",
                "prompt": "Awesome. Glad you're up. Give me one second while I pull up your morning briefing...",
                "action": "run_briefing",
                "lat": lat_out,
                "lon": lon_out
            }
        else:
            return {
                "status": "verifying",
                "prompt": "I hear you, but you still sound a bit sleepy. Tell me, what's the first thing on your mind today?"
            }
    else:
        return {
            "status": "verifying",
            "prompt": "Come on, give me a real sentence so I know you're not sleep-talking!"
        }
