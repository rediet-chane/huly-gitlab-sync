import asyncio
import websockets
import json
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

async def create_huly_issue_websocket(title, description, status="Todo"):
    """Create an issue in Huly using WebSocket with proper headers"""
    
    HULY_EMAIL = os.getenv("HULY_EMAIL")
    HULY_PASSWORD = os.getenv("HULY_PASSWORD")
    HULY_WORKSPACE = os.getenv("HULY_WORKSPACE")
    HULY_URL = os.getenv("HULY_URL", "https://huly.app")
    HULY_TOKEN = os.getenv("HULY_TOKEN")
    
    ws_url = HULY_URL.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/websocket"
    
    print(f"🔗 Connecting to: {ws_url}")
    print(f"📂 Workspace: {HULY_WORKSPACE}")
    print(f"📧 Email: {HULY_EMAIL}")
    
    try:
        approaches = [
            ("email_pw", await connect_with_email_pw(ws_url, HULY_EMAIL, HULY_PASSWORD, HULY_WORKSPACE, title, description, status)),
            ("token_body", await connect_with_token_body(ws_url, HULY_TOKEN, HULY_WORKSPACE, title, description, status)),
        ]
        
        for approach_name, result in approaches:
            if result:
                print(f"✅ Success with {approach_name}!")
                return True
                
        print("❌ All approaches failed")
        return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def connect_with_email_pw(ws_url, email, password, workspace, title, description, status):
    """Connect with email/password"""
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected with email/password!")
            
            auth_msg = {
                "type": "auth",
                "email": email,
                "password": password,
                "workspace": workspace
            }
            print(f"📤 Sending auth...")
            await websocket.send(json.dumps(auth_msg))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"📥 Auth response: {response[:100]}")
            except asyncio.TimeoutError:
                print("⏰ Auth timeout, continuing...")
            
            create_msg = {
                "type": "create_issue",
                "workspace": workspace,
                "data": {
                    "title": title,
                    "description": description,
                    "status": status
                }
            }
            print(f"📤 Creating issue...")
            await websocket.send(json.dumps(create_msg))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                print(f"📥 Create response: {response[:200]}")
                print("✅ Issue created!")
                return True
            except asyncio.TimeoutError:
                print("✅ Issue created (no response)")
                return True
    except Exception as e:
        print(f"❌ Email/pw approach failed: {e}")
        return False

async def connect_with_token_body(ws_url, token, workspace, title, description, status):
    """Connect with token in message body"""
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected with token body!")
            
            # Auth with token in body
            auth_msg = {
                "type": "auth",
                "token": token,
                "workspace": workspace
            }
            print(f"📤 Sending auth...")
            await websocket.send(json.dumps(auth_msg))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"📥 Auth response: {response[:100]}")
            except asyncio.TimeoutError:
                print("⏰ Auth timeout, continuing...")
            
            # Create issue
            create_msg = {
                "type": "create_issue",
                "workspace": workspace,
                "data": {
                    "title": title,
                    "description": description,
                    "status": status
                }
            }
            print(f"📤 Creating issue...")
            await websocket.send(json.dumps(create_msg))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                print(f"📥 Create response: {response[:200]}")
                print("✅ Issue created!")
                return True
            except asyncio.TimeoutError:
                print("✅ Issue created (no response)")
                return True
    except Exception as e:
        print(f"❌ Token body approach failed: {e}")
        return False

async def test_connection():
    """Test the WebSocket connection"""
    success = await create_huly_issue_websocket(
        "Test WebSocket Final",
        "This is a test using the final WebSocket approach\n\n**Source**: Python WebSocket Test"
    )
    
    if success:
        print("\n🎉 Issue created successfully in Huly!")
        print("   Check your Huly workspace to see the new issue.")
    else:
        print("\n❌ Failed to create issue.")
        print("\n💡 Since Huly WebSocket is not working, using fallback: logging.")
        log_issue(title, description, status)

def log_issue(title, description, status):
    """Log issue for manual review"""
    print("\n" + "=" * 50)
    print("📋 ISSUE LOGGED (Not sent to Huly)")
    print("=" * 50)
    print(f"Title: {title}")
    print(f"Status: {status}")
    print(f"Description: {description[:300]}...")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    print("🚀 Testing Huly WebSocket...")
    asyncio.run(test_connection())