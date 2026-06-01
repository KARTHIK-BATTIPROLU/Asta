#!/usr/bin/env python3
"""
Clean up ASTA Routine Database - Remove all existing pages
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.config import settings
import httpx

async def cleanup_routine_database():
    """Archive all pages in ASTA Routine database"""
    print("═══════════════════════════════════════════════════════")
    print("ASTA ROUTINE DATABASE CLEANUP")
    print("═══════════════════════════════════════════════════════\n")
    
    print(f"Database ID: {settings.NOTION_ROUTINE_DB}\n")
    
    async with httpx.AsyncClient() as client:
        # Query all pages in the database
        print("Fetching all pages...")
        response = await client.post(
            f"https://api.notion.com/v1/databases/{settings.NOTION_ROUTINE_DB}/query",
            headers={
                "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            json={}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to query database: {response.status_code}")
            print(f"   Error: {response.text}")
            return
        
        data = response.json()
        pages = data.get("results", [])
        
        if not pages:
            print("✅ Database is already empty!")
            return
        
        print(f"Found {len(pages)} pages to archive:\n")
        
        # Archive each page
        archived_count = 0
        for page in pages:
            page_id = page["id"]
            props = page.get("properties", {})
            
            # Try to get the title
            title = "Untitled"
            for key, val in props.items():
                if val.get("type") == "title":
                    title_parts = val.get("title", [])
                    if title_parts:
                        title = "".join(t.get("plain_text", "") for t in title_parts)
                    break
            
            print(f"  Archiving: {title} ({page_id[:8]}...)")
            
            # Archive the page
            archive_response = await client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers={
                    "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                },
                json={"archived": True}
            )
            
            if archive_response.status_code == 200:
                archived_count += 1
                print(f"    ✅ Archived")
            else:
                print(f"    ❌ Failed: {archive_response.status_code}")
        
        print(f"\n{'='*55}")
        print(f"✅ Archived {archived_count} out of {len(pages)} pages")
        print(f"{'='*55}")


async def main():
    print("\n⚠️  WARNING: This will archive ALL pages in ASTA Routine DB")
    print("This includes:")
    print("  - All tasks (Morning Jog, Fu, etc.)")
    print("  - DSA Progress Tracker")
    print("  - Permanent Memory")
    print("  - Gratitude Journal")
    print("  - ASTA — Study Plan")
    print("\nArchived pages can be restored from Notion's trash.\n")
    
    confirm = input("Type 'YES' to confirm cleanup: ").strip()
    
    if confirm != "YES":
        print("\n❌ Cleanup cancelled.")
        return
    
    print("\n🔄 Starting cleanup...\n")
    await cleanup_routine_database()
    print("\n✅ Cleanup complete!")


if __name__ == "__main__":
    asyncio.run(main())
