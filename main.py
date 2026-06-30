# main.py - Complete Production Version with Fixed Path
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import os
import asyncio
import base64
import hashlib
import hmac
import json
import httpx
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import subprocess
import sys

load_dotenv()

app = FastAPI()

# ============================================================
# DATABASE SETUP
# ============================================================

def init_db():
    """Create the database table if it doesn't exist"""
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        iid TEXT,
        title TEXT,
        description TEXT,
        state TEXT,
        author TEXT,
        project TEXT,
        url TEXT,
        created_at TEXT,
        received_at TEXT,
        synced_to_huly TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ Database initialized")

def save_issue_to_db(iid, title, description, state, author, project, url, created_at, synced=False):
    """Save an issue to the database"""
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('''INSERT INTO issues 
                 (iid, title, description, state, author, project, url, created_at, received_at, synced_to_huly)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (iid, title, description, state, author, project, url, created_at, 
               datetime.now().isoformat(), 'yes' if synced else 'no'))
    conn.commit()
    conn.close()
    print(f"💾 Issue #{iid} saved to database")

def get_issues_from_db(limit=100):
    """Get recent issues from the database"""
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('''SELECT iid, title, description, state, author, project, url, received_at, synced_to_huly
                 FROM issues ORDER BY id DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return [{
        'iid': row[0],
        'title': row[1],
        'description': row[2],
        'state': row[3],
        'author': row[4],
        'project': row[5],
        'url': row[6],
        'received_at': row[7],
        'synced_to_huly': row[8]
    } for row in rows]

def get_stats():
    """Get statistics from database"""
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM issues')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM issues WHERE state = "opened"')
    open_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM issues WHERE date(received_at) = date("now")')
    today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM issues WHERE synced_to_huly = "yes"')
    synced = c.fetchone()[0]
    conn.close()
    return {'total': total, 'open': open_count, 'today': today, 'synced': synced}

# Initialize database on startup
init_db()

# ============================================================
# CONFIGURATION
# ============================================================

GITLAB_API_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
GITLAB_API_TOKEN = os.getenv("GITLAB_API_TOKEN")

HULY_URL = os.getenv("HULY_URL", "https://huly.app")
HULY_WORKSPACE = os.getenv("HULY_WORKSPACE")
HULY_EMAIL = os.getenv("HULY_EMAIL")
HULY_PASSWORD = os.getenv("HULY_PASSWORD")
HULY_PROJECT_IDENTIFIER = os.getenv("HULY_PROJECT_IDENTIFIER")

HULY_CONFIGURED = bool(HULY_EMAIL and HULY_PASSWORD and HULY_WORKSPACE)
HULY_READY = bool(HULY_CONFIGURED and HULY_PROJECT_IDENTIFIER)

# ============================================================
# FIND BRIDGE SCRIPT (FIXED)
# ============================================================

def find_bridge_script():
    """Find huly_api.js in the project directory"""
    # Get the directory where main.py is located
    current_dir = Path(__file__).resolve().parent
    bridge_path = current_dir / "huly_api.js"
    
    # If not found in current dir, try the working directory
    if not bridge_path.exists():
        bridge_path = Path.cwd() / "huly_api.js"
    
    print(f"🔍 Bridge script path: {bridge_path}")
    print(f"📁 File exists: {bridge_path.exists()}")
    
    return bridge_path

