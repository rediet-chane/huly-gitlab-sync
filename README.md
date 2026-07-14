# Huly ↔ GitLab Sync Service

Bidirectional issue sync between GitLab and Huly. Built as an internship project at [Awura.tech](https://awura.tech).

**Live service:** https://huly-gitlab-sync.onrender.com  
**Dashboard:** https://huly-gitlab-sync.onrender.com/dashboard

---

## How it works

```
GitLab issue created → webhook fires → issue appears in Huly   (real-time)
Huly issue created   → polling runs  → issue appears in GitLab (every 5 min)
```

Loop prevention uses a hidden HTML marker `<!-- huly-sync:HULY-XX -->` embedded in issue descriptions, so the same issue is never bounced back and forth between platforms.

---

## Architecture

```
┌─────────────┐    webhook     ┌──────────────────┐    subprocess    ┌──────────────────┐
│   GitLab    │ ─────────────▶ │  FastAPI (Python) │ ───────────────▶ │  huly_api.js     │
│             │                │  main.py          │                  │  (Node.js bridge) │
│             │ ◀───────────── │                   │ ◀─────────────── │  @firfi/huly-mcp │
└─────────────┘  GitLab API    └──────────────────┘    JSON result   └──────────────────┘
                                        │
                                   SQLite DB
                                  (sync history)
```

Huly has no REST API — their only programmatic interface is a Node.js SDK. The bridge script (`huly_api.js`) wraps that SDK and is called as a subprocess from the Python server.

---

## Stack

- **Python + FastAPI** — webhook receiver and polling engine
- **Node.js** — Huly API bridge via `@firfi/huly-mcp`  
- **SQLite** — sync history and deduplication
- **Render** — cloud hosting

---

## Setup

```bash
git clone https://github.com/rediet-chane/huly-gitlab-sync
cd huly-gitlab-sync

pip install -r requirements.txt
npm install

cp .env.example .env
# fill in your credentials in .env

python main.py
```

### Required environment variables

```
GITLAB_API_TOKEN              # GitLab personal access token (api scope)
GITLAB_PROJECT_ID             # numeric project ID from your GitLab project page
GITLAB_WEBHOOK_SIGNING_TOKEN  # from GitLab webhook settings (whsec_... format)
GITLAB_WEBHOOK_SECRET         # fallback plain secret token

HULY_EMAIL                    # Huly account email
HULY_PASSWORD                 # Huly account password
HULY_WORKSPACE                # workspace slug from huly.app/workbench/<slug>
HULY_PROJECT_IDENTIFIER       # short code like "HULY" — run node huly_api.js --list-projects
```

---

## Endpoints

| Endpoint | What it does |
|----------|-------------|
| `GET /` | Service status and sync stats |
| `GET /dashboard` | Web dashboard showing all synced issues |
| `POST /webhook/gitlab` | GitLab webhook receiver |
| `GET /test/poll` | Manually trigger Huly → GitLab sync |
| `GET /test/gitlab` | Test GitLab connection |
| `GET /test/huly` | Test Huly configuration |

---

## Deployment on Render

The `render.yaml` file configures everything. Set the environment variables in Render's dashboard under Environment. Render runs both `pip install` and `npm install` at build time.

> **Note:** Render's free tier uses ephemeral storage, so the SQLite database resets on each deploy. The deduplication logic checks GitLab directly (not just the local DB) to handle this.

---

## What I learned building this

Huly's API turned out to be WebSocket-based with no public REST interface, which meant guessing endpoint URLs didn't work. The solution was finding their Node.js SDK and building a subprocess bridge from Python. Along the way I also debugged HMAC-SHA256 webhook signature verification, SQLite persistence issues on ephemeral cloud hosting, and a sync loop problem that caused 1,100+ duplicate GitLab issues before the loop-prevention marker was added.