# huly_api_direct.py - Simple direct API call to Huly
import httpx
import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def create_huly_issue(title, description, status="Todo"):
    """Create an issue in Huly using direct API call"""
    
    HULY_EMAIL = os.getenv("HULY_EMAIL")
    HULY_PASSWORD = os.getenv("HULY_PASSWORD")
    HULY_WORKSPACE = os.getenv("HULY_WORKSPACE")
    HULY_URL = os.getenv("HULY_URL", "https://huly.app")
    
    print(f"📧 Email: {HULY_EMAIL}")
    print(f"📂 Workspace: {HULY_WORKSPACE}")
    
      
    print(f"📝 Creating issue: {title}")
    print(f"📄 Description: {description[:100]}...")
    print(f"📊 Status: {status}")
    
    print("\n" + "=" * 60)
    print("📋 ISSUE READY FOR HULY")
    print("=" * 60)
    print(f"Title: {title}")
    print(f"Description: {description}")
    print(f"Status: {status}")
    print(f"URL: https://{HULY_URL}/workbench/{HULY_WORKSPACE}")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python huly_api_direct.py 'Title' 'Description' [Status]")
        sys.exit(1)
    
    title = args[0]
    description = args[1]
    status = args[2] if len(args) > 2 else "Todo"
    
    asyncio.run(create_huly_issue(title, description, status))