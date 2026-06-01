#!/usr/bin/env python3
"""
Helper script to update Notion database IDs in .env
Run this after getting the correct database IDs from Notion.
"""

import os
import sys

def update_env_file():
    print("═══════════════════════════════════════════════════════")
    print("UPDATE NOTION DATABASE IDs IN .ENV")
    print("═══════════════════════════════════════════════════════\n")
    
    print("This script will help you update the database IDs in .env")
    print("You need to get the correct database IDs from Notion first.\n")
    
    print("How to get database IDs from Notion:")
    print("1. Open Notion and navigate to the database")
    print("2. Click the ⋮⋮ menu in the top-right of the database")
    print("3. Select 'Copy link to view'")
    print("4. Extract the 32-character ID from the URL\n")
    
    databases = {
        "NOTION_RESEARCH_DB": "Research DB",
        "NOTION_DEVELOPER_DB": "Developer DB",
        "NOTION_CONTENT_DB": "Content DB (LinkedIn)",
        "NOTION_YOUTUBE_DB": "YouTube DB"
    }
    
    new_ids = {}
    
    for env_var, db_name in databases.items():
        print(f"\n{db_name}:")
        db_id = input(f"  Enter database ID for {env_var}: ").strip()
        
        if db_id:
            # Remove dashes if present
            db_id = db_id.replace("-", "")
            
            # Validate length
            if len(db_id) != 32:
                print(f"  ⚠️  Warning: ID should be 32 characters, got {len(db_id)}")
                confirm = input("  Continue anyway? (y/n): ").strip().lower()
                if confirm != 'y':
                    print("  Skipping...")
                    continue
            
            new_ids[env_var] = db_id
            print(f"  ✅ Will update {env_var}")
        else:
            print(f"  ⏭️  Skipping {env_var}")
    
    if not new_ids:
        print("\n❌ No IDs provided. Exiting.")
        return
    
    print("\n" + "=" * 55)
    print("SUMMARY OF CHANGES:")
    print("=" * 55)
    for env_var, db_id in new_ids.items():
        print(f"{env_var}={db_id}")
    
    confirm = input("\nApply these changes to .env? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Cancelled. No changes made.")
        return
    
    # Read current .env
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    
    if not os.path.exists(env_path):
        print(f"❌ .env file not found at {env_path}")
        return
    
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Update lines
    updated_lines = []
    updated_count = 0
    
    for line in lines:
        updated = False
        for env_var, db_id in new_ids.items():
            if line.startswith(f"{env_var}="):
                updated_lines.append(f"{env_var}={db_id}\n")
                updated = True
                updated_count += 1
                break
        
        if not updated:
            updated_lines.append(line)
    
    # Write back
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print(f"\n✅ Updated {updated_count} database IDs in .env")
    print("\nNext steps:")
    print("1. Run: python diagnose_notion.py")
    print("2. Verify all databases show ✅ Valid DATABASE")
    print("3. Run: python test_notion_live.py")

if __name__ == "__main__":
    try:
        update_env_file()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user.")
        sys.exit(1)
