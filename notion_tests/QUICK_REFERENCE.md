# Quick Reference — Notion Integration Fix

## 🚨 The Problem
4 database IDs in `.env` are **PAGE IDs** (wrong) instead of **DATABASE IDs** (correct).

## ✅ The Fix (5 minutes)

### 1. Get Database IDs

For each database (Research, Developer, Content, YouTube):

```
Open Notion → Find the database → Click ⋮⋮ menu → Copy link to view
```

Extract the 32-char ID from the URL:
```
https://notion.so/workspace/DATABASE_ID?v=VIEW_ID
                           ^^^^^^^^^^^^^^^^^^^^^^^^
```

### 2. Update .env

**Option A: Manual**
```bash
# Edit .env and replace these 4 lines:
NOTION_RESEARCH_DB=<new_database_id>
NOTION_DEVELOPER_DB=<new_database_id>
NOTION_CONTENT_DB=<new_database_id>
NOTION_YOUTUBE_DB=<new_database_id>
```

**Option B: Helper Script**
```bash
cd notion_tests
python update_database_ids.py
```

### 3. Verify

```bash
cd notion_tests
python diagnose_notion.py
```

Should see:
```
✅ Valid DATABASE: Research DB
✅ Valid DATABASE: Developer DB
✅ Valid DATABASE: Content DB (LinkedIn)
✅ Valid DATABASE: YouTube DB
✅ Valid DATABASE: ASTA Routine
```

### 4. Test

```bash
cd notion_tests
python test_notion_live.py
```

All 16 tests should pass ✅

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| `README.md` | Start here — overview and instructions |
| `HOW_TO_GET_DATABASE_IDS.md` | Visual guide with screenshots |
| `EXECUTIVE_SUMMARY.md` | High-level findings and recommendations |
| `PHASE_1_AUDIT_REPORT.md` | Detailed technical audit |

---

## 🔧 Tools

| Script | Purpose |
|--------|---------|
| `diagnose_notion.py` | Check if IDs are pages or databases |
| `update_database_ids.py` | Interactive helper to update .env |
| `test_notion_live.py` | Full test suite (16 tests) |

---

## ❓ Common Questions

**Q: How do I know if I have the right ID?**  
A: Run `python diagnose_notion.py` — it will tell you if each ID is a page or database.

**Q: Where is the ⋮⋮ menu?**  
A: On the database toolbar (top-right), NOT on the page. Look for six dots, not three.

**Q: What if I can't find the database?**  
A: The database is inside the page. Open the page, then look for a table/board/list view.

**Q: Can I use the page URL?**  
A: No! You need the database URL. Click ⋮⋮ on the database itself, not the page.

---

## 🎯 Current Status

| Database | Current ID | Type | Status |
|----------|-----------|------|--------|
| RESEARCH | `340337e75d1780e69b94e3c3f04f932e` | Page | ❌ Wrong |
| DEVELOPER | `340337e75d178069825ce1c860a3a9d8` | Page | ❌ Wrong |
| CONTENT | `340337e75d17804cafc7d5df3202ca06` | Page | ❌ Wrong |
| YOUTUBE | `340337e75d17807d9dc4d605b9930115` | Page | ❌ Wrong |
| ROUTINE | `c688a60c-80fb-4080-b51c-5085c1f55081` | Database | ✅ Correct |

---

## 🚀 After Fix

Once all IDs are correct:
- ✅ All 16 tests will pass
- ✅ ASTA can read/write all Notion databases
- ✅ Ready to wire into LangGraph workflows
- ✅ No code changes needed

---

**Need help?** Read `HOW_TO_GET_DATABASE_IDS.md` for a visual guide.
