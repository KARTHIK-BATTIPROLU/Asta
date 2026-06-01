#!/usr/bin/env python3
"""
Show all pending tasks in ASTA Routine DB
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.config import settings
from backend.app.services.notion_service import notion_service
from notion_client import AsyncClient

async def show_pending_tasks():
    print("═══════════════════════════════════════════════════════")
    print("ASTA ROUTINE DB — PENDING TASKS")
    print("═══════════════════════════════════════════════════════\n")
    
    # Use the working notion_service instead
    from backend.app.services.notion_service import notion_service
    
    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"📅 Date: {today}\n")
    
    try:
        # Use the working get_pending_tasks method
        tasks = await notion_service.get_pending_tasks(today)
        
        if not tasks:
            print("✅ No pending tasks found for today!")
            print("\nLet me check ALL pending tasks (any date)...\n")
            
            # Query all pending tasks using the client directly
            client = AsyncClient(auth=settings.NOTION_API_KEY)
            
            # Use httpx directly to query
            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f"https://api.notion.com/v1/databases/{settings.NOTION_ROUTINE_DB}/query",
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "filter": {
                            "property": "Status",
                            "select": {
                                "does_not_equal": "Completed"
                            }
                        },
                        "sorts": [
                            {
                                "property": "Date",
                                "direction": "descending"
                            }
                        ]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    all_tasks = data.get("results", [])
                    
                    if not all_tasks:
                        print("✅ No pending tasks at all!")
                        return
                    
                    print(f"Found {len(all_tasks)} pending task(s) (all dates):\n")
                    print("-" * 80)
                    
                    for i, page in enumerate(all_tasks, 1):
                        props = page["properties"]
                        
                        # Extract properties
                        task_name = ""
                        if "Task Name" in props and props["Task Name"]["title"]:
                            task_name = props["Task Name"]["title"][0]["text"]["content"]
                        
                        task_type = ""
                        if "Type" in props and props["Type"].get("select"):
                            task_type = props["Type"]["select"]["name"]
                        
                        scheduled_time = ""
                        if "Scheduled Time" in props and props["Scheduled Time"].get("rich_text"):
                            scheduled_time = props["Scheduled Time"]["rich_text"][0]["text"]["content"]
                        
                        status = ""
                        if "Status" in props and props["Status"].get("select"):
                            status = props["Status"]["select"]["name"]
                        
                        date = ""
                        if "Date" in props and props["Date"].get("date"):
                            date = props["Date"]["date"]["start"]
                        
                        # Format output
                        print(f"\n{i}. {task_name}")
                        print(f"   📅 Date: {date}")
                        print(f"   ⏰ Time: {scheduled_time}")
                        print(f"   📋 Type: {task_type}")
                        print(f"   🔵 Status: {status}")
                        print(f"   🔗 ID: {page['id'][:8]}...")
                    
                    print("\n" + "-" * 80)
                else:
                    print(f"❌ Error: {response.status_code} - {response.text}")
            
            return
        
        print(f"Found {len(tasks)} pending task(s) for TODAY:\n")
        print("-" * 80)
        
        for i, task in enumerate(tasks, 1):
            print(f"\n{i}. {task['task_name']}")
            print(f"   ⏰ Time: {task['scheduled_time']}")
            print(f"   📋 Type: {task['type']}")
            print(f"   🔵 Status: {task['status']}")
            print(f"   🔗 ID: {task['page_id'][:8]}...")
        
        print("\n" + "-" * 80)
        print("\n═══════════════════════════════════════════════════════")
        
    except Exception as e:
        print(f"❌ Error fetching tasks: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(show_pending_tasks())
