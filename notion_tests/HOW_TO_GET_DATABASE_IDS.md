# How to Get Notion Database IDs (Not Page IDs)

## The Problem

Your `.env` currently has **PAGE IDs** instead of **DATABASE IDs**. Here's the difference:

### Page ID (What you have now ❌)
```
https://www.notion.so/workspace/340337e75d1780e69b94e3c3f04f932e
                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                This is the PAGE that contains a database
```

### Database ID (What you need ✅)
```
https://www.notion.so/workspace/340337e75d1780e69b94e3c3f04f932e?v=abc123def456
                                                                   ^^^^^^^^^^^^
                                This is the DATABASE VIEW ID (part of database URL)
```

The database ID is **different** from the page ID. The database lives **inside** the page.

---

## Step-by-Step Guide

### For Each Database (Research, Developer, Content, YouTube):

#### Step 1: Open the Page in Notion
- Open your Notion workspace
- Navigate to the page (e.g., "Research DB")
- You should see a database/table on the page

#### Step 2: Identify the Database
Look for the database view on the page. It will look like:
- A table with columns and rows
- Or a board/gallery/list view
- It has its own toolbar with filters, sorts, etc.

#### Step 3: Click on the Database (Not the Page!)
- **Don't** click the page title at the top
- **Do** click somewhere in the database area
- The database should be "active" (you'll see its toolbar)

#### Step 4: Find the Database Menu
- Look for the **⋮⋮** (six dots) icon in the **top-right corner of the database**
- This is NOT the page menu (•••) — it's the database menu (⋮⋮)
- It's usually next to the "Filter", "Sort", "Search" buttons

#### Step 5: Copy the Database Link
- Click the **⋮⋮** menu
- Select **"Copy link to view"** (or "Copy link")
- The URL is now in your clipboard

#### Step 6: Extract the Database ID
The URL will look like one of these:

**Format 1: Full URL**
```
https://www.notion.so/workspace/DATABASE_ID?v=VIEW_ID
```

**Format 2: Short URL**
```
https://notion.so/DATABASE_ID?v=VIEW_ID
```

The `DATABASE_ID` is the **32-character hex string** before the `?v=`.

**Example:**
```
https://www.notion.so/myworkspace/15d4a8b3c9e74f2a8b1c3d5e6f7a8b9c?v=abc123
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                  This is your DATABASE_ID
```

Copy just the database ID part (with or without dashes, both work):
- With dashes: `15d4a8b3-c9e7-4f2a-8b1c-3d5e6f7a8b9c`
- Without dashes: `15d4a8b3c9e74f2a8b1c3d5e6f7a8b9c`

---

## Visual Guide

```
┌─────────────────────────────────────────────────────────────┐
│ 📄 Research DB                                    ••• (page) │  ← Page title
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  This is some text on the page...                            │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 🗂️ Research Database          🔍 ⚡ ⋮⋮ (database)    │  │  ← Database toolbar
│  ├───────────────────────────────────────────────────────┤  │
│  │ Name          │ Date       │ Status    │ Workflow    │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ Research 1    │ 2026-04-20 │ Completed │ Research    │  │
│  │ Research 2    │ 2026-04-21 │ Draft     │ Research    │  │
│  │ Research 3    │ 2026-04-22 │ Completed │ Research    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘

Click the ⋮⋮ menu on the DATABASE (not the ••• on the page!)
```

---

## Common Mistakes

### ❌ Mistake 1: Copying the Page URL
```
Right-click page title → Copy link
Result: Page ID (wrong!)
```

### ❌ Mistake 2: Using the Page Menu
```
Click ••• (three dots) at top of page
Result: Page menu, not database menu
```

### ✅ Correct: Using the Database Menu
```
Click ⋮⋮ (six dots) on the database toolbar
Select "Copy link to view"
Result: Database ID (correct!)
```

---

## Quick Test

After you get a database ID, you can test it:

```bash
cd notion_tests
python diagnose_notion.py
```

If you see:
- ✅ `Valid DATABASE: Research DB` — Correct!
- ❌ `This is a PAGE, not a database` — Wrong ID, try again

---

## What If I Can't Find the ⋮⋮ Menu?

### Option 1: Open Database as Full Page
1. Hover over the database
2. Click the **↗️** icon (open as page)
3. The database will open in full-page view
4. Now the ⋮⋮ menu should be visible in the top-right

### Option 2: Use the Database URL Directly
1. Open the database in full-page view (↗️ icon)
2. Copy the URL from your browser's address bar
3. The URL contains the database ID

### Option 3: Check Notion Settings
1. Go to Settings & Members → Integrations
2. Click on your integration (ASTA)
3. Under "Selected pages", you should see the databases
4. Click on a database → Copy link

---

## Need Help?

If you're still stuck:

1. Take a screenshot of your Notion page showing the database
2. Share it and I can help identify where the ⋮⋮ menu is
3. Or share the page URL and I can help extract the database ID

---

## Summary

| What | Where | How |
|------|-------|-----|
| **Page ID** | Page URL | Right-click page title → Copy link |
| **Database ID** | Database menu | Click ⋮⋮ on database → Copy link to view |

**You need:** Database ID (from the ⋮⋮ menu on the database itself)  
**You have:** Page ID (from the page URL)

---

## After Getting All 4 Database IDs

Update your `.env`:

```bash
NOTION_RESEARCH_DB=<database_id_from_research_db>
NOTION_DEVELOPER_DB=<database_id_from_developer_db>
NOTION_CONTENT_DB=<database_id_from_content_db>
NOTION_YOUTUBE_DB=<database_id_from_youtube_db>
```

Then run:
```bash
cd notion_tests
python diagnose_notion.py  # Verify all IDs are correct
python test_notion_live.py  # Run full test suite
```

All tests should pass! ✅
