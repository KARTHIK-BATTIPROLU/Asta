#!/usr/bin/env python3
"""
Auto-create Content DB and YouTube DB with correct schema
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.config import settings
import httpx

async def create_content_database():
    """Create Content DB (LinkedIn) as inline database in the existing page"""
    print("Creating Content DB (LinkedIn)...")
    
    # The page ID where we'll create the database
    page_id = "340337e75d17804cafc7d5df3202ca06"
    
    async with httpx.AsyncClient() as client:
        # Create a database as a child of the page
        response = await client.post(
            "https://api.notion.com/v1/databases",
            headers={
                "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            json={
                "parent": {
                    "type": "page_id",
                    "page_id": page_id
                },
                "title": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Content Database"
                        }
                    }
                ],
                "properties": {
                    "Name": {
                        "title": {}
                    },
                    "Date": {
                        "date": {}
                    },
                    "Status": {
                        "select": {
                            "options": [
                                {"name": "Draft", "color": "gray"},
                                {"name": "Ready", "color": "yellow"},
                                {"name": "Published", "color": "green"},
                                {"name": "Archived", "color": "red"}
                            ]
                        }
                    },
                    "Workflow": {
                        "select": {
                            "options": [
                                {"name": "LinkedIn", "color": "blue"},
                                {"name": "Instagram", "color": "pink"},
                                {"name": "Twitter", "color": "blue"},
                                {"name": "Blog", "color": "purple"}
                            ]
                        }
                    }
                }
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            db_id = data["id"]
            print(f"✅ Content DB created successfully!")
            print(f"   Database ID: {db_id}")
            print(f"   URL: {data.get('url', 'N/A')}")
            return db_id
        else:
            print(f"❌ Failed to create Content DB: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def create_youtube_database():
    """Create YouTube DB as inline database in the existing page"""
    print("\nCreating YouTube DB...")
    
    # The page ID where we'll create the database
    page_id = "340337e75d17807d9dc4d605b9930115"
    
    async with httpx.AsyncClient() as client:
        # Create a database as a child of the page
        response = await client.post(
            "https://api.notion.com/v1/databases",
            headers={
                "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            json={
                "parent": {
                    "type": "page_id",
                    "page_id": page_id
                },
                "title": [
                    {
                        "type": "text",
                        "text": {
                            "content": "YouTube Content Database"
                        }
                    }
                ],
                "properties": {
                    "Name": {
                        "title": {}
                    },
                    "Date": {
                        "date": {}
                    },
                    "Status": {
                        "select": {
                            "options": [
                                {"name": "Idea", "color": "gray"},
                                {"name": "Script Ready", "color": "yellow"},
                                {"name": "Recorded", "color": "orange"},
                                {"name": "Edited", "color": "blue"},
                                {"name": "Published", "color": "green"}
                            ]
                        }
                    },
                    "Duration": {
                        "number": {
                            "format": "number"
                        }
                    },
                    "Tags": {
                        "multi_select": {
                            "options": [
                                {"name": "Tutorial", "color": "blue"},
                                {"name": "Vlog", "color": "pink"},
                                {"name": "Tech", "color": "purple"},
                                {"name": "AI", "color": "green"}
                            ]
                        }
                    }
                }
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            db_id = data["id"]
            print(f"✅ YouTube DB created successfully!")
            print(f"   Database ID: {db_id}")
            print(f"   URL: {data.get('url', 'N/A')}")
            return db_id
        else:
            print(f"❌ Failed to create YouTube DB: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def verify_research_database():
    """Verify Research DB exists and has correct schema"""
    print("\nVerifying Research DB...")
    
    db_id = settings.NOTION_RESEARCH_DB
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.notion.com/v1/databases/{db_id}",
            headers={
                "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                "Notion-Version": "2022-06-28"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            title = "".join([t.get("plain_text", "") for t in data.get("title", [])])
            props = list(data.get("properties", {}).keys())
            print(f"✅ Research DB exists: {title}")
            print(f"   Properties: {', '.join(props)}")
            return True
        else:
            print(f"❌ Research DB not accessible: {response.status_code}")
            print(f"   Error: {response.text}")
            return False


async def update_env_file(content_db_id, youtube_db_id):
    """Update .env file with new database IDs"""
    print("\n" + "="*60)
    print("UPDATING .ENV FILE")
    print("="*60)
    
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    updated_lines = []
    for line in lines:
        if line.startswith("NOTION_CONTENT_DB="):
            updated_lines.append(f"NOTION_CONTENT_DB={content_db_id}\n")
            print(f"✅ Updated NOTION_CONTENT_DB={content_db_id}")
        elif line.startswith("NOTION_YOUTUBE_DB="):
            updated_lines.append(f"NOTION_YOUTUBE_DB={youtube_db_id}\n")
            print(f"✅ Updated NOTION_YOUTUBE_DB={youtube_db_id}")
        else:
            updated_lines.append(line)
    
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print("\n✅ .env file updated successfully!")


async def main():
    print("="*60)
    print("ASTA NOTION DATABASE AUTO-CREATOR")
    print("="*60)
    print("\nThis script will:")
    print("1. Create Content DB (LinkedIn) with correct schema")
    print("2. Create YouTube DB with correct schema")
    print("3. Verify Research DB is accessible")
    print("4. Update .env with new database IDs")
    print("\n" + "="*60 + "\n")
    
    # Create databases
    content_db_id = await create_content_database()
    youtube_db_id = await create_youtube_database()
    research_ok = await verify_research_database()
    
    if content_db_id and youtube_db_id:
        # Update .env file
        await update_env_file(content_db_id, youtube_db_id)
        
        print("\n" + "="*60)
        print("✅ ALL DATABASES READY!")
        print("="*60)
        print("\nNext steps:")
        print("1. Run: python notion_tests/diagnose_notion.py")
        print("2. Verify all databases show ✅ Valid DATABASE")
        print("3. Run: python notion_tests/test_notion_live.py")
        print("\n" + "="*60)
    else:
        print("\n" + "="*60)
        print("❌ SOME DATABASES FAILED TO CREATE")
        print("="*60)
        print("\nPlease check the errors above and try again.")


if __name__ == "__main__":
    asyncio.run(main())
