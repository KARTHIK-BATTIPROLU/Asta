# BLOCKED — items needing Kartik's action

## Neo4j Aura instance unreachable (pre-existing, not caused by this build run)

**Item:** D2.5 acceptance test requires "Neo4j nodes + Pinecone vector grew" after a
research conversation. Pinecone confirmed growing (4 -> 5 vectors after the live
research test). Neo4j cannot be verified — the configured Aura instance does not exist.

**Exact error:**
```
Failed to connect to Neo4j: Cannot resolve address c706f89b.databases.neo4j.io:7687
```
`nslookup c706f89b.databases.neo4j.io` returns **Non-existent domain** (NXDOMAIN) —
this is not a sandbox/DNS restriction, the hostname itself no longer exists.

**What was tried:**
- Confirmed `.env` has `NEO4J_URI=neo4j+s://c706f89b.databases.neo4j.io`,
  `NEO4J_USERNAME=c706f89b`, `NEO4J_PASSWORD=...`, `NEO4J_DATABASE=c706f89b`.
- `nslookup` confirms NXDOMAIN — the Aura instance `c706f89b` appears to have been
  deleted or its free-tier instance expired/was removed.
- This is pre-existing (same error appears in logs before this session's changes).
- The system degrades gracefully as required: `memory.memory_engine` logs
  `L2_neo4j failed to connect` and continues with L1/L3/L4 only — no turn crashes.

**What Kartik must do:**
1. Create a new Neo4j Aura (free tier is fine) instance, or restart/restore the
   existing `c706f89b` instance from the Aura console if it was just paused
   (note: paused Aura instances usually still resolve DNS, so it was likely deleted).
2. Update `.env` with the new `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`,
   `NEO4J_DATABASE`.
3. Restart the backend — `memory.l2_graph` will reconnect automatically on next
   startup (no code change needed).

**Downstream impact:** None blocking. `research_context` is held in LangGraph thread
state (Mongo checkpointer) independent of Neo4j, so Day 3 content-chaining is NOT
affected. Memory recall (test #6) will work via L3 Pinecone + L4 Mongo even with L2
down, just without the entity-graph cross-linking.
