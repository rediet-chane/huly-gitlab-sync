# delete_duplicates_fast.py
import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

GITLAB_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_URL   = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
PROJECT_ID   = os.getenv("GITLAB_PROJECT_ID", "83669199")

SYNC_MARKERS = ["Source: Huly", "Synced from Huly", "**Source**: Huly"]

async def delete_duplicates():
    if not GITLAB_TOKEN:
        print("❌ Set GITLAB_API_TOKEN in .env")
        return

    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}", "Content-Type": "application/json"}
    deleted = 0
    page = 1

    print("🔍 Scanning and DELETING sync-created duplicates...")
    print("   (Issues containing 'Source: Huly' will be DELETED)\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                r = await client.get(
                    f"{GITLAB_URL}/projects/{PROJECT_ID}/issues",
                    headers=headers,
                    params={"state": "all", "per_page": 100, "page": page},
                )
                
                if r.status_code != 200:
                    print(f"❌ Failed: {r.status_code}")
                    break
                    
                issues = r.json()
                if not issues:
                    break

                for issue in issues:
                    desc = issue.get("description") or ""
                    title = issue.get("title", "")
                    iid = issue["iid"]

                    # Skip if not a sync duplicate
                    if not any(marker in desc for marker in SYNC_MARKERS):
                        continue

                    # DELETE it (not just close)
                    try:
                        delete = await client.delete(
                            f"{GITLAB_URL}/projects/{PROJECT_ID}/issues/{issue['id']}",
                            headers=headers,
                        )
                        if delete.status_code == 204:
                            deleted += 1
                            print(f"✅ DELETED #{iid}: {title[:50]}")
                        else:
                            print(f"⚠️  Failed #{iid}: {delete.status_code}")
                    except Exception as e:
                        print(f"❌ Error #{iid}: {str(e)[:50]}")

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.05)

                print(f"📊 Page {page} done - {deleted} deleted so far")
                page += 1

                if len(issues) < 100:
                    break
                    
            except Exception as e:
                print(f"❌ Page error: {e}")
                await asyncio.sleep(2)
                continue

    print(f"\n🎉 Done! DELETED {deleted} duplicate issues.")
    print("   Your original issues are untouched.")

if __name__ == "__main__":
    asyncio.run(delete_duplicates())