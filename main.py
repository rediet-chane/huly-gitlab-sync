# main.py - Complete Working Version with Permanent Duplicate Fix
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
import os, asyncio, base64, hashlib, hmac, json, sqlite3, shutil, sys, re
import httpx
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

GITLAB_API_URL          = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
GITLAB_API_TOKEN        = os.getenv("GITLAB_API_TOKEN")
GITLAB_PROJECT_ID       = os.getenv("GITLAB_PROJECT_ID")

HULY_URL                = os.getenv("HULY_URL", "https://huly.app")
HULY_WORKSPACE          = os.getenv("HULY_WORKSPACE")
HULY_EMAIL              = os.getenv("HULY_EMAIL")
HULY_PASSWORD           = os.getenv("HULY_PASSWORD")
HULY_PROJECT_IDENTIFIER = os.getenv("HULY_PROJECT_IDENTIFIER")

HULY_READY = bool(HULY_EMAIL and HULY_PASSWORD and HULY_WORKSPACE and HULY_PROJECT_IDENTIFIER)

BRIDGE_SCRIPT = Path(__file__).resolve().parent / "huly_api.js"
NODE_CMD = shutil.which("node.exe" if sys.platform == "win32" else "node") or "node"

# ── Database ──────────────────────────────────────────────────────────────────

