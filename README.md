# Huly ↔ GitLab Sync Service

Bidirectional issue sync between GitLab and Huly. No more copying issues manually between platforms.

**Live demo:** https://huly-gitlab-sync.onrender.com  
**Dashboard:** https://huly-gitlab-sync.onrender.com/dashboard

---

## How it works

```
GitLab issue created → webhook → this service → Huly    (real-time, seconds)
Huly issue created   → polling every 5 min → this service → GitLab
```

Loop prevention is built in: issues created by the sync carry a hidden marker so they are never bounced back to the other platform.

---

## Features

- **GitLab → Huly** in real-time via webhook
- **Huly → GitLab** via polling every 5 minutes  
- HMAC-SHA256 webhook signature verification
- Loop prevention (no infinite sync cycles)
- Web dashboard with filtering, search, and CSV export
- Deployed on Render with persistent storage

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI |
| Huly API | Node.js bridge via `@firfi/huly-mcp` MCP server |
| Database | SQLite |
| Hosting | Render |
| Dashboard | HTML / CSS / JavaScript |

Huly has no REST API. The Node.js bridge spawns the official Huly MCP server as a subprocess and communicates with it over stdio, which is then called from Python.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/rediet-chane/huly-gitlab-sync
cd huly-gitlab-sync
pip install -r requirements.txt
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```env
# GitLab
GITLAB_API_TOKEN=glpat-...
GITLAB_PROJECT_ID=12345678
GITLAB_WEBHOOK_SECRET=your_secret
GITLAB_WEBHOOK_SIGNING_TOKEN=whsec_...

# Huly
HULY_EMAIL=you@example.com
HULY_PASSWORD=yourpassword
HULY_WORKSPACE=your-workspace-slug
HULY_PROJECT_IDENTIFIER=PROJ
HULY_URL=https://huly.app
```

To find your `HULY_PROJECT_IDENTIFIER`, run:
```bash
node huly_api.js --list-projects
```

### 3. Run

```bash
python main.py
```

The server starts on `http://localhost:8000`.

### 4. Configure GitLab webhook

In your GitLab project go to **Settings → Webhooks** and add:

- **URL:** your public URL + `/webhook/gitlab` (use [ngrok](https://ngrok.com) for local testing)
- **Trigger:** Issues events
- **Secret token:** value from `GITLAB_WEBHOOK_SIGNING_TOKEN`

---

## Deploying to Render

The `render.yaml` in this repo configures everything automatically. Add your environment variables in the Render dashboard under Environment.

For persistent storage (to survive restarts), create a Render **Disk** mounted at `/var/data`. The app detects this automatically and stores the database there.

---

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Service status and stats |
| `GET /dashboard` | Web dashboard |
| `GET /api/webhooks` | Raw JSON of all synced issues |
| `GET /test/poll` | Manually trigger Huly → GitLab poll |
| `GET /test/gitlab` | Test GitLab connection |
| `GET /test/huly` | Test Huly configuration |
| `POST /webhook/gitlab` | GitLab webhook receiver |

---

## Project structure

```
├── main.py          # FastAPI server, webhook handling, polling loop
├── huly_api.js      # Node.js bridge to Huly MCP server
├── dashboard.html   # Web dashboard frontend
├── requirements.txt # Python dependencies
├── package.json     # Node.js dependencies
├── render.yaml      # Render deployment config
├── test_local.py    # Local webhook test with real HMAC signing
└── .env.example     # Environment variable template
```