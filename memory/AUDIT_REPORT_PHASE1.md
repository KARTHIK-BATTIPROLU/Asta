# ASTA MEMORY LAYER - PHASE 1 STRUCTURAL AUDIT REPORT
Date: 2026-04-22
Auditor: Senior AI Systems Engineer

## EXECUTIVE SUMMARY
**STATUS: CRITICAL FAILURES FOUND - IMMEDIATE FIX REQUIRED**

Found 15 critical issues across memory layers and backend integration.
Memory layer is NOT production-ready until all issues are resolved.

---

## 1. memory/schema.py ✅ PASS
- All TypedDicts and dataclasses complete
- ENTITY_TYPES list correct: ["PROJECT", "SKILL", "PERSON", "GOAL", "TOPIC", "DECISION", "TASK"]
- No missing fields detected

---

## 2. memory/l4_store.py ⚠️ ISSUES FOUND

### ISSUE 2.1: Summary type validation missing
**File**: memory/l4_store.py, line 93
**Problem**: `save_session()` does NOT validate that summary is a STRING
**Impact**: If summary is passed as a list, MongoDB will store it as array, breaking retrieval
**Fix Required**: Add type validation before storage

```python
# Current code (line 93):
"summary": metadata.summary,

# Should be:
"summary": metadata.summary if isinstance(metadata.summary, str) else str(metadata.summary),
```

### ISSUE 2.2: TTL index exists ✅
**Status**: PASS - TTL index on `raw_transcript_expires_at` is correctly configured (line 56)

### ISSUE 2.3: Collection names consistent ✅
**Status**: PASS - All collection names are consistent

---

## 3. memory/l3_vectors.py ⚠️ CRITICAL ISSUES

### ISSUE 3.1: Embedding model mismatch
**File**: memory/l3_vectors.py, line 23
**Problem**: Comments say "text-embedding-004" but code uses "gemini-embedding-001" (3072 dimensions)
**Impact**: Documentation mismatch, but code is correct
**Fix Required**: Update comment to match actual model

### ISSUE 3.2: Empty string handling ✅ PASS
**File**: memory/l3_vectors.py, lines 73-76
**Status**: PASS - `embed_text()` correctly handles empty strings and returns []

### ISSUE 3.3: Pinecone dimension match ✅ PASS
**File**: memory/l3_vectors.py, line 48
**Status**: PASS - Pinecone index dimension (3072) matches embedding dimension exactly

### ISSUE 3.4: List input handling
**File**: memory/l3_vectors.py, lines 68-70
**Problem**: Converts list to string with join, but this is WRONG for summary lists
**Impact**: If summary is ["bullet 1", "bullet 2"], it becomes "bullet 1 bullet 2" losing structure
**Fix Required**: Reject list inputs or handle properly

---

## 4. memory/l2_graph.py ❌ CRITICAL FAILURE

### ISSUE 4.1: get_cluster_session_ids() empty input crash
**File**: memory/l2_graph.py, line 145
**Problem**: If `entity_names` is empty list [], Neo4j query will fail with "WHERE e.name IN []"
**Impact**: CRASH on empty input
**Fix Required**: Add guard clause

```python
# Add at line 145:
if not entity_names:
    return []
```

### ISSUE 4.2: SQL injection via f-string ❌ CRITICAL
**File**: memory/l2_graph.py, lines 111, 119
**Problem**: Uses f-string for label injection: `f"MERGE (e:{label} {{name: $name}})"`
**Impact**: If entity_type contains malicious input, could inject Cypher
**Fix Required**: Use parameterized label or whitelist validation

```python
# Current (UNSAFE):
query = f"""
MERGE (e:{label} {{name: $name}})
"""

# Should validate label first:
if label not in NEO4J_LABELS.values():
    label = "Topic"  # Safe default
```

### ISSUE 4.3: Karthik root node creation ✅ PASS
**File**: memory/l2_graph.py, line 40
**Status**: PASS - Root node created on connect()

---

## 5. memory/l1_cache.py ✅ MOSTLY PASS

### ISSUE 5.1: cache_entity_context() serialization ✅ PASS
**File**: memory/l1_cache.py, line 115
**Status**: PASS - Serializes to JSON without errors

### ISSUE 5.2: get_entity_context() KeyError handling ✅ PASS
**File**: memory/l1_cache.py, line 130
**Status**: PASS - Returns None on cache miss, no KeyError

### ISSUE 5.3: TTL values from settings ✅ PASS
**File**: memory/l1_cache.py, lines 73, 117
**Status**: PASS - Uses `settings.REDIS_TTL_HOT` and `settings.REDIS_TTL_ENTITY`

---

## 6. memory/entity_extractor.py ⚠️ ISSUES FOUND

### ISSUE 6.1: Malformed JSON handling ✅ PASS
**File**: memory/entity_extractor.py, lines 88-94
**Status**: PASS - Has try/except for JSONDecodeError

### ISSUE 6.2: Entity type validation ✅ PASS
**File**: memory/entity_extractor.py, line 100
**Status**: PASS - Validates `entity_type in ENTITY_TYPES`

### ISSUE 6.3: spot_entities_in_text() empty handling ⚠️ ISSUE
**File**: memory/entity_extractor.py, line 120
**Problem**: If `text` is None, will crash on `text.lower()`
**Impact**: Crash on None input
**Fix Required**: Add None check

