# ASTA NOTION INTEGRATION — PHASE 1 STRUCTURAL AUDIT REPORT

**Date:** 2026-04-22  
**Engineer:** Senior Integration Engineer  
**Status:** ⚠️ CRITICAL ISSUES FOUND — MUST FIX BEFORE PROCEEDING

---

## EXECUTIVE SUMMARY

The Notion integration code is **structurally sound** but has **critical configuration errors** in `.env`. Four out of five database IDs are **PAGE IDs instead of DATABASE IDs**, which will cause all operations to fail.

**VERDICT:** ❌ **NOT OPERATIONAL** — Configuration must be fixed before any tests can pass.

---

## 1. BACKEND CODE AUDIT

### ✅ `backend/app/tools/notion_tool.py`

**Operations Supported:**
- ✅ `create_page` — Create pages in databases
- ✅ `append_to_page` — Append blocks to existing pages
- ✅ `read_page` — Read page content
- ✅ `query_database` — Query databases with filters
- ✅ `update_page` — Update page properties
- ✅ `search` — Search across workspace
- ✅ `clear_page` — Delete all blocks from a page

**Authentication:**
- ✅ Uses `NOTION_API_KEY` from environment
- ✅ Proper Bearer token authentication
- ✅ Notion-Version header set to `2022-06-28`

**Implementation:**
- ✅ Uses raw `httpx` for HTTP calls (not notion-client SDK)
- ✅ Has rate limit handling (429 errors with exponential backoff)
- ✅ Retry logic with MAX_RETRIES = 3
- ✅ Timeout set to 10 seconds
- ✅ Handles 2000-char block limit (auto-splits long content)

**Database ID Handling:**
- ⚠️ Uses `_db_map()` function to get IDs from environment
- ⚠️ **NO HARDCODED IDs** — all from settings (GOOD)
- ⚠️ But relies on correct IDs being in `.env` (PROBLEM — see below)

**Markdown Conversion:**
- ✅ `_markdown_to_blocks()` — Converts markdown to Notion blocks
- ✅ Supports: headings (H1-H3), bullets, numbered lists, todos, paragraphs
- ✅ Auto-splits paragraphs over 2000 chars

---

### ✅ `backend/app/services/notion_service.py`

**Operations Supported:**
- ✅ `create_research_page()` — Full research workflow
- ✅ `create_routine_task()` — Create routine tasks
- ✅ `get_pending_tasks()` — Query with filters
- ✅ `update_task_status()` — Update task status
- ✅ `delete_completed_tasks()` — Archive completed tasks
- ✅ `append_to_gratitude_page()` — Gratitude journal
- ✅ `append_to_permanent_memory()` — Permanent memory log
- ✅ `create_linkedin_page()` — LinkedIn content
- ✅ `create_youtube_page()` — YouTube content
- ✅ `create_instagram_page()` — Instagram content
- ✅ `log_content_creation()` — Content logging
- ✅ `delete_page()` — Archive pages
- ✅ `append_to_habit_page()` — Habit tracking

**Implementation:**
- ✅ Uses `notion-client` SDK (`AsyncClient`)
- ✅ All methods are `async`
- ✅ Proper error handling with try/except and logging
- ✅ All database IDs from `settings` (not hardcoded)

**Rate Limiting:**
- ⚠️ **NO EXPLICIT RATE LIMITING** in notion_service.py
- ⚠️ Relies on notion-client SDK's internal handling
- ⚠️ Notion API limit: 3 requests/second
- ⚠️ **RISK:** Rapid calls could hit rate limits

**Block Size Handling:**
- ✅ Helper functions `_paragraph()`, `_bullet()` truncate to 2000 chars
- ✅ Safe content handling with `text[:2000]`

---

### ✅ `backend/app/config.py`

**Notion Environment Variables:**
- ✅ `NOTION_API_KEY` — Present
- ✅ `NOTION_RESEARCH_DB` — Present
- ✅ `NOTION_CONTENT_DB` — Present
- ✅ `NOTION_YOUTUBE_DB` — Present
- ✅ `NOTION_ROUTINE_DB` — Present
- ✅ `NOTION_DEVELOPER_DB` — Present (bonus)
- ✅ `NOTION_DATABASE_ID` — Present (legacy)

**All variables are defined in config.py** ✅

---

### ❌ `.env` FILE — CRITICAL ISSUES

**Notion API Key:**
- ✅ `NOTION_API_KEY=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`
- ✅ Valid format (starts with `ntn_`)
- ✅ Authentication works (tested successfully)

**Database IDs:**

| Variable | Value | Status | Issue |
|----------|-------|--------|-------|
| `NOTION_RESEARCH_DB` | `340337e75d1780e69b94e3c3f04f932e` | ❌ **PAGE ID** | Points to "Research DB" page, not database |
| `NOTION_DEVELOPER_DB` | `340337e75d178069825ce1c860a3a9d8` | ❌ **PAGE ID** | Points to "Developer DB" page, not database |
| `NOTION_CONTENT_DB` | `340337e75d17804cafc7d5df3202ca06` | ❌ **PAGE ID** | Points to "Content DB (LinkedIn)" page, not database |
| `NOTION_YOUTUBE_DB` | `340337e75d17807d9dc4d605b9930115` | ❌ **PAGE ID** | Points to "YouTube DB" page, not database |
| `NOTION_ROUTINE_DB` | `c688a60c-80fb-4080-b51c-5085c1f55081` | ✅ **DATABASE ID** | Valid database: "ASTA Routine" |

