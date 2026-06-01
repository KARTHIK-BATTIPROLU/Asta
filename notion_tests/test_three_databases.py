#!/usr/bin/env python3
"""
ASTA Notion Integration Tests - 3 Database Focus
Tests only Routine, Research, and Content databases (free tier limit)
"""

import asyncio
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.config import settings
from backend.app.services.notion_service import notion_service
from notion_client import AsyncClient

class ThreeDatabaseTests:
    def __init__(self):
        self.client = AsyncClient(auth=settings.NOTION_API_KEY)
        self.test_results = {}
        self.created_pages = []
        
    async def run_all_tests(self):
        """Run all tests for 3 databases"""
        print("═══════════════════════════════════════════════════════")
        print("ASTA NOTION INTEGRATION - 3 DATABASE TESTS")
        print("(Routine, Research, Content)")
        print("═══════════════════════════════════════════════════════\n")
        
        # Test Routine DB
        print("🔄 TESTING ROUTINE DB")
        await self.test_routine_create()
        await self.test_routine_update()
        await self.test_routine_query()
        await self.test_gratitude_journal()
        await self.test_permanent_memory()
        
        # Test Research DB
        print("\n🔄 TESTING RESEARCH DB")
        await self.test_research_create()
        
        # Test Content DB
        print("\n🔄 TESTING CONTENT DB")
        await self.test_content_create()
        
        await self.cleanup_test_pages()
        self.print_final_report()
    
    async def test_routine_create(self):
        """TEST 1 — Create routine task"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            page_id = await notion_service.create_routine_task(
                task_name="ASTA Integration Test",
                task_type="Fixed",
                scheduled_time="10:00",
                date=today
            )
            
            assert page_id, "Failed to create routine task"
            self.created_pages.append(page_id)
            print(f"✅ Created routine task: {page_id[:8]}...")
            
            self.test_results["Routine: Create task"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Routine create failed: {e}")
            self.test_results["Routine: Create task"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def test_routine_update(self):
        """TEST 2 — Update task status"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            page_id = await notion_service.create_routine_task(
                task_name="ASTA Update Test",
                task_type="Dynamic",
                scheduled_time="11:00",
                date=today
            )
            self.created_pages.append(page_id)
            
            success = await notion_service.update_task_status(page_id, "Completed")
            assert success, "Failed to update status"
            
            print(f"✅ Updated task status to Completed")
            self.test_results["Routine: Update status"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Routine update failed: {e}")
            self.test_results["Routine: Update status"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def test_routine_query(self):
        """TEST 3 — Query pending tasks"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            tasks = await notion_service.get_pending_tasks(today)
            print(f"✅ Retrieved {len(tasks)} pending tasks")
            
            self.test_results["Routine: Query tasks"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Routine query failed: {e}")
            self.test_results["Routine: Query tasks"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def test_gratitude_journal(self):
        """TEST 4 — Gratitude journal"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            success = await notion_service.append_to_gratitude_page(
                entry="Test: Notion integration working with 3 databases!",
                date=today
            )
            
            assert success, "Failed to append to gratitude journal"
            print("✅ Gratitude journal append successful")
            
            self.test_results["Routine: Gratitude journal"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Gratitude journal failed: {e}")
            self.test_results["Routine: Gratitude journal"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def test_permanent_memory(self):
        """TEST 5 — Permanent memory"""
        start_time = time.time()
        try:
            success = await notion_service.append_to_permanent_memory(
                content="Test: 3-database setup complete with free tier",
                tags=["ASTA", "Notion", "integration"]
            )
            
            assert success, "Failed to append to permanent memory"
            print("✅ Permanent memory append successful")
            
            self.test_results["Routine: Permanent memory"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Permanent memory failed: {e}")
            self.test_results["Routine: Permanent memory"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def test_research_create(self):
        """TEST 6 — Create research page"""
        start_time = time.time()
        try:
            page_id = await notion_service.create_research_page(
                topic="Notion Integration Test",
                conversation_summary="Testing ASTA's Notion integration with 3 databases on free tier",
                research_points=[
                    "Free tier allows 3 database connections",
                    "Prioritized Routine, Research, and Content databases",
                    "All core ASTA workflows supported"
                ],
                combined_solution="Use 3-database setup for optimal ASTA functionality within free tier limits"
            )
            
            assert page_id, "Failed to create research page"
            self.created_pages.append(page_id)
            print(f"✅ Created research page: {page_id[:8]}...")
            
            self.test_results["Research: Create page"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Research create failed: {e}")
            self.test_results["Research: Create page"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def test_content_create(self):
        """TEST 7 — Create LinkedIn content"""
        start_time = time.time()
        try:
            page_id = await notion_service.create_linkedin_page(
                topic="ASTA Integration Test",
                post_body="Just completed ASTA's Notion integration! Working with 3 databases on the free tier.",
                hashtags=["#BuildInPublic", "#AI", "#Notion", "#ASTA"],
                discussion_summary="Successfully integrated ASTA with Notion using free tier limits"
            )
            
            assert page_id, "Failed to create LinkedIn page"
            self.created_pages.append(page_id)
            print(f"✅ Created LinkedIn content: {page_id[:8]}...")
            
            self.test_results["Content: Create LinkedIn"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Content create failed: {e}")
            self.test_results["Content: Create LinkedIn"] = ("FAIL", int((time.time() - start_time) * 1000))
    
    async def cleanup_test_pages(self):
        """Archive all test pages"""
        archived_count = 0
        
        for page_id in self.created_pages:
            try:
                await self.client.pages.update(page_id=page_id, archived=True)
                archived_count += 1
            except Exception as e:
                print(f"   Warning: Could not archive page {page_id[:8]}: {e}")
        
        print(f"\n✅ Archived {archived_count} test pages")
    
    def print_final_report(self):
        """Print final test report"""
        print("\n═══════════════════════════════════════════════════════")
        print("FINAL TEST REPORT - 3 DATABASE SETUP")
        print("═══════════════════════════════════════════════════════")
        
        print(f"{'TEST':<35} | {'RESULT':<6} | {'TIME'}")
        print("-" * 55)
        
        all_passed = True
        for test_name, (result, time_ms) in self.test_results.items():
            print(f"{test_name:<35} | {result:<6} | {time_ms}ms")
            if result == "FAIL":
                all_passed = False
        
        print("\n" + "=" * 55)
        
        if all_passed:
            print("✅ NOTION INTEGRATION FULLY OPERATIONAL")
            print("\nDatabases Active:")
            print("  ✅ Routine DB - Tasks, habits, gratitude, memory")
            print("  ✅ Research DB - Research sessions, summaries")
            print("  ✅ Content DB - LinkedIn, social media content")
            print("\nReady to wire into LangGraph workflows!")
        else:
            failed_tests = [name for name, (result, _) in self.test_results.items() if result == "FAIL"]
            print("❌ SOME TESTS FAILED")
            print(f"Failed tests: {', '.join(failed_tests)}")


async def main():
    """Run 3-database tests"""
    print("Starting ASTA Notion Integration Tests (3 Databases)...\n")
    
    tester = ThreeDatabaseTests()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
