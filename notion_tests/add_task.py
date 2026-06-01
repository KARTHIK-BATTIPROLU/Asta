#!/usr/bin/env python3
"""
Add a task to ASTA Routine DB
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.services.notion_service import notion_service

async def add_jogging_task():
    """Add jogging task for tomorrow at 5:30 AM"""
    
    # Get tomorrow's date
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print("Adding task to ASTA Routine DB...")
    print(f"Task: Jogging")
    print(f"Time: 5:30 AM")
    print(f"Date: {tomorrow}\n")
    
    try:
        page_id = await notion_service.create_routine_task(
            task_name="Jogging",
            task_type="Fixed",
            scheduled_time="5:30",
            date=tomorrow
        )
        
        print(f"✅ Task created successfully!")
        print(f"   Page ID: {page_id}")
        print(f"\nYou can view it in your ASTA Routine database in Notion.")
        
    except Exception as e:
        print(f"❌ Failed to create task: {e}")

if __name__ == "__main__":
    asyncio.run(add_jogging_task())
