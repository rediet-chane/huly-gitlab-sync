import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

GITLAB_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_URL   = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
PROJECT_ID   = os.getenv("GITLAB_PROJECT_ID", "83669199")

SYNC_MARKERS = ["Source: Huly", "Synced from Huly", "**Source**: Huly"]

async def main():
    if not GITLAB_TOKEN:
        print("❌ Set GITLAB_API_TOKEN in .env")
        return

    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}", "Content-Type": "application/json"}
    closed = 0
    page   = 1

    print("🔍 Scanning GitLab issues for sync-created duplicates...")
    print("   (Only issues containing 'Source: Huly' will be closed)\n")

    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(
                f"{GITLAB_URL}/projects/{PROJECT_ID}/issues",
                headers=headers,
                params={"state": "opened", "per_page": 100, "page": page},
                timeout=15,
            )
            issues = r.json()
            if not issues:
                break

            for issue in issues:
                desc = issue.get("description") or ""
                title = issue.get("title", "")
                iid  = issue["iid"]

                is_sync_duplicate = any(marker in desc for marker in SYNC_MARKERS)
                if not is_sync_duplicate:
                    continue

                # Close it
                close = await client.put(
                    f"{GITLAB_URL}/projects/{PROJECT_ID}/issues/{iid}",
                    headers=headers,
                    json={"state_event": "close"},
                    timeout=10,
                )
                if close.status_code == 200:
                    closed += 1
                    print(f"✅ Closed #{iid}: {title[:60]}")
                else:
                    print(f"⚠️  Failed #{iid}: {close.status_code}")

            print(f"   Page {page} done ({len(issues)} issues scanned, {closed} closed so far)")
            page += 1

            if len(issues) < 100:
                break

    print(f"\n🎉 Done! Closed {closed} duplicate issues.")
    print("   Your original issues (no 'Source: Huly' marker) are untouched.")

asyncio.run(main())