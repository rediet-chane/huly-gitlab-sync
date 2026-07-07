from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
import os, asyncio, base64, hashlib, hmac, json, sqlite3, shutil, sys
import httpx
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# ── Config ────────────────────────────────────────────────────────────────────

GITLAB_API_URL       = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
GITLAB_API_TOKEN     = os.getenv("GITLAB_API_TOKEN")
GITLAB_PROJECT_ID    = os.getenv("GITLAB_PROJECT_ID")   # e.g. 83669199

HULY_URL             = os.getenv("HULY_URL", "https://huly.app")
HULY_WORKSPACE       = os.getenv("HULY_WORKSPACE")
HULY_EMAIL           = os.getenv("HULY_EMAIL")
HULY_PASSWORD        = os.getenv("HULY_PASSWORD")
HULY_PROJECT_IDENTIFIER = os.getenv("HULY_PROJECT_IDENTIFIER")

HULY_READY = bool(HULY_EMAIL and HULY_PASSWORD and HULY_WORKSPACE and HULY_PROJECT_IDENTIFIER)

BRIDGE_SCRIPT = Path(__file__).resolve().parent / "huly_api.js"
NODE_CMD = shutil.which("node.exe" if sys.platform == "win32" else "node") or "node"

# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS issues (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        iid              TEXT,
        title            TEXT,
        description      TEXT,
        state            TEXT,
        author           TEXT,
        project          TEXT,
        url              TEXT,
        created_at       TEXT,
        received_at      TEXT,
        synced_to_huly   TEXT DEFAULT "no",
        huly_identifier  TEXT,
        source           TEXT DEFAULT "gitlab"
    )''')
    # Migrate older databases that don't have the new columns yet
    for col, default in [("huly_identifier", None), ("source", '"gitlab"')]:
        try:
            c.execute(f'ALTER TABLE issues ADD COLUMN {col} TEXT DEFAULT {default or "NULL"}')
        except Exception:
            pass  # column already exists
    conn.commit()
    conn.close()
    print("✅ Database ready")

def save_issue(iid, title, description, state, author, project, url,
               created_at, synced=False, huly_identifier=None, source="gitlab"):
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('''INSERT INTO issues
                 (iid,title,description,state,author,project,url,
                  created_at,received_at,synced_to_huly,huly_identifier,source)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
              (iid, title, description, state, author, project, url, created_at,
               datetime.now().isoformat(), "yes" if synced else "no",
               huly_identifier, source))
    conn.commit()
    conn.close()

def mark_synced(iid, huly_identifier):
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('UPDATE issues SET synced_to_huly="yes", huly_identifier=? WHERE iid=?',
              (huly_identifier, iid))
    conn.commit()
    conn.close()

def get_known_huly_identifiers():
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('SELECT huly_identifier FROM issues WHERE huly_identifier IS NOT NULL')
    result = {row[0] for row in c.fetchall()}
    conn.close()
    return result

