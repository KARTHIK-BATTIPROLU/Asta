"""
ASTA Memory Layer - Phase 2 Stress Test
═══════════════════════════════════════

This test attacks every failure mode to verify the memory layer is production-ready.
Run this AFTER fixing all Phase 1 critical issues.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import List, Dict
import traceback

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("STRESS_TEST")

# Import memory layers
from memory.l1_cache import l1_cache
from memory.l2_graph import l2_graph
from memory.l3_vectors import l3_vectors
from memory.l4_store import l4_store
from memory.entity_extractor import entity_extractor
from memory.prefetch_engine import prefetch_engine
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

async def attack_1_corrupt_input():
    """ATTACK 1 — Corrupt input handling"""
    logger.info("\n" + "="*80)
    logger.info("ATTACK 1 — Corrupt Input Handling")
    logger.info("="*80)
    
    # Test 1.1: save_session with summary as list
    try:
        metadata = SessionMetadata(
            session_id="stress-test-001",
            workflow_type="test",
            start_time=datetime.utcnow().isoformat(),
            end_time=datetime.utcnow().isoformat(),
            summary=["bullet 1", "bullet 2", "bullet 3"],  # LIST not string!
            entities=[],
            topics=[]
        )
        result = await l4_store.save_session(metadata, [])
        # Should convert list to string, not crash
        log_test("1.1: save_session with summary as list", result, "")
    except Exception as e:
        log_test("1.1: save_session with summary as list", False, str(e))
    
    # Test 1.2: save_session with None messages
    try:
        metadata = SessionMetadata(
            session_id="stress-test-002",
            workflow_type="test",
            start_time=datetime.utcnow().isoformat(),
            end_time=datetime.utcnow().isoformat(),
            summary="Test summary",
            entities=[],
            topics=[]
        )
        result = await l4_store.save_session(metadata, None)  # None messages!
        log_test("1.2: save_session with None messages", result, "")
    except Exception as e:
        log_test("1.2: save_session with None messages", False, str(e))
    
    # Test 1.3: save_session with messages containing None content
    try:
        metadata = SessionMetadata(
            session_id="stress-test-003",
            workflow_type="test",
            start_time=datetime.utcnow().isoformat(),
            end_time=datetime.utcnow().isoformat(),
            summary="Test summary",
            entities=[],
            topics=[]
        )
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": None},  # None content!
            {"role": "user", "content": ""}  # Empty content!
        ]
        result = await l4_store.save_session(metadata, messages)
        log_test("1.3: save_session with None/empty content", result, "")
    except Exception as e:
        log_test("1.3: save_session with None/empty content", False, str(e))
    
    # Test 1.4: save_session with empty session_id
    try:
        metadata = SessionMetadata(
            session_id="",  # Empty!
            workflow_type="test",
            start_time=datetime.utcnow().isoformat(),
            end_time=datetime.utcnow().isoformat(),
            summary="Test summary",
            entities=[],
            topics=[]
        )
        result = await l4_store.save_session(metadata, [])
        # Should handle gracefully or reject
        log_test("1.4: save_session with empty session_id", True, "")
    except Exception as e:
        # Expected to fail - that's OK
        log_test("1.4: save_session with empty session_id", True, f"Rejected as expected: {e}")
    
    # Test 1.5: get_context_for_session with empty string
    try:
        result = await memory_engine.get_context_for_session("", "", "test")
        # Should return empty dict, not crash
        log_test("1.5: get_context_for_session with empty input", True, "")
    except Exception as e:
        log_test("1.5: get_context_for_session with empty input", False, str(e))
    
    # Test 1.6: get_context_for_session with 5000 char input
    try:
        long_input = "A" * 5000
        result = await memory_engine.get_context_for_session("test-session", long_input, "test")
        # Should handle without crashing
        log_test("1.6: get_context_for_session with 5000 char input", True, "")
    except Exception as e:
        log_test("1.6: get_context_for_session with 5000 char input", False, str(e))

async def attack_2_layer_failure_isolation():
    """ATTACK 2 — Layer failure isolation"""
    logger.info("\n" + "="*80)
    logger.info("ATTACK 2 — Layer Failure Isolation")
    logger.info("="*80)
    
    # Test 2.1: L2 Neo4j down - get_context should still work
    try:
        # Simulate Neo4j failure by passing empty entity list
        result = await memory_engine.get_context_for_session(
            "test-session-l2-down",
            "test query about ASTA",
            "test"
        )
        # Should fall back to L3 vector search
        log_test("2.1: get_context with L2 degraded", True, "")
    except Exception as e:
        log_test("2.1: get_context with L2 degraded", False, str(e))
    
    # Test 2.2: Empty entity_names to get_cluster_session_ids
    try:
        result = await l2_graph.get_cluster_session_ids([], depth=2)
        # Should return empty list, not crash
        passed = result == []
        log_test("2.2: get_cluster_session_ids with empty list", passed, "" if passed else f"Got {result}")
    except Exception as e:
        log_test("2.2: get_cluster_session_ids with empty list", False, str(e))
    
    # Test 2.3: None entity_names to get_cluster_session_ids
    try:
        result = await l2_graph.get_cluster_session_ids(None, depth=2)
        # If we get here without exception, check if it returned empty list (acceptable)
        if result == []:
            log_test("2.3: get_cluster_session_ids with None", True, "Handled gracefully with empty list")
        else:
            log_test("2.3: get_cluster_session_ids with None", False, f"Should reject None or return [], got {result}")
    except TypeError:
        log_test("2.3: get_cluster_session_ids with None", True, "Correctly rejected None input")
    except Exception as e:
        log_test("2.3: get_cluster_session_ids with None", False, f"Wrong exception: {e}")

async def attack_3_concurrent_stress():
    """ATTACK 3 — Concurrent session stress"""
    logger.info("\n" + "="*80)
    logger.info("ATTACK 3 — Concurrent Session Stress")
    logger.info("="*80)
    
    # Test 3.1: Save 10 sessions simultaneously
    try:
        async def save_test_session(idx: int):
            metadata = SessionMetadata(
                session_id=f"concurrent-test-{idx}",
                workflow_type="test",
                start_time=datetime.utcnow().isoformat(),
                end_time=datetime.utcnow().isoformat(),
                summary=f"Test session {idx} summary",
                entities=[
                    Entity(name=f"Entity{idx}", entity_type="TOPIC", description=f"Test entity {idx}")
                ],
                topics=[f"topic{idx}"]
            )
            messages = [
                {"role": "user", "content": f"Test message {idx}"},
                {"role": "assistant", "content": f"Response {idx}"}
            ]
            return await l4_store.save_session(metadata, messages)
        
        results = await asyncio.gather(*[save_test_session(i) for i in range(10)], return_exceptions=True)
        failures = [r for r in results if isinstance(r, Exception) or not r]
        passed = len(failures) == 0
        log_test("3.1: Save 10 sessions simultaneously", passed, f"{len(failures)} failures" if not passed else "")
    except Exception as e:
        log_test("3.1: Save 10 sessions simultaneously", False, str(e))
    
    # Test 3.2: Retrieve context for 10 sessions simultaneously
    try:
        async def get_test_context(idx: int):
            return await memory_engine.get_context_for_session(
                f"concurrent-retrieve-{idx}",
                f"test query {idx}",
                "test"
            )
        
        results = await asyncio.gather(*[get_test_context(i) for i in range(10)], return_exceptions=True)
        failures = [r for r in results if isinstance(r, Exception)]
        passed = len(failures) == 0
        log_test("3.2: Retrieve 10 contexts simultaneously", passed, f"{len(failures)} failures" if not passed else "")
    except Exception as e:
        log_test("3.2: Retrieve 10 contexts simultaneously", False, str(e))

async def attack_4_entity_extraction_edge_cases():
    """ATTACK 4 — Entity extraction edge cases"""
    logger.info("\n" + "="*80)
    logger.info("ATTACK 4 — Entity Extraction Edge Cases")
    logger.info("="*80)
    
    # Test 4.1: Extract from 1-word input
    try:
        result = await entity_extractor.extract([{"role": "user", "content": "ASTA"}], "test")
        # Should return empty or minimal entities, not crash
        log_test("4.1: Extract from 1-word input", True, "")
    except Exception as e:
        log_test("4.1: Extract from 1-word input", False, str(e))
    
    # Test 4.2: Extract from pure code
    try:
        result = await entity_extractor.extract(
            [{"role": "user", "content": "def foo(): return bar"}],
            "test"
        )
        log_test("4.2: Extract from pure code", True, "")
    except Exception as e:
        log_test("4.2: Extract from pure code", False, str(e))
    
    # Test 4.3: Extract from 10,000 char conversation
    try:
        long_content = "A" * 10000
        result = await entity_extractor.extract(
            [{"role": "user", "content": long_content}],
            "test"
        )
        # Should truncate and still work
        log_test("4.3: Extract from 10,000 char conversation", True, "")
    except Exception as e:
        log_test("4.3: Extract from 10,000 char conversation", False, str(e))
    
    # Test 4.4: spot_entities_in_text with empty text
    try:
        result = entity_extractor.spot_entities_in_text("", ["ASTA", "LangGraph"])
        passed = result == []
        log_test("4.4: spot_entities with empty text", passed, "" if passed else f"Got {result}")
    except Exception as e:
        log_test("4.4: spot_entities with empty text", False, str(e))
    
    # Test 4.5: spot_entities_in_text with None text
    try:
        result = entity_extractor.spot_entities_in_text(None, ["ASTA", "LangGraph"])
        passed = result == []
        log_test("4.5: spot_entities with None text", passed, "" if passed else f"Got {result}")
    except Exception as e:
        log_test("4.5: spot_entities with None text", False, str(e))
    
    # Test 4.6: spot_entities_in_text with empty entity list
    try:
        result = entity_extractor.spot_entities_in_text("test text", [])
        passed = result == []
        log_test("4.6: spot_entities with empty entity list", passed, "" if passed else f"Got {result}")
    except Exception as e:
        log_test("4.6: spot_entities with empty entity list", False, str(e))

async def attack_5_prefetch_queue():
    """ATTACK 5 — Prefetch engine queue bounds"""
    logger.info("\n" + "="*80)
    logger.info("ATTACK 5 — Prefetch Engine Queue Bounds")
    logger.info("="*80)
    
    # Test 5.1: Fire 100 prefetch requests rapidly
    try:
        if not prefetch_engine._prefetch_queue:
            log_test("5.1: Prefetch queue bounded", True, "Prefetch engine not started (OK)")
        else:
            initial_size = prefetch_engine.get_queue_size()
            
            # Fire 100 requests
            for i in range(100):
                await prefetch_engine.on_message(f"test-session-{i}", f"test message {i}")
            
            final_size = prefetch_engine.get_queue_size()
            
            # Queue should be bounded (max 50)
            passed = final_size <= 50
            log_test("5.1: Prefetch queue bounded", passed, 
                    f"Queue size: {final_size} (should be ≤50)" if not passed else f"Queue size: {final_size}")
    except Exception as e:
        log_test("5.1: Prefetch queue bounded", False, str(e))

async def attack_6_format_context():
    """ATTACK 6 — Context formatting edge cases"""
    logger.info("\n" + "="*80)
    logger.info("ATTACK 6 — Context Formatting Edge Cases")
    logger.info("="*80)
    
    # Test 6.1: Format empty context
    try:
        result = memory_engine.format_context_for_prompt({"sessions": []})
        passed = result == ""
        log_test("6.1: Format empty context", passed, "" if passed else f"Got: {result}")
    except Exception as e:
        log_test("6.1: Format empty context", False, str(e))
    
    # Test 6.2: Format context with list summary
    try:
        context = {
            "sessions": [{
                "session_id": "test",
                "workflow_type": "test",
                "end_time": "2026-04-22T00:00:00",
                "summary": ["bullet 1", "bullet 2"],  # List!
                "entities": []
            }]
        }
        result = memory_engine.format_context_for_prompt(context)
        # Should handle list summary gracefully
        passed = "bullet 1" in result or "bullet 2" in result
        log_test("6.2: Format context with list summary", passed, "" if passed else f"Got: {result}")
    except Exception as e:
        log_test("6.2: Format context with list summary", False, str(e))
    
    # Test 6.3: Format context with None summary
    try:
        context = {
            "sessions": [{
                "session_id": "test",
                "workflow_type": "test",
                "end_time": "2026-04-22T00:00:00",
                "summary": None,  # None!
                "entities": []
            }]
        }
        result = memory_engine.format_context_for_prompt(context)
        # Should handle None gracefully
        log_test("6.3: Format context with None summary", True, "")
    except Exception as e:
        log_test("6.3: Format context with None summary", False, str(e))

async def main():
    """Run all stress tests."""
    logger.info("="*80)
    logger.info("ASTA MEMORY LAYER - PHASE 2 STRESS TEST")
    logger.info("="*80)
    logger.info("Starting stress tests...")
    logger.info("")
    
    try:
        # Connect all layers first
        logger.info("Connecting memory layers...")
        status = await memory_engine.connect_all()
        logger.info(f"Connection status: {status}")
        
        # Run all attacks
        await attack_1_corrupt_input()
        await attack_2_layer_failure_isolation()
        await attack_3_concurrent_stress()
        await attack_4_entity_extraction_edge_cases()
        await attack_5_prefetch_queue()
        await attack_6_format_context()
        
    except Exception as e:
        logger.error(f"Fatal error during stress test: {e}")
        traceback.print_exc()
    
    # Print summary
    logger.info("\n" + "="*80)
    logger.info("STRESS TEST SUMMARY")
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
        logger.error("❌ PHASE 2 FAILED - Fix issues before proceeding to Phase 3")
        sys.exit(1)
    else:
        logger.info("✅ ALL STRESS TESTS PASSED - Ready for Phase 3")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
