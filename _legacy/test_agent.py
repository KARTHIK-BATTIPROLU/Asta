import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
# Fix import to point to the correct module path
from reminder_agent.mongo import mongo_handler

# We'll mock the Telegram part or just assume it fails safely if keys are invalid for dev testing
# But 'mongo' logic is critical here.

class TestReminderLogic(unittest.TestCase):
    
    def setUp(self):
        # Clean up test reminders
        mongo_handler.collection.delete_many({"text": {"$regex": "^TEST_REMINDER"}})

    def test_due_reminders(self):
        """Test retrieving due reminders"""
        # Create a past reminder
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        res = mongo_handler.collection.insert_one({
            "text": "TEST_REMINDER_PAST",
            "remind_at": past_time,
            "status": "pending",
            "created_at": datetime.now(timezone.utc)
        })
        
        # Create future reminder
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mongo_handler.collection.insert_one({
            "text": "TEST_REMINDER_FUTURE",
            "remind_at": future_time,
            "status": "pending",
            "created_at": datetime.now(timezone.utc)
        })
        
        due = mongo_handler.get_due_reminders()
        
        found = any(r["_id"] == res.inserted_id for r in due)
        self.assertTrue(found, "Should find past reminder")
        
        # Should not find future
        found_future = any(r["text"] == "TEST_REMINDER_FUTURE" for r in due)
        self.assertFalse(found_future, "Should NOT find future reminder")

    def test_claim_atomicity(self):
        """Test claiming logic"""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        res = mongo_handler.collection.insert_one({
            "text": "TEST_REMINDER_CLAIM",
            "remind_at": past_time,
            "status": "pending",
            "created_at": datetime.now(timezone.utc)
        })
        
        # First claim should succeed
        claimed1 = mongo_handler.claim_reminder(res.inserted_id)
        self.assertIsNotNone(claimed1)
        self.assertEqual(claimed1["status"], "sending")
        
        # Second claim should fail (already sending)
        claimed2 = mongo_handler.claim_reminder(res.inserted_id)
        self.assertIsNone(claimed2)

    def test_stale_recovery(self):
        """Test recovering stuck reminders"""
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10) # 10 mins ago (threshold is 5)
        res = mongo_handler.collection.insert_one({
            "text": "TEST_REMINDER_STALE",
            "remind_at": stale_time, 
            "status": "sending",
            "claimed_at": stale_time,
            "created_at": datetime.now(timezone.utc)
        })
        
        mongo_handler.recover_stale_reminders()
        
        updated = mongo_handler.collection.find_one({"_id": res.inserted_id})
        self.assertEqual(updated["status"], "pending", "Should revert to pending")

    def tearDown(self):
        # Cleanup
        mongo_handler.collection.delete_many({"text": {"$regex": "^TEST_REMINDER"}})

if __name__ == '__main__':
    unittest.main()