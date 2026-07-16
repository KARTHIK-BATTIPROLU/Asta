"""
Logical backup + restore for ASTA's MongoDB and Neo4j/Graphiti stores.

Why logical (JSON) dumps instead of mongodump/neo4j-admin: this dev machine
doesn't have the Mongo Database Tools installed (only mongod/mongosh), and
Neo4j runs on Aura -- a managed cloud instance with no filesystem to run
neo4j-admin against. A driver-based export/import is the form of backup that
is actually runnable here, and it's exactly what scripts/backup.sh drives.

Subcommands (see scripts/backup.sh for the orchestration):
  insert-canary   Write one uniquely-tagged record to Mongo and Neo4j.
  dump-mongo      Export every Mongo collection to <out>/*.json.
  dump-neo4j      Export all Neo4j nodes + relationships to <out>/*.json.
  test-restore    Load an archive into scratch targets and verify the canary
                  record survived the round trip, then clean up.
"""
import argparse
import asyncio
import json
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import settings  # noqa: E402


async def _mongo_client():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)


def _neo4j_driver():
    from neo4j import AsyncGraphDatabase
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )


async def cmd_insert_canary(args):
    tag = f"backup-canary-{uuid.uuid4().hex[:10]}"
    client = await _mongo_client()
    db = client[settings.DB_NAME]
    await db["backup_canary"].insert_one({
        "tag": tag,
        "text": "backup/restore canary record",
        "created_at": datetime.now(timezone.utc),
    })
    client.close()

    driver = _neo4j_driver()
    async with driver.session() as session:
        await session.run(
            "CREATE (n:BackupCanary {tag: $tag, text: $text, created_at: $ts})",
            tag=tag, text="backup/restore canary node", ts=datetime.now(timezone.utc).isoformat(),
        )
    await driver.close()

    print(tag)  # stdout is the only contract scripts/backup.sh relies on


async def cmd_dump_mongo(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = await _mongo_client()
    db = client[settings.DB_NAME]
    collections = await db.list_collection_names()

    manifest = {"db_name": settings.DB_NAME, "dumped_at": datetime.now(timezone.utc).isoformat(), "collections": []}
    for name in collections:
        docs = await db[name].find({}).to_list(length=None)
        (out_dir / f"{name}.json").write_text(json_util.dumps(docs), encoding="utf-8")
        manifest["collections"].append({"name": name, "count": len(docs)})
        print(f"  mongo/{name}.json: {len(docs)} docs")
    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    client.close()


async def cmd_dump_neo4j(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    driver = _neo4j_driver()
    async with driver.session() as session:
        node_result = await session.run(
            "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props"
        )
        nodes = [dict(r) async for r in node_result]

        rel_result = await session.run(
            "MATCH (a)-[r]->(b) RETURN elementId(r) AS id, type(r) AS type, "
            "elementId(a) AS start_id, elementId(b) AS end_id, properties(r) AS props"
        )
        rels = [dict(r) async for r in rel_result]
    await driver.close()

    (out_dir / "nodes.json").write_text(json.dumps(nodes, default=str), encoding="utf-8")
    (out_dir / "relationships.json").write_text(json.dumps(rels, default=str), encoding="utf-8")
    print(f"  neo4j/nodes.json: {len(nodes)} nodes")
    print(f"  neo4j/relationships.json: {len(rels)} relationships")


async def cmd_test_restore(args):
    archive_path = Path(args.archive)
    canary_tag = args.canary_tag

    with tempfile.TemporaryDirectory(prefix="asta_restore_") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(tmp_path)

        backup_dirs = list(tmp_path.glob("asta_backup_*"))
        assert len(backup_dirs) == 1, f"expected exactly one backup dir in archive, found {backup_dirs}"
        backup_dir = backup_dirs[0]

        # --- Mongo: restore into a scratch database on the same cluster ---
        scratch_db_name = f"{settings.DB_NAME}_restore_test_{uuid.uuid4().hex[:8]}"
        canary_docs = json_util.loads((backup_dir / "mongo" / "backup_canary.json").read_text(encoding="utf-8"))

        client = await _mongo_client()
        scratch_db = client[scratch_db_name]
        if canary_docs:
            await scratch_db["backup_canary"].insert_many(canary_docs)

        restored = await scratch_db["backup_canary"].find_one({"tag": canary_tag})
        mongo_ok = restored is not None
        print(f"  mongo restore -> scratch db '{scratch_db_name}': canary found = {mongo_ok}")

        await client.drop_database(scratch_db_name)
        client.close()

        # --- Neo4j: Aura free tier is a single managed instance -- there's no
        # second instance to restore into, so we restore into a distinctly
        # labeled scratch subgraph (:RestoreTest) in the same instance, verify,
        # then delete exactly those restored nodes. ---
        nodes = json.loads((backup_dir / "neo4j" / "nodes.json").read_text(encoding="utf-8"))
        canary_nodes = [n for n in nodes if n["props"].get("tag") == canary_tag]
        assert canary_nodes, f"canary tag {canary_tag} not present in the Neo4j dump"

        driver = _neo4j_driver()
        async with driver.session() as session:
            for n in canary_nodes:
                await session.run(
                    "CREATE (n:RestoreTest {tag: $tag, text: $text})",
                    tag=n["props"]["tag"], text=n["props"].get("text", ""),
                )
            check = await session.run(
                "MATCH (n:RestoreTest {tag: $tag}) RETURN count(n) AS c", tag=canary_tag
            )
            record = await check.single()
            neo4j_ok = record["c"] > 0
            print(f"  neo4j restore -> :RestoreTest scratch label: canary found = {neo4j_ok}")

            await session.run("MATCH (n:RestoreTest {tag: $tag}) DETACH DELETE n", tag=canary_tag)
        await driver.close()

    ok = mongo_ok and neo4j_ok
    print(f"RESTORE_OK={ok}")
    sys.exit(0 if ok else 1)


async def cmd_cleanup_canary(args):
    tag = args.canary_tag
    client = await _mongo_client()
    db = client[settings.DB_NAME]
    res = await db["backup_canary"].delete_many({"tag": tag})
    print(f"  mongo: deleted {res.deleted_count} canary doc(s)")
    client.close()

    driver = _neo4j_driver()
    async with driver.session() as session:
        await session.run("MATCH (n:BackupCanary {tag: $tag}) DETACH DELETE n", tag=tag)
    await driver.close()
    print("  neo4j: deleted canary node")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("insert-canary")

    p_mongo = sub.add_parser("dump-mongo")
    p_mongo.add_argument("--out", required=True)

    p_neo4j = sub.add_parser("dump-neo4j")
    p_neo4j.add_argument("--out", required=True)

    p_restore = sub.add_parser("test-restore")
    p_restore.add_argument("--archive", required=True)
    p_restore.add_argument("--canary-tag", required=True)

    p_cleanup = sub.add_parser("cleanup-canary")
    p_cleanup.add_argument("--canary-tag", required=True)

    args = parser.parse_args()
    handlers = {
        "insert-canary": cmd_insert_canary,
        "dump-mongo": cmd_dump_mongo,
        "dump-neo4j": cmd_dump_neo4j,
        "test-restore": cmd_test_restore,
        "cleanup-canary": cmd_cleanup_canary,
    }
    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
