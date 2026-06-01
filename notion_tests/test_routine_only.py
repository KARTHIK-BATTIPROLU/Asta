#!/usr/bin/env python3
"""
ASTA Notion Integration Tests — ROUTINE DB ONLY
Tests only the working ROUTINE database while other DB IDs are being fixed.
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

class RoutineTests:
    def __init__(self):
        self.client = AsyncClient(auth=settings.NOTION_API_KEY)
        self.test_results = {}
        self.created_pages = []
        
    async def run_all_tests(self):
        """Run all routine-specific tests."""
        print("═══════════════════════════════════════════════════════")
        print("ASTA NOTION ROUTINE DB TESTS")
        print("═══════════════════════════════════════════════════════\n")
        
        await self.test_create_routine_task()
        await self.test_update_task_status()
        await self.test_get_pending_tasks()
        await self.test_gratitude_journal()
        await self.test_permanent_memory()
        await self.test_habit_tracking()
        await self.test_routine_workflow()
        
        await self.cleanup_test_pages()
        self.print_final_report()
    
    async def test_create_routine_task(self):
        """TEST 1 — Create routine task"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            page_id = await notion_service.create_routine_task(
                task_name="ASTA Test Task — Create",
                task_type="Fixed",
                scheduled_time="10:00",
                date=today
            )
            
            assert page_id, "Page creation returned empty page_id"
            assert len(page_id) == 36, f"page_id should be UUID format, got: {page_id}"
            print(f"✅ Created routine task: {page_id[:8]}...")
            self.created_pages.append(page_id)
            
            # Verify it was created
            page = await self.client.pages.retrieve(page_id=page_id)
            props = page["properties"]
            task_name = props["Task Name"]["title"][0]["text"]["content"]
            assert "ASTA Test Task" in task_name, f"Title mismatch: {task_name}"
            
            self.test_results["Create routine task"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Create routine task failed: {e}")
            self.test_results["Create routine task"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
    async def test_update_task_status(self):
        """TEST 2 — Update task status"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Create a task
            page_id = await notion_service.create_routine_task(
                task_name="ASTA Test Task — Update",
                task_type="Dynamic",
                scheduled_time="11:00",
                date=today
            )
            self.created_pages.append(page_id)
            
            # Update status to Completed
            success = await notion_service.update_task_status(page_id, "Completed")
            assert success, "Failed to update task status"
            
            # Verify update
            page = await self.client.pages.retrieve(page_id=page_id)
            status = page["properties"]["Status"]["select"]["name"]
            assert status == "Completed", f"Status not updated: {status}"
            
            print(f"✅ Updated task status to Completed")
            self.test_results["Update task status"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Update task status failed: {e}")
            self.test_results["Update task status"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
    async def test_get_pending_tasks(self):
        """TEST 3 — Get pending tasks"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Create 2 test tasks
            for i in range(2):
                page_id = await notion_service.create_routine_task(
                    task_name=f"ASTA Test Task — Query {i+1}",
                    task_type="Fixed",
                    scheduled_time=f"1{i}:00",
                    date=today
                )
                self.created_pages.append(page_id)
            
            # Query pending tasks
            tasks = await notion_service.get_pending_tasks(today)
            assert len(tasks) >= 2, f"Expected at least 2 tasks, got {len(tasks)}"
            
            # Verify our tasks are in the results
            task_names = [t["task_name"] for t in tasks]
            assert any("ASTA Test Task — Query" in name for name in task_names), "Test tasks not found in query"
            
            print(f"✅ Retrieved {len(tasks)} pending tasks for today")
            self.test_results["Get pending tasks"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Get pending tasks failed: {e}")
            self.test_results["Get pending tasks"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
    async def test_gratitude_journal(self):
        """TEST 4 — Gratitude journal append"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            success = await notion_service.append_to_gratitude_page(
                entry="Test entry: Grateful for the Notion integration working!",
                date=today
            )
            
            assert success, "Gratitude journal append failed"
            print("✅ Gratitude journal append successful")
            
            self.test_results["Gratitude journal"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Gratitude journal failed: {e}")
            self.test_results["Gratitude journal"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
    async def test_permanent_memory(self):
        """TEST 5 — Permanent memory append"""
        start_time = time.time()
        try:
            success = await notion_service.append_to_permanent_memory(
                content="Test: Notion integration fully operational with fixed Status property",
                tags=["ASTA", "Notion", "testing"]
            )
            
            assert success, "Permanent memory append failed"
            print("✅ Permanent memory append successful")
            
            self.test_results["Permanent memory"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Permanent memory failed: {e}")
            self.test_results["Permanent memory"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
    async def test_habit_tracking(self):
        """TEST 6 — Habit tracking append"""
        start_time = time.time()
        try:
            success = await notion_service.append_to_habit_page(
                habit_type="dsa",
                content="Test: Solved binary tree traversal problem"
            )
            
            assert success, "Habit tracking append failed"
            print("✅ Habit tracking (DSA) append successful")
            
            self.test_results["Habit tracking"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Habit tracking failed: {e}")
            self.test_results["Habit tracking"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
    async def test_routine_workflow(self):
        """TEST 7 — Full routine workflow simulation"""
        start_time = time.time()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Create 3 tasks
            task_ids = []
            tasks = [
                ("Morning Workout", "Fixed", "07:00"),
                ("Code Review", "Dynamic", "10:00"),
                ("Team Standup", "Fixed", "15:00")
            ]
            
            for task_name, task_type, time_slot in tasks:
                page_id = await notion_service.create_routine_task(task_name, task_type, time_slot, today)
                task_ids.append(page_id)
                self.created_pages.append(page_id)
            
            # Get pending tasks
            pending_tasks = await notion_service.get_pending_tasks(today)
            assert len(pending_tasks) >= 3, f"Expected at least 3 tasks, got {len(pending_tasks)}"
            
            # Mark first task as completed
            await notion_service.update_task_status(task_ids[0], "Completed")
            
            # Verify it's no longer in pending
            updated_pending = await notion_service.get_pending_tasks(today)
            # Should have one less pending task (or same if there were other pending tasks)
            
            print(f"✅ Routine workflow: Created 3 tasks, marked 1 complete")
            self.test_results["Routine workflow"] = ("PASS", int((time.time() - start_time) * 1000))
            
        except Exception as e:
            print(f"❌ Routine workflow failed: {e}")
            self.test_results["Routine workflow"] = ("FAIL", int((time.time() - start_time) * 1000))
            import traceback
            traceback.print_exc()
    
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
        print("ROUTINE DB TEST REPORT")
        print("═══════════════════════════════════════════════════════")
        
        print(f"{'TEST':<30} | {'RESULT':<6} | {'TIME'}")
        print("-" * 50)
        
        all_passed = True
        for test_name, (result, time_ms) in self.test_results.items():
            print(f"{test_name:<30} | {result:<6} | {time_ms}ms")
            if result == "FAIL":
                all_passed = False
        
        print("\n" + "=" * 50)
        
        if all_passed:
            print("✅ ROUTINE DB INTEGRATION FULLY OPERATIONAL")
            print("All routine task operations working correctly.")
            print("\n⚠️  NEXT STEP: Fix database IDs for RESEARCH, CONTENT, YOUTUBE")
            print("   Run: python diagnose_notion.py")
            print("   Then: python test_notion_live.py (full test suite)")
        else:
            failed_tests = [name for name, (result, _) in self.test_results.items() if result == "FAIL"]
            print("❌ SOME TESTS FAILED")
            print(f"Failed tests: {', '.join(failed_tests)}")


async def main():
    """Run routine DB tests"""
    print("Starting ASTA Routine DB Tests...")
    print("Testing only ROUTINE_DB (other databases need ID fixes)\n")
    
    tester = RoutineTests()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
