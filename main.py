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

_RENDER_DATA = Path("/var/data")
DB_PATH = str(_RENDER_DATA / "webhooks.db") if _RENDER_DATA.exists() else "webhooks.db"

def parse_huly_id(raw: str) -> str:
    """Extract just the identifier from the bridge's JSON response."""
    if not raw:
        return raw
    try:
        parsed = json.loads(raw)
        return parsed.get("identifier", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw.strip()

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

    c.execute("SELECT id, huly_identifier FROM issues WHERE huly_identifier LIKE '{%'")
    bad_rows = c.fetchall()
    fixed = 0
    for row_id, bad_id in bad_rows:
        good_id = parse_huly_id(bad_id)
        if good_id != bad_id:
            c.execute("UPDATE issues SET huly_identifier=? WHERE id=?", (good_id, row_id))
            fixed += 1
    if fixed:
        print(f"🔧 Fixed {fixed} bad huly_identifier rows in DB")

    conn.commit()
    conn.close()
    print(f"✅ Database ready: {DB_PATH}")

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

def mark_synced(iid, raw_result):
    """Parse the Huly identifier from the bridge response and mark as synced."""
    huly_id = parse_huly_id(raw_result)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE issues SET synced_to_huly="yes", huly_identifier=? WHERE iid=?',
              (huly_id, str(iid)))
    conn.commit()
    conn.close()
    return huly_id

def iid_exists(iid: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM issues WHERE iid=? LIMIT 1', (iid,))
    found = c.fetchone() is not None
    conn.close()
    return found

def huly_id_exists(huly_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM issues WHERE huly_identifier=? LIMIT 1', (huly_id,))
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
        'open':   q('SELECT COUNT(*) FROM issues WHERE state IN ("opened","Todo","Backlog")'),
        'today':  q('SELECT COUNT(*) FROM issues WHERE date(received_at)=date("now")'),
        'synced': q('SELECT COUNT(*) FROM issues WHERE synced_to_huly="yes"'),
    }
    conn.close()
    return stats

init_db()

def make_gitlab_desc_from_huly(identifier, status):
    return (
        f"Synced from Huly\n\n"
        f"**Huly ID**: {identifier}\n"
        f"**Status**: {status}\n\n"
        f"<!-- huly-sync:{identifier} -->"
    )

def extract_huly_sync_id(description: str):
    if not description:
        return None
    m = re.search(r'<!-- huly-sync:([A-Z0-9\-]+) -->', description)
    return m.group(1) if m else None

async def gitlab_huly_issue_exists(huly_identifier: str) -> bool:
    """Check if GitLab already has an issue with this specific Huly ID marker."""
    if not GITLAB_API_TOKEN or not GITLAB_PROJECT_ID:
        return False
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{GITLAB_API_URL}/projects/{GITLAB_PROJECT_ID}/issues",
                headers={"Authorization": f"Bearer {GITLAB_API_TOKEN}"},
                params={"search": f"huly-sync:{huly_identifier}", "state": "all", "per_page": 5},
                timeout=10
            )
            if r.status_code == 200:
                for issue in r.json():
                    if f"<!-- huly-sync:{huly_identifier} -->" in (issue.get("description") or ""):
                        return True
        except Exception as e:
            print(f"⚠️  GitLab check error: {e}")
    return False

async def run_bridge(*args, timeout=60) -> tuple[bool, str]:
    if not HULY_READY:
        return False, "Huly not configured"
    if not BRIDGE_SCRIPT.exists():
        return False, f"Bridge not found: {BRIDGE_SCRIPT}"

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

    return proc.returncode == 0, stdout.decode(errors="replace").strip()

async def poll_huly_forever():
    await asyncio.sleep(30)
    while True:
        try:
            await sync_huly_to_gitlab()
        except Exception as e:
            print(f"❌ Poll error: {e}")
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
        print(f"⚠️  Could not parse response: {out[:100]}")
        return

    known = get_known_huly_identifiers()
    print(f"📊 Huly: {len(huly_issues)} issues | DB knows: {len(known)} identifiers")

    new_count = 0
    for issue in huly_issues:
        identifier = issue.get("identifier")
        if not identifier:
            continue
            
        title = issue.get("title", "(no title)")
        status = issue.get("status", "")
        
        if identifier in known:
            print(f"⏭️  Already known: {identifier}")
            continue
        
        if await gitlab_huly_issue_exists(identifier):
            print(f"⏭️  Already in GitLab ({identifier}): {title}")
            save_issue(
                iid=identifier, title=title, description="",
                state=status, author="huly", project=HULY_PROJECT_IDENTIFIER,
                url=f"{HULY_URL}/workbench/{HULY_WORKSPACE}",
                created_at=None, synced=True,
                huly_identifier=identifier, source="huly",
            )
            continue

        desc = make_gitlab_desc_from_huly(identifier, status)

        print(f"🔄 Huly→GitLab: {identifier} — {title}")
        if await create_gitlab_issue(title, desc, GITLAB_PROJECT_ID):
            save_issue(
                iid=identifier, title=title, description=desc,
                state=status, author="huly", project=HULY_PROJECT_IDENTIFIER,
                url=f"{HULY_URL}/workbench/{HULY_WORKSPACE}",
                created_at=None, synced=True,
                huly_identifier=identifier, source="huly",
            )
            new_count += 1

    print(f"✅ Poll done — {new_count} new issue(s) sent to GitLab")

