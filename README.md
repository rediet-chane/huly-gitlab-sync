# Huly-GitLab Sync Service

**Bidirectional sync between GitLab and Huly** — no copy-pasting needed.

- ✅ GitLab → Huly: **Real-time** (webhooks)
- ✅ Huly → GitLab: **Every 5 minutes** (polling)
- ✅ **No duplicates** — hidden marker prevents loops

**Live:** https://huly-gitlab-sync.onrender.com  
**Dashboard:** https://huly-gitlab-sync.onrender.com/dashboard

---

## How it works

**Loop prevention** is handled by a hidden HTML comment (`<!-- huly-sync:HULY-XX -->`) in every issue description. When the system sees this marker, it knows the issue came from the other side and **doesn't sync it back**, preventing infinite loops.

---

## Stack

| Technology | Purpose |
|------------|---------|
| **Python + FastAPI** | Webhook receiver & API server |
| **Node.js + MCP** | Huly API bridge |
| **SQLite** | Sync history & duplicate prevention |
| **Render** | Cloud hosting (24/7) |
| **HTML + CSS + JS** | Dashboard |

---

## Setup

```bash
# Clone the repo
git clone https://github.com/rediet-chane/huly-gitlab-sync
cd huly-gitlab-sync

# Install dependencies
pip install -r requirements.txt
npm install

# Configure credentials
cp .env.example .env
# Edit .env with your GitLab and Huly credentials

# Run the service
python main.py

---

## 🚀 **Deploy the Fix**

```bash
# Replace main.py with the fix
# Replace README.md with the new version

git add main.py README.md
git commit -m "Fix: Parse Huly ID from JSON response to prevent duplicates"
git push