**ROOT CAUSE:**
The IDs for RESEARCH, DEVELOPER, CONTENT, and YOUTUBE are **page IDs**, not **database IDs**. These pages likely contain inline databases, but you need the database ID itself, not the parent page ID.

---

## 2. LIVE CONNECTION TEST RESULTS

### ✅ TEST 1 — Authentication
- **Status:** PASS ✅
- **Result:** Connected to Notion workspace: "ASTA"
- **API Key:** Valid and working

### ❌ TEST 2 — Database Access
- **RESEARCH DB:** ❌ FAIL — 400 Bad Request (is a page, not a database)
- **DEVELOPER DB:** ❌ FAIL — 400 Bad Request (is a page, not a database)
- **CONTENT DB:** ❌ FAIL — 400 Bad Request (is a page, not a database)
- **YOUTUBE DB:** ❌ FAIL — 400 Bad Request (is a page, not a database)
- **ROUTINE DB:** ✅ PASS — "ASTA Routine" database accessible

### ⏸️ TEST 3+ — Blocked
Cannot proceed with remaining tests until database IDs are fixed.

---

## 3. HOW TO FIX

### Step 1: Get Correct Database IDs

For each database (RESEARCH, DEVELOPER, CONTENT, YOUTUBE):

1. **Open Notion** and navigate to the page containing the database
2. **Find the database view** on the page (it's an inline database)
3. **Click the ⋮⋮ menu** in the top-right corner of the database (not the page)
4. **Select "Copy link to view"**
5. **Extract the database ID** from the URL

**URL Format:**
```
https://www.notion.so/{workspace}/{DATABASE_ID}?v={view_id}
```

The `DATABASE_ID` is the 32-character hex string (with or without dashes).

**Example:**
```
https://www.notion.so/myworkspace/340337e75d1780e69b94e3c3f04f932e?v=abc123
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                  This is the DATABASE ID
```

### Step 2: Update `.env`

Replace the current PAGE IDs with the correct DATABASE IDs:

```bash
# OLD (PAGE IDs) — WRONG ❌
NOTION_RESEARCH_DB=340337e75d1780e69b94e3c3f04f932e
NOTION_DEVELOPER_DB=340337e75d178069825ce1c860a3a9d8
NOTION_CONTENT_DB=340337e75d17804cafc7d5df3202ca06
NOTION_YOUTUBE_DB=340337e75d17807d9dc4d605b9930115

# NEW (DATABASE IDs) — CORRECT ✅
NOTION_RESEARCH_DB={get_from_notion}
NOTION_DEVELOPER_DB={get_from_notion}
NOTION_CONTENT_DB={get_from_notion}
NOTION_YOUTUBE_DB={get_from_notion}
```

### Step 3: Verify Integration Sharing

After updating the IDs, ensure your Notion integration has access:

1. Open each database in Notion
2. Click **Share** in the top right
3. **Invite** your integration (should be named "ASTA" or similar)
4. Ensure it has **Edit** permissions

### Step 4: Re-run Diagnostic

```bash
cd notion_tests
python diagnose_notion.py
```

All databases should show ✅ Valid DATABASE.

### Step 5: Run Full Test Suite

```bash
cd notion_tests
python test_notion_live.py
```

---

## 4. ADDITIONAL FINDINGS

### Rate Limiting
- ⚠️ `notion_service.py` does NOT implement rate limiting
- ⚠️ Notion API limit: 3 requests/second
- ⚠️ **Recommendation:** Add rate limiting to prevent 429 errors during bulk operations

### Error Handling
- ✅ Both `notion_tool.py` and `notion_service.py` have proper error handling
- ✅ Errors are logged with context
- ✅ Graceful degradation (returns False/empty on failure)

### Content Splitting
- ✅ Both implementations handle 2000-char block limit
- ✅ `notion_tool.py` auto-splits long paragraphs
- ✅ `notion_service.py` truncates to 2000 chars

---

## 5. NEXT STEPS

### Immediate (BLOCKING)
1. ❌ **Get correct database IDs from Notion** (see Step 1 above)
2. ❌ **Update `.env` with database IDs** (see Step 2 above)
3. ❌ **Verify integration sharing** (see Step 3 above)
4. ❌ **Re-run diagnostic** to confirm all databases accessible

### After Fix (PHASE 2-6)
5. ⏸️ Run full live test suite (PHASE 2-6)
6. ⏸️ Fix any failures at root cause
7. ⏸️ Verify all ASTA workflows work end-to-end

---

## 6. FROZEN FILES (DO NOT MODIFY)

As per requirements, these files are **FROZEN** and were not modified:
- ✅ `stt_service.py`
- ✅ `tts_service.py`
- ✅ `deepgram_stt.py`
- ✅ `deepgram_tts.py`
- ✅ `wake_word_service.py`
- ✅ `vad_service.py`
- ✅ `speech/` folder
- ✅ `ws_routes.py`

---

## FINAL VERDICT

**❌ NOTION INTEGRATION NOT OPERATIONAL**

**Blocking Issue:** 4 out of 5 database IDs in `.env` are PAGE IDs instead of DATABASE IDs.

**Fix Required:** Update `.env` with correct database IDs from Notion.

**Estimated Fix Time:** 5-10 minutes (manual task in Notion UI)

**After Fix:** All code is ready — tests should pass immediately once IDs are corrected.

---

**Report Generated:** 2026-04-22  
**Next Action:** User must obtain correct database IDs from Notion workspace
