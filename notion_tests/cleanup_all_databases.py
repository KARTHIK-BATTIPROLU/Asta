#!/usr/bin/env python3
"""
Clean up ALL ASTA Databases - Remove all existing pages
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.config import settings
import httpx

async def cleanup_database(db_name, db_id):
    """Archive all pages in a database"""
    print(f"\n{'='*55}")
    print(f"Cleaning up {db_name}")
    print(f"{'='*55}")
    print(f"Database ID: {db_id}\n")
    
    async with httpx.AsyncClient() as client:
        # Query all pages in the database
        print("Fetching all pages...")
        response = await client.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
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
            return 0
        
        data = response.json()
        pages = data.get("results", [])
        
        if not pages:
            print("✅ Database is already empty!")
            return 0
        
        print(f"Found {len(pages)} pages to archive\n")
        
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
            
            print(f"  Archiving: {title[:50]} ({page_id[:8]}...)")
            
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
        
        print(f"\n✅ Archived {archived_count} out of {len(pages)} pages from {db_name}")
        return archived_count


async def main():
    print("═══════════════════════════════════════════════════════")
    print("ASTA DATABASES CLEANUP")
    print("═══════════════════════════════════════════════════════")
    print("\n⚠️  WARNING: This will archive ALL pages in:")
    print("  - ASTA Routine DB")
    print("  - ASTA Research DB")
    print("  - Content DB (LinkedIn)")
    print("\nArchived pages can be restored from Notion's trash.\n")
    
    confirm = input("Type 'YES' to confirm cleanup: ").strip()
    
    if confirm != "YES":
        print("\n❌ Cleanup cancelled.")
        return
    
    print("\n🔄 Starting cleanup...\n")
    
    total_archived = 0
    
    # Clean up Routine DB
    total_archived += await cleanup_database("ASTA Routine DB", settings.NOTION_ROUTINE_DB)
    
    # Clean up Research DB
    total_archived += await cleanup_database("ASTA Research DB", settings.NOTION_RESEARCH_DB)
    
    # Clean up Content DB
    total_archived += await cleanup_database("Content DB (LinkedIn)", settings.NOTION_CONTENT_DB)
    
    print(f"\n{'='*55}")
    print(f"✅ CLEANUP COMPLETE")
    print(f"{'='*55}")
    print(f"Total pages archived: {total_archived}")
    print("\nAll databases are now clean and ready for testing!")


if __name__ == "__main__":
    asyncio.run(main())