BRIDGE_SCRIPT = find_bridge_script()

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Check if the service is running"""
    return {
        "message": "Huly-GitLab Sync Service is running!",
        "huly_configured": HULY_CONFIGURED,
        "huly_project_identifier": HULY_PROJECT_IDENTIFIER,
        "huly_ready_to_create_issues": HULY_READY,
        "workspace": HULY_WORKSPACE,
        "gitlab_configured": bool(GITLAB_API_TOKEN),
        "status": "ready" if HULY_READY else "needs_project_identifier",
        "stats": get_stats(),
        "bridge_script_exists": BRIDGE_SCRIPT.exists(),
        "note": None if HULY_READY else (
            "HULY_PROJECT_IDENTIFIER not set. Run: "
            "node huly_api.js --list-projects, then add it to .env"
        ),
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Web dashboard showing all received webhooks"""
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <h1>📋 Dashboard</h1>
        <p>Create <code>dashboard.html</code> in the project folder.</p>
        <p>Or use the API: <a href="/api/webhooks">/api/webhooks</a></p>
        """

@app.get("/api/webhooks")
async def get_webhooks():
    """API endpoint to get recent webhooks from database"""
    issues = get_issues_from_db(100)
    return {"webhooks": issues, "stats": get_stats()}

@app.get("/test/gitlab")
async def test_gitlab():
    """Test GitLab connection"""
    if not GITLAB_API_TOKEN:
        return {"status": "error", "message": "GitLab token not configured"}

    headers = {
        "Authorization": f"Bearer {GITLAB_API_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{GITLAB_API_URL}/projects",
                headers=headers,
                params={"membership": True, "per_page": 5}
            )

            if response.status_code == 200:
                projects = response.json()
                return {
                    "status": "connected",
                    "projects": [
                        {"id": p["id"], "name": p["name"], "url": p["web_url"]}
                        for p in projects
                    ]
                }
            else:
                return {"status": "error", "code": response.status_code, "message": response.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

@app.get("/logs")
async def get_logs():
    """Get recent logs (simplified)"""
    return {
        "message": "Check the console where main.py is running for full logs.",
    }

@app.get("/test/huly")
async def test_huly():
    """Test Huly configuration"""
    return {
        "status": "ready" if HULY_READY else ("configured" if HULY_CONFIGURED else "not_configured"),
        "workspace": HULY_WORKSPACE,
        "email": HULY_EMAIL,
        "project_identifier": HULY_PROJECT_IDENTIFIER,
        "note": None if HULY_READY else "Run 'node huly_api.js --list-projects' to find your project identifier.",
    }
@app.get("/fix-sync")
async def fix_sync():
    """Manually mark all issues as synced"""
    try:
        conn = sqlite3.connect('webhooks.db')
        c = conn.cursor()
        c.execute('UPDATE issues SET synced_to_huly = "yes" WHERE synced_to_huly = "no"')
        conn.commit()
        count = c.rowcount
        conn.close()
        return {
            "status": "success",
            "message": f"✅ Updated {count} issues to synced!",
            "updated_count": count
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
@app.post("/webhook/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str = Header(None),
    webhook_id: str = Header(None),
    webhook_timestamp: str = Header(None),
    webhook_signature: str = Header(None),
):
    """Main webhook endpoint for GitLab"""
    raw_body = await request.body()

    verified = False
    signing_token = os.getenv("GITLAB_WEBHOOK_SIGNING_TOKEN")

    # HMAC verification
    if signing_token and webhook_signature and webhook_id and webhook_timestamp:
        raw_key = base64.b64decode(signing_token.removeprefix("whsec_"))
        message = f"{webhook_id}.{webhook_timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
        digest = hmac.new(raw_key, message, hashlib.sha256).digest()
        expected = "v1," + base64.b64encode(digest).decode("utf-8")
        verified = hmac.compare_digest(expected, webhook_signature)
        print("✅ Signing token (HMAC) verified!" if verified else "❌ Signing token mismatch")
    else:
        # Fall back to secret token
        expected_token = os.getenv("GITLAB_WEBHOOK_SECRET")
        if expected_token and x_gitlab_token:
            verified = hmac.compare_digest(expected_token, x_gitlab_token)
            print("✅ Secret token verified!" if verified else "❌ Secret token mismatch")

    if not verified:
        print("❌ No valid token/signature provided")
        raise HTTPException(status_code=401, detail="Invalid or missing webhook credentials")

    payload = json.loads(raw_body)
    event_type = payload.get('object_kind')
    print(f"📨 Received webhook: {event_type}")

    if event_type in ['issue', 'work_item']:
        asyncio.create_task(process_issue_event(payload))

    return {"status": "success", "event": event_type}

# ============================================================
# WEBHOOK PROCESSING
# ============================================================

async def process_issue_event(payload: dict):
    """Process a GitLab issue event"""
    print("🔍 Processing issue event...")

    issue_data = payload.get('object_attributes', {})
    project_data = payload.get('project', {})

    if not issue_data:
        print("❌ No issue data found")
        return

    # Extract data
    issue_iid = issue_data.get('iid')
    title = issue_data.get('title')
    description = issue_data.get('description', '')
    state = issue_data.get('state')
    author_username = issue_data.get('author', {}).get('username', 'unknown')
    project_name = project_data.get('name', 'unknown')
    gitlab_url = issue_data.get('url')
    created_at = issue_data.get('created_at')

    print(f"📝 Issue: #{issue_iid} - {title}")
    print(f"   State: {state} | Author: {author_username} | Project: {project_name}")

    # Save to database immediately
    save_issue_to_db(issue_iid, title, description, state, author_username, project_name, gitlab_url, created_at, synced=False)

    # Try to create in Huly
    status_map = {"opened": "Todo", "closed": "Done", "reopened": "Todo"}
    huly_status = status_map.get(state, "Todo")
    huly_description = f"{description}\n\n---\n**Source**: GitLab\n**Issue**: #{issue_iid}\n**URL**: {gitlab_url}"

    success, result = await send_to_huly(title, huly_description, huly_status)

    if success:
        print(f"✅ Created in Huly: {result}")
        # Update database to mark as synced
        conn = sqlite3.connect('webhooks.db')
        c = conn.cursor()
        c.execute('UPDATE issues SET synced_to_huly = "yes" WHERE iid = ?', (issue_iid,))
        conn.commit()
        conn.close()
    else:
        print(f"⚠️  Huly creation failed ({result}) — saved to database")
        log_issue(issue_iid, title, description, state, author_username, project_name, gitlab_url, created_at)

async def send_to_huly(title: str, description: str, status: str) -> tuple[bool, str]:
    """Create the issue in Huly by calling the Node MCP bridge."""
    if not HULY_READY:
        return False, "Huly not fully configured"

    if not BRIDGE_SCRIPT.exists():
        return False, f"Bridge script not found at {BRIDGE_SCRIPT}"

    # Use which to find node
    node_cmd = "node"
    if sys.platform == "win32":
        node_cmd = "node.exe"
    
    # Try to find node in PATH
    import shutil
    node_path = shutil.which(node_cmd)
    if node_path:
        node_cmd = node_path
        print(f"🔍 Found node at: {node_cmd}")

    proc = await asyncio.create_subprocess_exec(
        node_cmd, str(BRIDGE_SCRIPT), title, description, status,
        cwd=str(BRIDGE_SCRIPT.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, "timed out after 180s waiting for Huly"

    if stderr:
        for line in stderr.decode(errors="replace").splitlines():
            print(f"   [huly bridge] {line}")

    if proc.returncode == 0:
        return True, stdout.decode(errors="replace").strip()
    else:
        return False, stdout.decode(errors="replace").strip() or f"node exited with code {proc.returncode}"

# ============================================================
# FALLBACK LOGGING
# ============================================================

def log_issue(issue_iid, title, description, state, author, project, url, created):
    """Log issue with full details"""
    print("\n" + "=" * 60)
    print("📋 ISSUE SAVED TO DATABASE")
    print("=" * 60)
    print(f"🆔 Issue #: {issue_iid}")
    print(f"📝 Title: {title}")
    print(f"📊 Status: {state}")
    print(f"👤 Author: {author}")
    print(f"📂 Project: {project}")
    print(f"🔗 URL: {url}")
    print("-" * 60)
    print("📄 Description:")
    print(description if description else "  (No description)")
    print("=" * 60 + "\n")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Huly-GitLab Sync Service...")
    print("=" * 60)
    print(f"📂 GitLab: {GITLAB_API_URL}")
    print(f"📂 Huly: {HULY_URL}")
    print(f"📂 Workspace: {HULY_WORKSPACE}")
    print(f"📂 Project identifier: {HULY_PROJECT_IDENTIFIER or '(not set)'}")
    print(f"🔐 Huly ready: {'✅' if HULY_READY else '❌'}")
    print(f"🔗 Webhook: http://localhost:8000/webhook/gitlab")
    print(f"📊 Dashboard: http://localhost:8000/dashboard")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)