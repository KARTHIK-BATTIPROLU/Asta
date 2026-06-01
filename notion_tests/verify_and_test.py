#!/usr/bin/env python3
"""
Verify database access and run comprehensive tests
"""
import asyncio
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.config import settings
from backend.app.services.notion_service import notion_service
from notion_client import AsyncClient
import httpx

async def verify_database_access():
    """Verify ASTA integration has access to all databases"""
    print("═══════════════════════════════════════════════════════")
    print("VERIFYING DATABASE ACCESS")
    print("═══════════════════════════════════════════════════════\n")
    
    databases = {
        "Routine": settings.NOTION_ROUTINE_DB,
        "Research": settings.NOTION_RESEARCH_DB,
        "Content": settings.NOTION_CONTENT_DB
    }
    
    all_accessible = True
    
    async with httpx.AsyncClient() as client:
        for db_name, db_id in databases.items():
            # Test read access
            response = await client.get(
                f"https://api.notion.com/v1/databases/{db_id}",
                headers={
                    "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28"
                }
            )
            
            if response.status_code == 200:
                print(f"✅ {db_name} DB - Read access: OK")
            else:
                print(f"❌ {db_name} DB - Read access: FAILED ({response.status_code})")
                all_accessible = False
                continue
            
            # Test write access (try to create a test page)
            test_response = await client.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                },
                json={
                    "parent": {"database_id": db_id},
                    "properties": {
                        "Name": {"title": [{"text": {"content": "Access Test"}}]}
                    }
                }
            )
            
            if test_response.status_code == 200:
                print(f"✅ {db_name} DB - Write access: OK")
                # Clean up test page
                test_page_id = test_response.json()["id"]
                await client.patch(
                    f"https://api.notion.com/v1/pages/{test_page_id}",
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={"archived": True}
                )
            else:
                print(f"❌ {db_name} DB - Write access: FAILED ({test_response.status_code})")
                print(f"   Error: {test_response.text[:200]}")
                all_accessible = False
    
    print("\n" + "="*55)
    if all_accessible:
        print("✅ ALL DATABASES ACCESSIBLE")
        print("="*55)
        return True
    else:
        print("❌ SOME DATABASES NOT ACCESSIBLE")
        print("="*55)
        print("\nFIX REQUIRED:")
        print("1. Go to each database in Notion")
        print("2. Click '...' menu → Connections")
        print("3. Add 'ASTA' integration")
        print("4. Make sure it has 'Can edit' permission")
        return False


async def run_comprehensive_tests():
    """Run comprehensive tests on all databases"""
    print("\n═══════════════════════════════════════════════════════")
    print("RUNNING COMPREHENSIVE TESTS")
    print("═══════════════════════════════════════════════════════\n")
    
    client = AsyncClient(auth=settings.NOTION_API_KEY)
    test_results = {}
    created_pages = []
    
    # TEST 1: Create routine task
    print("TEST 1: Create routine task...")
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        page_id = await notion_service.create_routine_task(
            task_name="Integration Test Task",
            task_type="Fixed",
            scheduled_time="10:00",
            date=today
        )
        created_pages.append(page_id)
        print(f"  ✅ PASS - Created task: {page_id[:8]}...")
        test_results["Create routine task"] = "PASS"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Create routine task"] = "FAIL"
    
    # TEST 2: Update task status
    print("\nTEST 2: Update task status...")
    try:
        if created_pages:
            success = await notion_service.update_task_status(created_pages[0], "Completed")
            assert success
            print(f"  ✅ PASS - Updated status to Completed")
            test_results["Update task status"] = "PASS"
        else:
            print(f"  ⏭️  SKIP - No task to update")
            test_results["Update task status"] = "SKIP"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Update task status"] = "FAIL"
    
    # TEST 3: Query pending tasks
    print("\nTEST 3: Query pending tasks...")
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await notion_service.get_pending_tasks(today)
        print(f"  ✅ PASS - Retrieved {len(tasks)} tasks")
        test_results["Query pending tasks"] = "PASS"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Query pending tasks"] = "FAIL"
    
    # TEST 4: Gratitude journal
    print("\nTEST 4: Gratitude journal...")
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        success = await notion_service.append_to_gratitude_page(
            entry="Integration test successful!",
            date=today
        )
        assert success
        print(f"  ✅ PASS - Appended to gratitude journal")
        test_results["Gratitude journal"] = "PASS"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Gratitude journal"] = "FAIL"
    
    # TEST 5: Permanent memory
    print("\nTEST 5: Permanent memory...")
    try:
        success = await notion_service.append_to_permanent_memory(
            content="Integration test: All systems operational",
            tags=["ASTA", "test"]
        )
        assert success
        print(f"  ✅ PASS - Appended to permanent memory")
        test_results["Permanent memory"] = "PASS"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Permanent memory"] = "FAIL"
    
    # TEST 6: Create research page
    print("\nTEST 6: Create research page...")
    try:
        page_id = await notion_service.create_research_page(
            topic="Integration Test",
            conversation_summary="Testing ASTA Notion integration",
            research_points=["Point 1", "Point 2", "Point 3"],
            combined_solution="All tests passing"
        )
        created_pages.append(page_id)
        print(f"  ✅ PASS - Created research page: {page_id[:8]}...")
        test_results["Create research page"] = "PASS"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Create research page"] = "FAIL"
    
    # TEST 7: Create LinkedIn content
    print("\nTEST 7: Create LinkedIn content...")
    try:
        page_id = await notion_service.create_linkedin_page(
            topic="Integration Test",
            post_body="Testing ASTA's Notion integration!",
            hashtags=["#ASTA", "#Notion", "#AI"],
            discussion_summary="Integration test"
        )
        created_pages.append(page_id)
        print(f"  ✅ PASS - Created LinkedIn page: {page_id[:8]}...")
        test_results["Create LinkedIn content"] = "PASS"
    except Exception as e:
        print(f"  ❌ FAIL - {str(e)[:100]}")
        test_results["Create LinkedIn content"] = "FAIL"
    
    # Cleanup
    print("\n🧹 Cleaning up test pages...")
    for page_id in created_pages:
        try:
            await client.pages.update(page_id=page_id, archived=True)
        except:
            pass
    
    # Print results
    print("\n" + "="*55)
    print("TEST RESULTS")
    print("="*55)
    
    passed = sum(1 for r in test_results.values() if r == "PASS")
    failed = sum(1 for r in test_results.values() if r == "FAIL")
    skipped = sum(1 for r in test_results.values() if r == "SKIP")
    
    for test_name, result in test_results.items():
        emoji = "✅" if result == "PASS" else "❌" if result == "FAIL" else "⏭️"
        print(f"{emoji} {test_name:<30} {result}")
    
    print("\n" + "="*55)
    print(f"PASSED: {passed} | FAILED: {failed} | SKIPPED: {skipped}")
    print("="*55)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        print("ASTA Notion integration is fully operational!")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return False


async def main():
    # Step 1: Verify access
    has_access = await verify_database_access()
    
    if not has_access:
        print("\n❌ Cannot proceed with tests - fix database access first")
        return
    
    # Step 2: Run tests
    await asyncio.sleep(1)
    success = await run_comprehensive_tests()
    
    if success:
        print("\n✅ NOTION INTEGRATION READY FOR PRODUCTION!")


if __name__ == "__main__":
    asyncio.run(main())
