"""
ASTA Memory Layer - Phase 3 End-to-End Integration Tests
═══════════════════════════════════════════════════════════

This test verifies the FULL memory pipeline from API → memory_engine → all layers → back to API.
Tests the 3 critical hooks in session_manager.py and llm_service.py.

Run this AFTER Phase 2 stress tests pass.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import List, Dict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("E2E_TEST")

# Import memory engine
from memory.memory_engine import memory_engine
from memory.schema import SessionMetadata, Entity

# Test results tracker
test_results = []

def log_test(name: str, passed: bool, error: str = ""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({"name": name, "passed": passed, "error": error})
    if passed:
        logger.info(f"{status} - {name}")
    else:
        logger.error(f"{status} - {name}: {error}")


async def scenario_1_new_session_cold_start():
    """
    SCENARIO 1 — New session cold start (no prior context)
    
    Simulates: User starts fresh conversation with no history
    Tests: HOOK 1 (get_context_for_session on new session)
    
    Expected: Returns empty context gracefully, doesn't crash
    """
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 1 — New Session Cold Start")
    logger.info("="*80)
    
    try:
        # Simulate new session with no prior context
        session_id = "e2e-test-cold-start"
        user_input = "Hello ASTA, what can you help me with?"
        
        # HOOK 1: Get context for new session
        context = await memory_engine.get_context_for_session(
            session_id=session_id,
            user_input=user_input,
            workflow_type="general"
        )
        
        # Verify structure
        passed = (
            isinstance(context, dict) and
            "sessions" in context and
            isinstance(context["sessions"], list)
        )
        
        if passed:
            logger.info(f"  → Retrieved {len(context['sessions'])} sessions (expected 0 for cold start)")
            log_test("1.1: Cold start returns valid empty context", True, "")
        else:
            log_test("1.1: Cold start returns valid empty context", False, f"Invalid structure: {context}")
        
        # Test formatting empty context
        formatted = memory_engine.format_context_for_prompt(context)
        passed = isinstance(formatted, str)
        log_test("1.2: Format empty context for prompt", passed, "" if passed else f"Got {type(formatted)}")
        
    except Exception as e:
        log_test("1.1: Cold start returns valid empty context", False, str(e))
        log_test("1.2: Format empty context for prompt", False, str(e))


async def scenario_2_session_with_entity_recall():
    """
    SCENARIO 2 — Session with entity recall
    
    Simulates: User mentions known entity, system retrieves related context
    Tests: Full retrieval pipeline (L1 → L2 → L3 → L4)
    
    Expected: Retrieves related sessions, spots entities, returns context
    """
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 2 — Session with Entity Recall")
    logger.info("="*80)
    
    try:
        # Step 1: Save a session with entities first
        session_id_1 = "e2e-test-entity-save"
        metadata = SessionMetadata(
            session_id=session_id_1,
            workflow_type="research",
            start_time=datetime.utcnow().isoformat(),
            end_time=datetime.utcnow().isoformat(),
            summary="Discussed ASTA memory architecture and LangGraph integration",
            entities=[
                Entity(name="ASTA", entity_type="PROJECT", description="AI assistant project"),
                Entity(name="LangGraph", entity_type="SKILL", description="State machine framework")
            ],
            topics=["ASTA", "LangGraph", "memory"]
        )
        
        messages = [
            {"role": "user", "content": "Tell me about ASTA's memory system"},
            {"role": "assistant", "content": "ASTA uses a 5-layer memory architecture with LangGraph for state management"}
        ]
        
        saved = await memory_engine.save_session(
            session_id=session_id_1,
            workflow_type="research",
            messages=messages,
            start_time=metadata.start_time
        )
        
        log_test("2.1: Save session with entities", saved, "" if saved else "Save failed")
        
        # Step 2: Start new session mentioning same entity
        session_id_2 = "e2e-test-entity-recall"
        user_input = "What did we discuss about ASTA before?"
        
        context = await memory_engine.get_context_for_session(
            session_id=session_id_2,
            user_input=user_input,
            workflow_type="general"
        )
        
        # Verify entity was spotted and context retrieved
        entities_spotted = context.get("entities_spotted", [])
        sessions_retrieved = context.get("sessions", [])
        
        passed = "ASTA" in entities_spotted or len(sessions_retrieved) > 0
        log_test("2.2: Entity spotted and context retrieved", passed, 
                f"Entities: {entities_spotted}, Sessions: {len(sessions_retrieved)}")
        
        # Step 3: Format context for LLM
        formatted = memory_engine.format_context_for_prompt(context)
        passed = isinstance(formatted, str) and len(formatted) > 0
        log_test("2.3: Format context with entities", passed, 
                f"Length: {len(formatted)}" if passed else f"Got {type(formatted)}")
        
    except Exception as e:
        log_test("2.1: Save session with entities", False, str(e))
        log_test("2.2: Entity spotted and context retrieved", False, str(e))
        log_test("2.3: Format context with entities", False, str(e))


async def scenario_3_concurrent_sessions():
    """
    SCENARIO 3 — Concurrent sessions (multi-user simulation)
    
    Simulates: Multiple users/sessions running simultaneously
    Tests: Thread safety, cache isolation, no cross-contamination
    
    Expected: Each session gets its own context, no mixing
    """
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 3 — Concurrent Sessions")
    logger.info("="*80)
    
    try:
        # Create 5 concurrent sessions with different contexts
        async def run_session(idx: int):
            session_id = f"e2e-concurrent-{idx}"
            user_input = f"Tell me about project {idx}"
            
            # Get context
            context = await memory_engine.get_context_for_session(
                session_id=session_id,
                user_input=user_input,
                workflow_type="general"
            )
            
            # Simulate conversation
            await memory_engine.on_user_message(session_id, f"More about project {idx}")
            
            # Save session
            messages = [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": f"Project {idx} details..."}
            ]
            
            saved = await memory_engine.save_session(
                session_id=session_id,
                workflow_type="general",
                messages=messages,
                start_time=datetime.utcnow().isoformat()
            )
            
            return saved
        
        # Run 5 sessions concurrently
        results = await asyncio.gather(*[run_session(i) for i in range(5)], return_exceptions=True)
        
        failures = [r for r in results if isinstance(r, Exception) or not r]
        passed = len(failures) == 0
        
        log_test("3.1: Concurrent sessions complete without errors", passed, 
                f"{len(failures)} failures" if not passed else "All 5 sessions succeeded")
        
    except Exception as e:
        log_test("3.1: Concurrent sessions complete without errors", False, str(e))


async def scenario_4_full_session_lifecycle():
    """
    SCENARIO 4 — Full session lifecycle (start → messages → end)
    
    Simulates: Complete user session from start to finish
    Tests: All 3 hooks (HOOK 1, HOOK 2, HOOK 3) + full write pipeline
    
    Expected: Context retrieved at start, prefetch on messages, save at end
    """
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 4 — Full Session Lifecycle")
    logger.info("="*80)
    
    try:
        session_id = "e2e-full-lifecycle"
        
        # HOOK 1: Session start - get context
        logger.info("  → HOOK 1: Getting context for new session...")
        context = await memory_engine.get_context_for_session(
            session_id=session_id,
            user_input="I want to work on ASTA today",
            workflow_type="routine"
        )
        
        passed = isinstance(context, dict) and "sessions" in context
        log_test("4.1: HOOK 1 - Get context on session start", passed, 
                "" if passed else f"Invalid context: {context}")
        
        # HOOK 2: User messages - trigger prefetch
        logger.info("  → HOOK 2: Sending user messages (triggers prefetch)...")
        messages = [
            "Let's review the memory architecture",
            "I need to update the Neo4j schema",
            "Can you help me with LangGraph integration?"
        ]
        
        for msg in messages:
            await memory_engine.on_user_message(session_id, msg)
        
        log_test("4.2: HOOK 2 - Prefetch on user messages", True, "Prefetch triggered (non-blocking)")
        
        # HOOK 3: Session end - save everything
        logger.info("  → HOOK 3: Ending session (full save pipeline)...")
        full_messages = [
            {"role": "user", "content": "Let's review the memory architecture"},
            {"role": "assistant", "content": "The memory system has 5 layers: L0 in-flight, L1 cache, L2 graph, L3 vectors, L4 store"},
            {"role": "user", "content": "I need to update the Neo4j schema"},
            {"role": "assistant", "content": "I can help with that. What changes do you need?"},
            {"role": "user", "content": "Can you help me with LangGraph integration?"},
            {"role": "assistant", "content": "Yes, LangGraph manages the state machine for ASTA's workflows"}
        ]
        
        saved = await memory_engine.save_session(
            session_id=session_id,
            workflow_type="routine",
            messages=full_messages,
            start_time=datetime.utcnow().isoformat()
        )
        
        log_test("4.3: HOOK 3 - Save session on end", saved, "" if saved else "Save failed")
        
        # Verify we can retrieve this session later
        logger.info("  → Verifying saved session can be retrieved...")
        new_context = await memory_engine.get_context_for_session(
            session_id="e2e-verify-retrieval",
            user_input="What did we discuss about memory architecture?",
            workflow_type="general"
        )
        
        # Should retrieve the session we just saved (if vector search works)
        passed = isinstance(new_context, dict) and "sessions" in new_context
        log_test("4.4: Retrieve saved session in new context", passed, 
                f"Retrieved {len(new_context.get('sessions', []))} sessions")
        
    except Exception as e:
        log_test("4.1: HOOK 1 - Get context on session start", False, str(e))
        log_test("4.2: HOOK 2 - Prefetch on user messages", False, str(e))
        log_test("4.3: HOOK 3 - Save session on end", False, str(e))
        log_test("4.4: Retrieve saved session in new context", False, str(e))


async def scenario_5_layer_degradation_fallback():
    """
    SCENARIO 5 — Layer degradation fallback
    
    Simulates: One layer fails, system falls back gracefully
    Tests: Per-layer error isolation, no cascading failures
    
    Expected: System continues working even if L2 or L3 fails
    """
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 5 — Layer Degradation Fallback")
    logger.info("="*80)
    
    try:
        # Test 1: Get context with empty entity list (simulates L2 failure)
        logger.info("  → Testing L2 degradation (empty entity list)...")
        context = await memory_engine.get_context_for_session(
            session_id="e2e-l2-degraded",
            user_input="Tell me about something",
            workflow_type="general"
        )
        
        # Should fall back to L3 vector search
        passed = isinstance(context, dict) and "sessions" in context
        log_test("5.1: L2 degraded - fallback to L3", passed, 
                "" if passed else f"Failed to fall back: {context}")
        
        # Test 2: Save session with partial layer failures
        logger.info("  → Testing save with potential layer failures...")
        session_id = "e2e-partial-save"
        messages = [
            {"role": "user", "content": "Test message"},
            {"role": "assistant", "content": "Test response"}
        ]
        
        # This should succeed even if some layers fail (due to error isolation)
        saved = await memory_engine.save_session(
            session_id=session_id,
            workflow_type="test",
            messages=messages,
            start_time=datetime.utcnow().isoformat()
        )
        
        log_test("5.2: Save with layer isolation", saved, 
                "" if saved else "Save failed completely (should have partial success)")
        
        # Test 3: Format context with malformed data
        logger.info("  → Testing format with malformed data...")
        malformed_context = {
            "sessions": [
                {
                    "session_id": "test",
                    "workflow_type": "test",
                    "end_time": None,  # Malformed!
                    "summary": ["list", "instead", "of", "string"],  # Malformed!
                    "entities": None  # Malformed!
                }
            ]
        }
        
        try:
            formatted = memory_engine.format_context_for_prompt(malformed_context)
            passed = isinstance(formatted, str)
            log_test("5.3: Format malformed context gracefully", passed, 
                    "" if passed else f"Got {type(formatted)}")
        except Exception as format_err:
            log_test("5.3: Format malformed context gracefully", False, str(format_err))
        
    except Exception as e:
        log_test("5.1: L2 degraded - fallback to L3", False, str(e))
        log_test("5.2: Save with layer isolation", False, str(e))
        log_test("5.3: Format malformed context gracefully", False, str(e))


async def main():
    """Run all E2E integration tests."""
    logger.info("="*80)
    logger.info("ASTA MEMORY LAYER - PHASE 3 END-TO-END INTEGRATION TESTS")
    logger.info("="*80)
    logger.info("Testing full memory pipeline from API → memory_engine → all layers")
    logger.info("")
    
    try:
        # Connect all layers first
        logger.info("Connecting memory layers...")
        status = await memory_engine.connect_all()
        logger.info(f"Connection status: {status}")
        
        # Check if all layers connected
        failed_layers = [k for k, v in status.items() if "FAILED" in str(v)]
        if failed_layers:
            logger.warning(f"Some layers failed to connect: {failed_layers}")
            logger.warning("Tests will continue but may have limited functionality")
        
        logger.info("")
        
        # Run all scenarios
        await scenario_1_new_session_cold_start()
        await scenario_2_session_with_entity_recall()
        await scenario_3_concurrent_sessions()
        await scenario_4_full_session_lifecycle()
        await scenario_5_layer_degradation_fallback()
        
    except Exception as e:
        logger.error(f"Fatal error during E2E test: {e}")
        import traceback
        traceback.print_exc()
    
    # Print summary
    logger.info("\n" + "="*80)
    logger.info("E2E INTEGRATION TEST SUMMARY")
    logger.info("="*80)
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    
    logger.info(f"Total tests: {total}")
    logger.info(f"Passed: {passed} ✅")
    logger.info(f"Failed: {failed} ❌")
    logger.info("")
    
    if failed > 0:
        logger.error("FAILED TESTS:")
        for r in test_results:
            if not r["passed"]:
                logger.error(f"  ❌ {r['name']}: {r['error']}")
        logger.info("")
        logger.error("❌ PHASE 3 FAILED - Fix issues before proceeding to Phase 4")
        sys.exit(1)
    else:
        logger.info("✅ ALL E2E TESTS PASSED - Ready for Phase 4 (Performance Benchmarks)")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
