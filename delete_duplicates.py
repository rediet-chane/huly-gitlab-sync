# delete_duplicates.py
# Permanently deletes closed GitLab issues that were created by the sync service.
# Safe: only touches issues that contain "Synced from Huly" in their description.
# Your real original issues are not affected.
#
# Run: python delete_duplicates.py

import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN      = os.getenv("GITLAB_API_TOKEN")
PROJECT_ID = os.getenv("GITLAB_PROJECT_ID", "83669199")
BASE_URL   = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")

SYNC_MARKERS = ["Synced from Huly", "Source: Huly", "**Source**: Huly", "huly-sync:"]

async def main():
    if not TOKEN:
        print("❌ Set GITLAB_API_TOKEN in .env")
        return

    headers = {"Authorization": f"Bearer {TOKEN}"}
    to_delete = []
    page = 1

    print("🔍 Finding closed sync-created issues...")

    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(
                f"{BASE_URL}/projects/{PROJECT_ID}/issues",
                headers=headers,
                params={"state": "closed", "per_page": 100, "page": page},
                timeout=15,
            )
            issues = r.json()
            if not issues:
                break

            for issue in issues:
                desc = issue.get("description") or ""
                if any(m in desc for m in SYNC_MARKERS):
                    to_delete.append((issue["iid"], issue["title"]))

            page += 1
            if len(issues) < 100:
                break

    if not to_delete:
        print("✅ No sync-created closed issues found. Nothing to delete.")
        return

    print(f"\n📋 Found {len(to_delete)} closed sync-created issues to delete.")
    print("   First 5 examples:")
    for iid, title in to_delete[:5]:
        print(f"   #{iid}: {title[:60]}")

    confirm = input(f"\n⚠️  Permanently delete all {len(to_delete)} issues? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("Cancelled.")
        return

    deleted = 0
    failed  = 0

    async with httpx.AsyncClient() as client:
        for iid, title in to_delete:
            r = await client.delete(
                f"{BASE_URL}/projects/{PROJECT_ID}/issues/{iid}",
                headers=headers,
                timeout=10,
            )
            if r.status_code == 204:
                deleted += 1
                print(f"🗑️  Deleted #{iid}: {title[:50]}")
            else:
                failed += 1
                print(f"❌ Failed #{iid}: {r.status_code} — {r.text[:80]}")

    print(f"\n✅ Done — {deleted} deleted, {failed} failed.")
    if failed > 0:
        print("   Failed issues may require Owner role. Check your GitLab permissions.")

asyncio.run(main())