_RENDER_DATA = Path("/var/data")
DB_PATH = str(_RENDER_DATA / "webhooks.db") if _RENDER_DATA.exists() else "webhooks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
        source           TEXT DEFAULT "gitlab",
        labels           TEXT
    )''')
    for col in ["huly_identifier", "source", "labels"]:
        try:
            c.execute(f'ALTER TABLE issues ADD COLUMN {col} TEXT')
        except Exception:
            pass
    conn.commit()
    conn.close()
    print(f"✅ Database ready at: {DB_PATH}")

def save_issue(iid, title, description, state, author, project, url,
               created_at, synced=False, huly_identifier=None, source="gitlab", labels=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO issues
                 (iid,title,description,state,author,project,url,
                  created_at,received_at,synced_to_huly,huly_identifier,source,labels)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (iid, title, description, state, author, project, url, created_at,
               datetime.now().isoformat(), "yes" if synced else "no",
               huly_identifier, source, labels))
    conn.commit()
    conn.close()

def mark_synced(iid, huly_identifier):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE issues SET synced_to_huly="yes", huly_identifier=? WHERE iid=?',
              (huly_identifier, iid))
    conn.commit()
    conn.close()

def iid_exists(iid: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM issues WHERE iid=? LIMIT 1', (iid,))
    found = c.fetchone() is not None
    conn.close()
    return found

def get_known_huly_identifiers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT huly_identifier FROM issues WHERE huly_identifier IS NOT NULL')
    result = {row[0] for row in c.fetchall()}
    conn.close()
    return result

def get_issues(limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT iid,title,description,state,author,project,url,
                        received_at,synced_to_huly,huly_identifier,source,labels
                 FROM issues ORDER BY id DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(
        ['iid','title','description','state','author','project','url',
         'received_at','synced_to_huly','huly_identifier','source','labels'], row
    )) for row in rows]

def get_stats():
    conn = sqlite3.connect(DB_PATH)
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

# ── Loop prevention ───────────────────────────────────────────────────────────

def make_gitlab_desc_from_huly(title, identifier, status, labels=None):
    labels_section = f"\n\n**Labels**: {labels}" if labels else ""
    return (
        f"Synced from Huly\n\n"
        f"**Huly ID**: {identifier}\n"
        f"**Status**: {status}\n"
        f"{labels_section}\n"
        f"<!-- huly-sync:{identifier} -->"
    )

def extract_huly_sync_id(description: str):
    if not description:
        return None
    m = re.search(r'<!-- huly-sync:([A-Z0-9\-]+) -->', description)
    return m.group(1) if m else None

# ── Node bridge helper ────────────────────────────────────────────────────────

async def run_bridge(*args, timeout=60) -> tuple[bool, str]:
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

# ── Huly → GitLab polling ────────────────────────────────────────────────────

async def poll_huly_forever():
    await asyncio.sleep(30)
    while True:
        try:
            await sync_huly_to_gitlab()
        except Exception as e:
            print(f"❌ Huly poll error: {e}")
        await asyncio.sleep(300)

async def sync_huly_to_gitlab():
    if not HULY_READY or not GITLAB_API_TOKEN or not GITLAB_PROJECT_ID:
        print(f"⚠️  Poll skipped — GITLAB_PROJECT_ID={'set' if GITLAB_PROJECT_ID else 'MISSING'}")
        return

    print("🔄 Polling Huly for new issues...")
    ok, out = await run_bridge("--list-issues", timeout=60)
    if not ok:
        print(f"⚠️  list-issues failed: {out[:200]}")
        return

    try:
        huly_issues = json.loads(out)
        if isinstance(huly_issues, dict):
            huly_issues = huly_issues.get("result", [])
    except json.JSONDecodeError:
        print(f"⚠️  Could not parse Huly issue list: {out[:100]}")
        return

    known = get_known_huly_identifiers()
    print(f"📊 Huly: {len(huly_issues)} issues | DB knows: {len(known)} identifiers")

    new_count = 0
    for issue in huly_issues:
        identifier = issue.get("identifier")
        if not identifier or identifier in known:
            continue

        title = issue.get("title", "(no title)")
        status = issue.get("status", "")
        labels = issue.get("labels", [])
        if isinstance(labels, list):
            labels_str = ", ".join(labels) if labels else ""
        else:
            labels_str = str(labels) if labels else ""

        # ─── PERMANENT FIX: Check if already exists in GitLab ──────────────
        if await gitlab_issue_exists(title):
            print(f"⏭️  Issue already exists in GitLab: {title}")
            # Add to known so we don't check again
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO issues (huly_identifier, title, source) VALUES (?, ?, "huly")',
                      (identifier, title))
            conn.commit()
            conn.close()
            continue

        print(f"🔄 New Huly issue → GitLab: {identifier} — {title}")
        desc = make_gitlab_desc_from_huly(title, identifier, status, labels_str)

        success = await create_gitlab_issue(title, desc, GITLAB_PROJECT_ID)
        if success:
            save_issue(
                iid=identifier, title=title, description=desc,
                state=status, author="huly", project=HULY_PROJECT_IDENTIFIER,
                url=f"{HULY_URL}/workbench/{HULY_WORKSPACE}",
                created_at=None, synced=True,
                huly_identifier=identifier, source="huly",
                labels=labels_str,
            )
            new_count += 1

    print(f"✅ Poll done — {new_count} new issue(s) sent to GitLab")
    
# ── GitLab API ────────────────────────────────────────────────────────────────

async def create_gitlab_issue(title, description, project_id):
    headers = {"Authorization": f"Bearer {GITLAB_API_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{GITLAB_API_URL}/projects/{project_id}/issues",
                headers=headers,
                json={"title": title, "description": description},
                timeout=10,
            )
            if r.status_code == 201:
                issue = r.json()
                print(f"✅ GitLab issue created: #{issue['iid']} — {title}")
                return True
            print(f"❌ GitLab API {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"❌ GitLab error: {e}")
    return False

# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    print("🚀 Starting Huly-GitLab Sync Service...")
    print("🔄 Starting background polling task (runs every 5 minutes)...")
    task = asyncio.create_task(poll_huly_forever())
    yield
    print("🛑 Shutting down...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("✅ Polling task cancelled")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {
        "status": "running",
        "huly_ready": HULY_READY,
        "gitlab_configured": bool(GITLAB_API_TOKEN),
        "gitlab_project_id": GITLAB_PROJECT_ID,
        "huly_project": HULY_PROJECT_IDENTIFIER,
        "db_path": DB_PATH,
        "stats": get_stats(),
    }

@app.get("/stats")
async def get_stats_endpoint():
    """Get current statistics"""
    return get_stats()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    try:
        return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "<p>dashboard.html not found</p>"

@app.get("/api/webhooks")
async def api_webhooks():
    return {"webhooks": get_issues(100), "stats": get_stats()}

@app.get("/test/poll")
async def trigger_poll():
    await sync_huly_to_gitlab()
    return {"status": "done", "stats": get_stats()}

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
        except Exception as e:
            return {"status": "error", "message": str(e)}

@app.get("/test/huly")
async def test_huly():
    return {"huly_ready": HULY_READY, "workspace": HULY_WORKSPACE,
            "project": HULY_PROJECT_IDENTIFIER, "bridge_exists": BRIDGE_SCRIPT.exists()}

@app.get("/fix-duplicates")
async def fix_duplicates():
    """Clean up duplicate issues in the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT huly_identifier, COUNT(*) as cnt 
            FROM issues 
            WHERE huly_identifier IS NOT NULL 
            GROUP BY huly_identifier 
            HAVING cnt > 1
        ''')
        duplicates = c.fetchall()
        deleted = 0
        for huly_id, count in duplicates:
            c.execute('''
                DELETE FROM issues 
                WHERE huly_identifier = ? 
                AND source = 'gitlab'
            ''', (huly_id,))
            deleted += c.rowcount
        conn.commit()
        conn.close()
        return {
            "status": "success",
            "duplicate_groups": len(duplicates),
            "deleted": deleted,
            "message": f"Deleted {deleted} duplicate entries"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── GitLab webhook ────────────────────────────────────────────────────────────

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
        verified = any(hmac.compare_digest(expected, sig) for sig in webhook_signature.split())
        print("✅ HMAC verified!" if verified else "❌ HMAC mismatch")
    else:
        secret = os.getenv("GITLAB_WEBHOOK_SECRET")
        if secret and x_gitlab_token:
            verified = hmac.compare_digest(secret, x_gitlab_token)
            print("✅ Secret token verified!" if verified else "❌ Secret token mismatch")

    if not verified:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload    = json.loads(raw_body)
    event_type = payload.get("object_kind")
    print(f"📨 GitLab event: {event_type}")

    if event_type in ("issue", "work_item"):
        asyncio.create_task(process_gitlab_issue(payload))

    return {"status": "success", "event": event_type}

# ── PERMANENT DUPLICATE FIX ──────────────────────────────────────────────────

async def process_gitlab_issue(payload: dict):
    issue_data = payload.get("object_attributes", {})
    project_data = payload.get("project", {})
    if not issue_data:
        return

    iid = str(issue_data.get("iid", ""))
    title = issue_data.get("title", "")
    desc = issue_data.get("description", "") or ""
    state = issue_data.get("state", "opened")
    author = issue_data.get("author", {}).get("username", "unknown")
    project = project_data.get("name", "unknown")
    url = issue_data.get("url")
    created = issue_data.get("created_at")
    
    # Extract labels
    labels = issue_data.get("labels", [])
    if isinstance(labels, list):
        labels_str = ", ".join(labels) if labels else ""
    else:
        labels_str = str(labels) if labels else ""

    # ─── PERMANENT DUPLICATE FIX ───────────────────────────────────────────
    # Check if this issue came from our own Huly sync
    huly_id_from_marker = extract_huly_sync_id(desc)
    
    if huly_id_from_marker:
        # This issue came from Huly → GitLab sync
        # Check if we already have it in the database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT 1 FROM issues WHERE huly_identifier = ?', (huly_id_from_marker,))
        existing = c.fetchone() is not None
        conn.close()
        
        if existing:
            print(f"⏭️  #{iid} already exists in DB (Huly ID: {huly_id_from_marker}) — skipping")
            return
        
        # First time seeing this Huly ID - save it without syncing back
        if not iid_exists(iid):
            print(f"⏭️  #{iid} came from Huly ({huly_id_from_marker}) — recording, skipping Huly sync")
            save_issue(iid, title, desc, state, author, project, url, created,
                       synced=True, huly_identifier=huly_id_from_marker, source="huly", labels=labels_str)
        return

    # ─── NORMAL GITLAB ISSUE (Not from Huly) ──────────────────────────────
    if iid_exists(iid):
        print(f"⏭️  #{iid} already in DB — skipping")
        return

    print(f"📝 #{iid} — {title} ({state}) by {author}")
    save_issue(iid, title, desc, state, author, project, url, created, synced=False, labels=labels_str)

    # Create in Huly
    status_map = {"opened": "Todo", "closed": "Done", "reopened": "Todo"}
    huly_status = status_map.get(state, "Todo")
    
    labels_section = f"\n\n**Labels**: {labels_str}" if labels_str else ""
    huly_desc = f"{desc}{labels_section}\n\n---\n**Source**: GitLab #{iid}\n**URL**: {url}"

    ok, result = await run_bridge(title, huly_desc, huly_status, timeout=180)
    if ok:
        print(f"✅ Created in Huly: {result}")
        mark_synced(iid, result)
    else:
        print(f"⚠️  Huly failed ({result})")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print(f"   Huly ready:     {'✅' if HULY_READY else '❌'}")
    print(f"   GitLab:         {'✅' if GITLAB_API_TOKEN else '❌'}")
    print(f"   GitLab project: {GITLAB_PROJECT_ID or '⚠️  not set'}")
    print(f"   Huly project:   {HULY_PROJECT_IDENTIFIER or '⚠️  not set'}")
    print(f"   DB:             {DB_PATH}")
    print(f"   Dashboard:      http://localhost:8000/dashboard")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)