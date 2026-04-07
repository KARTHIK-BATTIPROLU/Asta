import asyncio
from backend.app.services.graph_service import L3GraphManager

async def test():
    manager = L3GraphManager()
    await manager.connect()
    identity = await manager.get_user_identity("KARTHIK")
    print(identity)
    await manager.close()

if __name__ == "__main__":
    asyncio.run(test())
