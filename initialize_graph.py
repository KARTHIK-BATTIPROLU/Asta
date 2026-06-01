"""
Initialize the Neo4j knowledge graph with base structure.
Run this after wiping Neo4j to set up the foundation.
"""
import asyncio
from backend.app.db.database import db_manager
from memory.graph_service import graph_service as l3_manager


async def initialize():
    print("=" * 70)
    print("INITIALIZING NEO4J KNOWLEDGE GRAPH")
    print("=" * 70)
    
    # Connect to database
    await db_manager.connect()
    
    # Initialize base graph
    print("\n✓ Connecting to Neo4j...")
    await l3_manager.initialize_base_graph(user_name="KARTHIK")
    
    # Verify structure
    print("\n✓ Verifying graph structure...")
    if l3_manager.driver:
        async with l3_manager.driver.session() as session:
            # Count nodes
            result = await session.run("MATCH (n) RETURN labels(n)[0] as label, count(n) as count ORDER BY label")
            records = await result.data()
            print("\nNodes created:")
            for record in records:
                label = record.get("label", "")
                count = record.get("count", 0)
                print(f"  {label}: {count}")
            
            # Count relationships
            result2 = await session.run("MATCH ()-[r]->() RETURN type(r) as type, count(r) as count ORDER BY type")
            records2 = await result2.data()
            print("\nRelationships created:")
            for record in records2:
                rel_type = record.get("type", "")
                count = record.get("count", 0)
                print(f"  {rel_type}: {count}")
    
    # Get graph summary
    print("\n✓ Generating graph summary...")
    summary = await l3_manager.get_graph_summary()
    print("\nGraph Summary:")
    print(summary)
    
    await db_manager.disconnect()
    
    print("\n" + "=" * 70)
    print("✅ INITIALIZATION COMPLETE")
    print("=" * 70)
    print("\nThe knowledge graph is ready to use.")
    print("Start ASTA and begin conversations to populate the graph.")


if __name__ == "__main__":
    asyncio.run(initialize())