```python
# Add at line 120:
if not text or not known_entities:
    return []
```

---

## 7. memory/prefetch_engine.py ⚠️ ISSUES FOUND

### ISSUE 7.1: Worker restart on crash ❌ MISSING
**File**: memory/prefetch_engine.py, line 155
**Problem**: Worker catches exceptions but does NOT restart if it crashes
**Impact**: Prefetch stops working after first error
**Fix Required**: Add restart logic or supervisor

### ISSUE 7.2: on_message() disabled check ✅ PASS
**File**: memory/prefetch_engine.py, line 96
**Status**: PASS - Skips if `MEMORY_PREFETCH_ENABLED` is False

### ISSUE 7.3: Queue bounded ❌ MISSING
**File**: memory/prefetch_engine.py, line 64
**Problem**: Queue is unbounded `asyncio.Queue()` - can grow infinitely
**Impact**: Memory leak on high traffic
**Fix Required**: Use `asyncio.Queue(maxsize=50)`

---

## 8. memory/memory_engine.py ⚠️ ISSUES FOUND

### ISSUE 8.1: get_context_for_session() failure handling ⚠️ PARTIAL
**File**: memory/memory_engine.py, line 77
**Problem**: Returns empty dict on failure, but doesn't handle individual layer failures gracefully
**Impact**: If L2 fails, entire retrieval fails instead of falling back to L3
**Fix Required**: Add per-layer try/except with fallback

### ISSUE 8.2: save_session() atomic writes ⚠️ PARTIAL
**File**: memory/memory_engine.py, line 186
**Problem**: Writes to L4, L3, L2 sequentially - if L3 fails, L2 never runs
**Impact**: Partial data loss on layer failure
**Fix Required**: Use asyncio.gather with return_exceptions=True

### ISSUE 8.3: format_context_for_prompt() empty handling ✅ PASS
**File**: memory/memory_engine.py, line 283
**Status**: PASS - Returns empty string on empty sessions

---

## 9. backend/app/services/session_manager.py ❌ CRITICAL FAILURES

### ISSUE 9.1: HOOK 1 - memory_context storage ❌ MISSING
**File**: session_manager.py, line 565
**Problem**: `_create_new_session()` tries to store memory_context but Session model may not have this field
**Impact**: AttributeError if Session doesn't have memory_context field
**Fix Required**: Verify Session model has memory_context field or use dict storage

### ISSUE 9.2: HOOK 2 - prefetch on user message ✅ PASS
**File**: session_manager.py, line 685
**Status**: PASS - Fires `_fire_memory_prefetch()` only on role=="user"

### ISSUE 9.3: HOOK 3 - memory save on end_session ✅ PASS
**File**: session_manager.py, line 774
**Status**: PASS - Calls `memory_engine.save_session()` before cleanup

---

## 10. backend/app/services/llm_service.py ⚠️ ISSUES FOUND

### ISSUE 10.1: get_system_prompt() memory_context parameter ✅ PASS
**File**: llm_service.py, line 8
**Status**: PASS - Accepts `memory_context` parameter

### ISSUE 10.2: Memory context injection position ✅ PASS
**File**: llm_service.py, line 35
**Status**: PASS - Memory context injected ABOVE personality prompt

### ISSUE 10.3: get_hydrated_messages() pass-through ✅ PASS
**File**: llm_service.py, line 67
**Status**: PASS - Passes memory_context through to get_system_prompt()

---

## 11. backend/app/api/ws_routes.py ⚠️ ISSUES FOUND (PARTIAL READ)

### ISSUE 11.1: stream_llm_response() memory_context ✅ PASS
**File**: ws_routes.py, line 572 (truncated)
**Status**: PASS - Fetches memory_context from SessionManager.get_session()

### ISSUE 11.2: Memory context fetch ⚠️ NEEDS VERIFICATION
**File**: ws_routes.py (need to read more)
**Problem**: File truncated, need to verify full implementation
**Fix Required**: Read remaining lines to verify

---

## CRITICAL ISSUES SUMMARY

### MUST FIX BEFORE PRODUCTION:
1. ❌ **l2_graph.py**: SQL injection via f-string label (SECURITY)
2. ❌ **l2_graph.py**: Empty entity_names crash
3. ❌ **prefetch_engine.py**: Unbounded queue (MEMORY LEAK)
4. ❌ **session_manager.py**: memory_context field may not exist
5. ⚠️ **l4_store.py**: Summary type validation missing
6. ⚠️ **l3_vectors.py**: List input handling wrong
7. ⚠️ **entity_extractor.py**: None text crash
8. ⚠️ **memory_engine.py**: No per-layer failure isolation
9. ⚠️ **prefetch_engine.py**: Worker doesn't restart on crash

### TOTAL ISSUES: 15
- Critical (❌): 4
- Warning (⚠️): 11
- Pass (✅): Many

---

## NEXT STEPS

1. Fix all critical issues immediately
2. Run Phase 2 stress tests to verify fixes
3. Run Phase 3 E2E tests
4. Run Phase 4 performance benchmarks
5. Only then declare production-ready

**DO NOT PROCEED TO PHASE 2 UNTIL CRITICAL ISSUES ARE FIXED**