async def create_gitlab_issue(title, description, project_id) -> bool:
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
                print(f"✅ GitLab issue #{r.json()['iid']} created: {title}")
                return True
            print(f"❌ GitLab {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"❌ GitLab error: {e}")
    return False

@asynccontextmanager
async def lifespan(app):
    print("🚀 Starting Huly-GitLab Sync Service...")
    task = asyncio.create_task(poll_huly_forever())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {
        "status": "running",
        "huly_ready": HULY_READY,
        "gitlab_project_id": GITLAB_PROJECT_ID,
        "huly_project": HULY_PROJECT_IDENTIFIER,
        "db_path": DB_PATH,
        "stats": get_stats(),
    }

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
            "project": HULY_PROJECT_IDENTIFIER}

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
        verified = any(hmac.compare_digest(expected, s) for s in webhook_signature.split())
        print("✅ HMAC verified!" if verified else "❌ HMAC mismatch")
    else:
        secret = os.getenv("GITLAB_WEBHOOK_SECRET")
        if secret and x_gitlab_token:
            verified = hmac.compare_digest(secret, x_gitlab_token)
            print("✅ Secret verified!" if verified else "❌ Secret mismatch")

    if not verified:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload    = json.loads(raw_body)
    event_type = payload.get("object_kind")
    action     = payload.get("object_attributes", {}).get("action", "")
    print(f"📨 GitLab event: {event_type} action={action}")

    if event_type in ("issue", "work_item"):
        asyncio.create_task(process_gitlab_issue(payload))

    return {"status": "success", "event": event_type}

async def process_gitlab_issue(payload: dict):
    issue_data   = payload.get("object_attributes", {})
    project_data = payload.get("project", {})
    if not issue_data:
        return

    iid     = str(issue_data.get("iid", ""))
    title   = issue_data.get("title", "")
    desc    = issue_data.get("description", "") or ""
    state   = issue_data.get("state", "opened")
    author  = issue_data.get("author", {}).get("username", "unknown")
    project = project_data.get("name", "unknown")
    url     = issue_data.get("url")
    created = issue_data.get("created_at")
    action  = issue_data.get("action", "open")

    huly_origin = extract_huly_sync_id(desc)
    if huly_origin:
        if not huly_id_exists(huly_origin):
            print(f"⏭️  #{iid} came from Huly ({huly_origin}) — recording only")
            save_issue(iid, title, desc, state, author, project, url, created,
                       synced=True, huly_identifier=huly_origin, source="huly")
        else:
            print(f"⏭️  #{iid} already in DB (Huly ID: {huly_origin}) — skipping")
        return

    if action == "update" and iid_exists(iid):
        print(f"✏️  #{iid} updated in GitLab — edit sync not yet implemented")
        return

    if iid_exists(iid):
        print(f"⏭️  #{iid} already in DB — skipping")
        return

    print(f"📝 #{iid} — {title} ({state}) by {author}")
    save_issue(iid, title, desc, state, author, project, url, created, synced=False)

    status_map  = {"opened": "Todo", "closed": "Done", "reopened": "Todo"}
    huly_status = status_map.get(state, "Todo")
    huly_desc   = f"{desc}\n\n---\n**Source**: GitLab #{iid}\n**URL**: {url}"

    ok, result = await run_bridge(title, huly_desc, huly_status, timeout=180)
    if ok:
        try:
            huly_id = json.loads(result).get('identifier', result)
        except Exception:
            huly_id = result
        print(f"✅ Created in Huly: {huly_id}")
        mark_synced(str(iid), huly_id)
    else:
        print(f"⚠️  Huly failed ({result})")

if __name__ == "__main__":
    print("=" * 50)
    print(f"  Huly ready:   {'✅' if HULY_READY else '❌'}")
    print(f"  GitLab:       {'✅' if GITLAB_API_TOKEN else '❌'}")
    print(f"  Project ID:   {GITLAB_PROJECT_ID or '⚠️  not set'}")
    print(f"  DB:           {DB_PATH}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)