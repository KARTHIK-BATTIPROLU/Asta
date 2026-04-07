import asyncio
from backend.app.services.graph_service import L3GraphManager

async def test():
    manager = L3GraphManager()
    
    async with manager.driver.session() as session:
        res = await session.run("MATCH (n) RETURN labels(n) as label, n.name as name")
        print("\nALL NODES:")
        for r in await res.data():
            print(r)
            
        res2 = await session.run("MATCH (n)-[r]->(m) RETURN n.name as n1, type(r) as rel, m.name as n2")
        print("\nALL RELATIONS:")
        for r in await res2.data():
            print(r)

    if hasattr(manager, 'close'): await manager.close()

if __name__ == "__main__":
    asyncio.run(test())
