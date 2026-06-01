# ASTA Notion Integration Testing

## 🚨 CRITICAL ISSUE FOUND

**Status:** ❌ **NOT OPERATIONAL**  
**Issue:** 4 out of 5 database IDs in `.env` are **PAGE IDs** instead of **DATABASE IDs**

---

## Quick Summary

✅ **Code is perfect** — Both `notion_tool.py` and `notion_service.py` are well-implemented  
✅ **API key works** — Successfully authenticated with Notion  
❌ **Configuration broken** — Wrong database IDs in `.env`

**Only ROUTINE_DB works.** RESEARCH, DEVELOPER, CONTENT, and YOUTUBE are page IDs.

---

## How to Fix (5 minutes)

### Step 1: Get Correct Database IDs

For each database, you need to get the **database ID**, not the page ID:

1. Open **Notion** in your browser
2. Navigate to the page containing the database (e.g., "Research DB")
3. **Click on the database** itself (not the page)
4. Click the **⋮⋮ menu** in the top-right corner of the database
5. Select **"Copy link to view"**
6. The URL will look like:
   ```
   https://www.notion.so/workspace/DATABASE_ID?v=VIEW_ID
   ```
7. Copy the `DATABASE_ID` (32-character hex string)

### Step 2: Update .env

**Option A: Manual Edit**

Open `.env` and replace these lines:

```bash
# Current (WRONG - these are page IDs)
NOTION_RESEARCH_DB=340337e75d1780e69b94e3c3f04f932e
NOTION_DEVELOPER_DB=340337e75d178069825ce1c860a3a9d8
NOTION_CONTENT_DB=340337e75d17804cafc7d5df3202ca06
NOTION_YOUTUBE_DB=340337e75d17807d9dc4d605b9930115

# New (CORRECT - database IDs from Notion)
NOTION_RESEARCH_DB=<paste_database_id_here>
NOTION_DEVELOPER_DB=<paste_database_id_here>
NOTION_CONTENT_DB=<paste_database_id_here>
NOTION_YOUTUBE_DB=<paste_database_id_here>
```

**Option B: Use Helper Script**

```bash
cd notion_tests
python update_database_ids.py
```

The script will prompt you for each database ID and update `.env` automatically.

### Step 3: Verify Integration Access

Make sure your Notion integration has access to each database:

1. Open each database in Notion
2. Click **Share** (top right)
3. **Invite** your integration (should be named "ASTA")
4. Ensure it has **Edit** permissions

### Step 4: Verify Fix

```bash
cd notion_tests
python diagnose_notion.py
```

You should see:
```
✅ Valid DATABASE: Research DB
✅ Valid DATABASE: Developer DB
✅ Valid DATABASE: Content DB (LinkedIn)
✅ Valid DATABASE: YouTube DB
✅ Valid DATABASE: ASTA Routine
```

### Step 5: Run Full Test Suite

```bash
cd notion_tests
python test_notion_live.py
```

All tests should pass ✅

---

## Files in This Directory

| File | Purpose |
|------|---------|
| `PHASE_1_AUDIT_REPORT.md` | Detailed structural audit and findings |
| `diagnose_notion.py` | Diagnostic tool to check database IDs |
| `update_database_ids.py` | Helper script to update .env |
| `test_notion_live.py` | Full live test suite (16 tests) |
| `README.md` | This file |

---

## Test Suite Overview

Once database IDs are fixed, `test_notion_live.py` will run:

### Phase 2: Live Connection Tests
- ✅ Authentication
- ✅ Database access (all 5 databases)
- ✅ Read existing pages

### Phase 3: Write and Read Back Tests
- ✅ Create routine task
- ✅ Update task status
- ✅ Create research page with full content
- ✅ Append to existing page
- ✅ Create LinkedIn content page
- ✅ Gratitude journal append
- ✅ Query with filters

### Phase 4: ASTA Workflow Simulation
- ✅ Full routine workflow (create 3 tasks, query, update)
- ✅ Full research workflow (create page with 4 research points)
- ✅ Permanent memory append

### Phase 5: Error Handling
- ✅ Invalid database ID handling
- ✅ Long content (>2000 chars) auto-splitting
- ✅ Rate limit handling (5 rapid writes)

### Phase 6: Cleanup
- ✅ Archive all test pages
- ✅ Final report with timing

---

## What Was Audited

### ✅ `backend/app/tools/notion_tool.py`
- Uses `httpx` for HTTP calls
- Has rate limiting (429 retry with backoff)
- Supports: create, read, update, query, search, append, clear
- Auto-splits content over 2000 chars
- Markdown to Notion blocks conversion

### ✅ `backend/app/services/notion_service.py`
- Uses `notion-client` SDK (AsyncClient)
- All methods async
- Proper error handling
- All database IDs from settings (not hardcoded)
- Supports all ASTA workflows:
  - Research pages
  - Routine tasks
  - Content creation (LinkedIn, YouTube, Instagram)
  - Habit tracking
  - Permanent memory

### ✅ `backend/app/config.py`
- All 5 Notion env vars defined
- Proper Pydantic settings

### ❌ `.env`
- API key: ✅ Valid
- ROUTINE_DB: ✅ Valid database ID
- RESEARCH_DB: ❌ Page ID (not database)
- DEVELOPER_DB: ❌ Page ID (not database)
- CONTENT_DB: ❌ Page ID (not database)
- YOUTUBE_DB: ❌ Page ID (not database)

---

## Current Status

```
TEST                              | STATUS
----------------------------------|--------
Authentication                    | ✅ PASS
Database Access - ROUTINE         | ✅ PASS
Database Access - RESEARCH        | ❌ FAIL (page ID)
Database Access - DEVELOPER       | ❌ FAIL (page ID)
Database Access - CONTENT         | ❌ FAIL (page ID)
Database Access - YOUTUBE         | ❌ FAIL (page ID)
All other tests                   | ⏸️  BLOCKED
```

---

## After Fix

Once you update the database IDs:

1. All tests should pass ✅
2. ASTA can read/write all Notion databases in real-time
3. Ready to wire into LangGraph workflows
4. No code changes needed — just configuration

---

## Need Help?

**Common Issues:**

**Q: How do I know if I have the database ID vs page ID?**  
A: Run `python diagnose_notion.py` — it will tell you exactly what each ID is.

**Q: I can't find the ⋮⋮ menu on the database**  
A: Make sure you're clicking on the database itself, not the page. The database has its own menu in the top-right corner.

**Q: The integration isn't showing up when I try to share**  
A: Go to Notion Settings → Integrations → check if your integration is created. If not, create one at https://www.notion.so/my-integrations

**Q: Tests are still failing after updating IDs**  
A: Run `python diagnose_notion.py` to verify all IDs are correct. Also check that the integration has access to each database (Share → Invite integration).

---

## Contact

If you need help getting the database IDs, share your screen and I can guide you through the Notion UI.

**Next Action:** Get the correct database IDs from Notion and update `.env`
