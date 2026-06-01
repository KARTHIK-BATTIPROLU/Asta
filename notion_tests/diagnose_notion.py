#!/usr/bin/env python3
"""
Diagnose Notion Database IDs
"""
import os
import sys
import asyncio
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from backend.app.config import settings

async def diagnose():
    print("═══════════════════════════════════════════════════════")
    print("NOTION DATABASE ID DIAGNOSTIC")
    print("═══════════════════════════════════════════════════════\n")
    
    databases = {
        "RESEARCH": settings.NOTION_RESEARCH_DB,
        "DEVELOPER": settings.NOTION_DEVELOPER_DB,
        "CONTENT": settings.NOTION_CONTENT_DB,
        "YOUTUBE": settings.NOTION_YOUTUBE_DB,
        "ROUTINE": settings.NOTION_ROUTINE_DB
    }
    
    headers = {
        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
        "Notion-Version": "2022-06-28"
    }
    
    async with httpx.AsyncClient() as client:
        for db_name, db_id in databases.items():
            if not db_id:
                print(f"❌ {db_name}: EMPTY in .env")
                continue
            
            # Format ID with dashes if needed
            formatted_id = db_id
            if '-' not in db_id and len(db_id) == 32:
                formatted_id = f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"
            
            print(f"\n{db_name}:")
            print(f"  Raw ID: {db_id}")
            print(f"  Formatted: {formatted_id}")
            
            # Try as database
            db_response = await client.get(
                f"https://api.notion.com/v1/databases/{formatted_id}",
                headers=headers
            )
            
            if db_response.status_code == 200:
                db_data = db_response.json()
                title = "".join([t.get("plain_text", "") for t in db_data.get("title", [])])
                print(f"  ✅ Valid DATABASE: {title}")
                continue
            elif db_response.status_code == 400:
                error = db_response.json()
                if "is a page" in error.get("message", ""):
                    print(f"  ❌ This is a PAGE, not a database!")
                    
                    # Try to retrieve as page
                    page_response = await client.get(
                        f"https://api.notion.com/v1/pages/{formatted_id}",
                        headers=headers
                    )
                    
                    if page_response.status_code == 200:
                        page_data = page_response.json()
                        props = page_data.get("properties", {})
                        
                        # Try to get title
                        title = "Unknown"
                        for key, val in props.items():
                            if val.get("type") == "title":
                                title_parts = val.get("title", [])
                                title = "".join(t.get("plain_text", "") for t in title_parts)
                                break
                        
                        print(f"  📄 Page title: {title}")
                        print(f"  🔧 FIX: You need the DATABASE ID, not the page ID")
                        print(f"      1. Open this page in Notion")
                        print(f"      2. Look for a database view on the page")
                        print(f"      3. Click the ⋮⋮ menu on the database → Copy link to view")
                        print(f"      4. Extract the database ID from that URL")
                else:
                    print(f"  ❌ Error: {error.get('message', 'Unknown')}")
            elif db_response.status_code == 404:
                print(f"  ❌ Not found - integration not shared or invalid ID")
            else:
                print(f"  ❌ Error {db_response.status_code}: {db_response.text[:200]}")
    
    print("\n═══════════════════════════════════════════════════════")
    print("SUMMARY")
    print("═══════════════════════════════════════════════════════")
    print("\nYou need to update .env with the correct DATABASE IDs.")
    print("The IDs you have for RESEARCH, CONTENT, and YOUTUBE are PAGE IDs.")
    print("\nTo get the correct database ID:")
    print("1. Open Notion and navigate to the database")
    print("2. Click the ⋮⋮ menu in the top right of the database")
    print("3. Select 'Copy link to view'")
    print("4. The database ID is the 32-character hex string in the URL")
    print("   Format: https://www.notion.so/{workspace}/{DATABASE_ID}?v=...")

if __name__ == "__main__":
    asyncio.run(diagnose())
