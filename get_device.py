import asyncio
from dotenv import load_dotenv
load_dotenv()
from backend.app.db.database import db_manager

async def get_dev():
    await db_manager.connect()
    dev = await db_manager.db.registered_devices.find_one()
    print(dev['device_id'] if dev else 'NO_DEVICE')

asyncio.run(get_dev())