def get_issues(limit=100):
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    c.execute('''SELECT iid,title,description,state,author,project,url,
                        received_at,synced_to_huly,huly_identifier,source
                 FROM issues ORDER BY id DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(
        ['iid','title','description','state','author','project','url',
         'received_at','synced_to_huly','huly_identifier','source'], row
    )) for row in rows]

def get_stats():
    conn = sqlite3.connect('webhooks.db')
    c = conn.cursor()
    def q(sql): c.execute(sql); return c.fetchone()[0]
    stats = {
        'total':  q('SELECT COUNT(*) FROM issues'),
        'open':   q('SELECT COUNT(*) FROM issues WHERE state="opened"'),
        'today':  q('SELECT COUNT(*) FROM issues WHERE date(received_at)=date("now")'),
        'synced': q('SELECT COUNT(*) FROM issues WHERE synced_to_huly="yes"'),
    }
    conn.close()
    return stats

init_db()

# ── Node bridge helper ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Huly-GitLab Sync Service...")
    print("🔄 Starting background polling task (runs every 5 minutes)...")
    task = asyncio.create_task(poll_huly_forever())
    yield
    # Shutdown
    print("🛑 Shutting down...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("✅ Polling task cancelled")

app = FastAPI(lifespan=lifespan)

async def run_bridge(*args, timeout=60) -> tuple[bool, str]:
    """Run huly_api.js with given args. Returns (success, stdout_or_error)."""
    if not HULY_READY:
        return False, "Huly not configured"
    if not BRIDGE_SCRIPT.exists():
        return False, f"Bridge script not found: {BRIDGE_SCRIPT}"

    proc = await asyncio.create_subprocess_exec(
        NODE_CMD, str(BRIDGE_SCRIPT), *args,
        cwd=str(BRIDGE_SCRIPT.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        return False, f"timed out after {timeout}s"

    for line in stderr.decode(errors="replace").splitlines():
        print(f"   [bridge] {line}")

    out = stdout.decode(errors="replace").strip()
    return proc.returncode == 0, out

# ── Huly → GitLab polling (bidirectional sync) ────────────────────────────────

async def poll_huly_forever():
    """Background task: every 5 minutes, pull new Huly issues into GitLab."""
    await asyncio.sleep(30)          # let the server fully start first
    while True:
        try:
            await sync_huly_to_gitlab()
        except Exception as e:
            print(f"❌ Huly poll error: {e}")
        await asyncio.sleep(300)     # 5 minutes

async def sync_huly_to_gitlab():
    if not HULY_READY or not GITLAB_API_TOKEN or not GITLAB_PROJECT_ID:
        return

    print("🔄 Polling Huly for new issues...")
    ok, out = await run_bridge("--list-issues", timeout=60)
    if not ok:
        print(f"⚠️  Huly list failed: {out[:200]}")
        return

    try:
        data = json.loads(out)
        huly_issues = data.get('result', [])
        if not huly_issues:
            print("⚠️  No issues found in Huly response")
            return
        print(f"📊 Found {len(huly_issues)} issues in Huly")
    except json.JSONDecodeError:
        print(f"⚠️  Could not parse Huly issue list: {out[:100]}")
        return

    known = get_known_huly_identifiers()
    print(f"📊 Known identifiers in DB: {len(known)}")
    new_count = 0

    for issue in huly_issues:
        identifier = issue.get("identifier")
        if not identifier or identifier in known:
            continue

        # Check if this issue already exists in GitLab by title
        title = issue.get("title", "(no title)")
        status = issue.get("status", "")
        desc = f"Synced from Huly\n\n**Huly ID**: {identifier}\n**Status**: {status}"

        print(f"🔄 New Huly issue → GitLab: {identifier} — {title}")
        success = await create_gitlab_issue(title, desc, GITLAB_PROJECT_ID)
        if success:
            save_issue(
                iid=identifier, title=title, description=desc,
                state=status, author="huly", project=HULY_PROJECT_IDENTIFIER,
                url=f"{HULY_URL}/workbench/{HULY_WORKSPACE}",
                created_at=None, synced=True,
                huly_identifier=identifier, source="huly",
            )
            new_count += 1

    print(f"✅ Huly poll done — {new_count} new issue(s) pushed to GitLab")

# ── GitLab API ────────────────────────────────────────────────────────────────

async def create_gitlab_issue(title, description, project_id):
    headers = {"Authorization": f"Bearer {GITLAB_API_TOKEN}", "Content-Type": "application/json"}
    data = {
        "title": title,
        "description": f"{description}\n\n---\n**Source**: Huly\n**Synced**: {datetime.now().isoformat()}",
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{GITLAB_API_URL}/projects/{project_id}/issues",
                headers=headers, json=data, timeout=10,
            )
            if r.status_code == 201:
                issue = r.json()
                print(f"✅ GitLab issue created: #{issue['iid']} — {title}")
                return True
            print(f"❌ GitLab API {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"❌ GitLab error: {e}")
    return False

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/stats")
async def get_stats_endpoint():
    """Get current statistics"""
    return get_stats()

@app.get("/")
async def root():
    return {
        "status": "running",
        "huly_ready": HULY_READY,
        "gitlab_configured": bool(GITLAB_API_TOKEN),
        "gitlab_project_id": GITLAB_PROJECT_ID,
        "huly_project": HULY_PROJECT_IDENTIFIER,
        "bridge_exists": BRIDGE_SCRIPT.exists(),
        "stats": get_stats(),
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    try:
        return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "<p>dashboard.html not found. Open <a href='/api/webhooks'>/api/webhooks</a> instead.</p>"

@app.get("/api/webhooks")
async def api_webhooks():
    return {"webhooks": get_issues(100), "stats": get_stats()}

@app.get("/test/gitlab")
async def test_gitlab():
    if not GITLAB_API_TOKEN:
        return {"status": "error", "message": "GITLAB_API_TOKEN not set"}
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{GITLAB_API_URL}/projects",
                                 headers={"Authorization": f"Bearer {GITLAB_API_TOKEN}"},
                                 params={"membership": True, "per_page": 5})
            if r.status_code == 200:
                return {"status": "connected",
                        "projects": [{"id": p["id"], "name": p["name"]} for p in r.json()]}
            return {"status": "error", "code": r.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}

@app.get("/test/huly")
async def test_huly():
    return {
        "huly_ready": HULY_READY,
        "workspace": HULY_WORKSPACE,
        "project": HULY_PROJECT_IDENTIFIER,
        "bridge_exists": BRIDGE_SCRIPT.exists(),
    }

# ── GitLab webhook (GitLab → Huly) ───────────────────────────────────────────

@app.post("/webhook/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str = Header(None),
    webhook_id: str = Header(None),
    webhook_timestamp: str = Header(None),
    webhook_signature: str = Header(None),
):
    raw_body = await request.body()
    verified = False
    signing_token = os.getenv("GITLAB_WEBHOOK_SIGNING_TOKEN")

    if signing_token and webhook_signature and webhook_id and webhook_timestamp:
        raw_key = base64.b64decode(signing_token.removeprefix("whsec_"))
        message = f"{webhook_id}.{webhook_timestamp}.{raw_body.decode()}".encode()
        digest  = hmac.new(raw_key, message, hashlib.sha256).digest()
        expected = "v1," + base64.b64encode(digest).decode()
        # GitLab may send multiple signatures space-separated
        verified = any(hmac.compare_digest(expected, sig)
                       for sig in webhook_signature.split())
        print("✅ HMAC verified!" if verified else "❌ HMAC mismatch")
    else:
        secret = os.getenv("GITLAB_WEBHOOK_SECRET")
        if secret and x_gitlab_token:
            verified = hmac.compare_digest(secret, x_gitlab_token)
            print("✅ Secret token verified!" if verified else "❌ Secret token mismatch")

    if not verified:
        raise HTTPException(status_code=401, detail="Invalid or missing credentials")

    payload    = json.loads(raw_body)
    event_type = payload.get("object_kind")
    print(f"📨 GitLab event: {event_type}")

    if event_type in ("issue", "work_item"):
        asyncio.create_task(process_gitlab_issue(payload))

    return {"status": "success", "event": event_type}

# ── Huly webhook (Huly → GitLab, for when Huly adds webhook support later) ───
@app.get("/test/poll")
async def trigger_poll():
    """Manually trigger Huly → GitLab sync"""
    try:
        await sync_huly_to_gitlab()
        return {"status": "polling_completed", "message": "Check GitLab for new issues"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/webhook/huly")
async def huly_webhook(request: Request):
    """Placeholder — Huly doesn't support outbound webhooks yet.
    Bidirectional sync currently runs via polling (poll_huly_forever)."""
    payload = await request.json()
    print(f"📨 Huly webhook (unexpected): {payload}")
    return {"status": "received"}

# ── Issue processing ─────────────────────────────────────────────────────────

async def process_gitlab_issue(payload: dict):
    issue_data   = payload.get("object_attributes", {})
    project_data = payload.get("project", {})
    if not issue_data:
        return

    iid     = issue_data.get("iid")
    title   = issue_data.get("title")
    desc    = issue_data.get("description", "")
    state   = issue_data.get("state")
    author  = issue_data.get("author", {}).get("username", "unknown")
    project = project_data.get("name", "unknown")
    url     = issue_data.get("url")
    created = issue_data.get("created_at")

    print(f"📝 #{iid} — {title} ({state}) by {author}")

    # Save to DB immediately (not yet synced to Huly)
    save_issue(iid, title, desc, state, author, project, url, created, synced=False)

    status_map  = {"opened": "Todo", "closed": "Done", "reopened": "Todo"}
    huly_status = status_map.get(state, "Todo")
    huly_desc   = f"{desc}\n\n---\n**Source**: GitLab #{iid}\n**URL**: {url}"

    ok, result = await run_bridge(title, huly_desc, huly_status, timeout=180)

    if ok:
        print(f"✅ Created in Huly: {result}")
        mark_synced(iid, result)  # result is the Huly identifier e.g. "HULY-7"
    else:
        print(f"⚠️  Huly failed ({result}) — issue saved to DB, will show in dashboard")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Huly-GitLab Sync Service")
    print(f"   Huly ready:      {'✅' if HULY_READY else '❌ (check .env)'}")
    print(f"   GitLab:          {'✅' if GITLAB_API_TOKEN else '❌'}")
    print(f"   GitLab project:  {GITLAB_PROJECT_ID or '⚠️  GITLAB_PROJECT_ID not set'}")
    print(f"   Huly project:    {HULY_PROJECT_IDENTIFIER or '⚠️  not set'}")
    print(f"   Dashboard:       http://localhost:8000/dashboard")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)