"""
Demo: ASTA Notion Integration
Shows how users can interact with ASTA to check and modify Notion databases.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.app.core.supervisor import run_supervisor


async def demo():
    """Demonstrate ASTA's Notion integration capabilities."""
    
    print("\n" + "="*70)
    print("🤖 ASTA NOTION INTEGRATION DEMO")
    print("="*70)
    print("\nThis demo shows how ASTA can check and modify your Notion databases")
    print("through natural conversation.\n")
    
    demos = [
        {
            "title": "📋 Check Today's Tasks",
            "query": "What are my tasks for today?",
            "workflow": "routine",
            "description": "ASTA reads from Notion Routine DB and lists your pending tasks"
        },
        {
            "title": "➕ Add a New Task",
            "query": "Add a task: Call the dentist at 2 PM tomorrow",
            "workflow": "routine",
            "description": "ASTA creates a new task in Notion Routine DB"
        },
        {
            "title": "🔍 Research a Topic",
            "query": "Research the best practices for LangGraph workflows",
            "workflow": "research",
            "description": "ASTA researches the web and saves findings to Notion Research DB"
        },
        {
            "title": "📝 Create LinkedIn Content",
            "query": "Write a LinkedIn post about AI agent workflows",
            "workflow": "content",
            "description": "ASTA generates content and logs it to Notion Content DB"
        }
    ]
    
    for i, demo in enumerate(demos, 1):
        print(f"\n{'─'*70}")
        print(f"Demo {i}/4: {demo['title']}")
        print(f"{'─'*70}")
        print(f"📝 User asks: \"{demo['query']}\"")
        print(f"🎯 Expected workflow: {demo['workflow']}")
        print(f"💡 What happens: {demo['description']}")
        print(f"\n⏳ Processing...")
        
        result = await run_supervisor(
            session_id=f"demo-{i}",
            user_input=demo['query'],
            workflow_hint=demo['workflow']
        )
        
        print(f"\n✅ Workflow executed: {result.get('workflow_type', 'unknown')}")
        print(f"🔧 Tools used: {', '.join(result.get('tools_used', []))}")
        
        if result.get('notion_page_id'):
            print(f"📄 Notion Page ID: {result['notion_page_id']}")
        
        response = result.get('asta_response', 'No response')
        print(f"\n🤖 ASTA's response:")
        print(f"   {response[:200]}{'...' if len(response) > 200 else ''}")
        
        if i < len(demos):
            print(f"\n{'─'*70}")
            input("Press Enter to continue to next demo...")
    
    print(f"\n{'='*70}")
    print("✅ DEMO COMPLETE!")
    print("="*70)
    print("\n📚 Key Takeaways:")
    print("  1. ASTA automatically routes queries to the right workflow")
    print("  2. Workflows interact with Notion databases seamlessly")
    print("  3. All operations happen through natural conversation")
    print("  4. No manual API calls needed - just ask ASTA!")
    print("\n💡 Try it yourself:")
    print("  - Start the ASTA backend: python -m backend.app.main")
    print("  - Send requests to /api/chat endpoint")
    print("  - Or use the mobile app to talk to ASTA")
    print("\n🎉 Notion integration is LIVE and READY!\n")


if __name__ == "__main__":
    asyncio.run(demo())
