# delete_duplicates_direct.py
import gitlab
import os
from dotenv import load_dotenv

load_dotenv()

PRIVATE_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com")
PROJECT_ID = 83669199  # Your project ID from earlier

print(f"🔑 Token: {PRIVATE_TOKEN[:10]}...")
print(f"📂 Project ID: {PROJECT_ID}")

if not PRIVATE_TOKEN:
    print("❌ GITLAB_API_TOKEN not found in .env")
    exit(1)

# Initialize GitLab
gl = gitlab.Gitlab(GITLAB_URL, private_token=PRIVATE_TOKEN)

try:
    # Try to get the project directly by ID
    project = gl.projects.get(PROJECT_ID)
    print(f"✅ Connected to project: {project.name}")
    print(f"   Full path: {project.path_with_namespace}")
    
except gitlab.exceptions.GitlabGetError as e:
    if e.response_code == 404:
        print(f"❌ Project {PROJECT_ID} not found. Trying alternative...")
        
        # Try by path if ID fails
        try:
            project = gl.projects.get("redichane-group/redichane-project")
            print(f"✅ Found by path: {project.name} (ID: {project.id})")
        except:
            print("❌ Could not find project by path either.")
            exit(1)
    else:
        print(f"❌ Error: {e}")
        exit(1)

# Now work with the project
print("\n🔍 Fetching closed issues...")
all_issues = []
page = 1

while True:
    try:
        issues = project.issues.list(state="closed", per_page=100, page=page)
        if not issues:
            break
        all_issues.extend(issues)
        print(f"📊 Page {page}: found {len(issues)} closed issues")
        page += 1
    except Exception as e:
        print(f"⚠️  Error on page {page}: {e}")
        break

if not all_issues:
    print("✅ No closed issues found!")
    exit(0)

print(f"\n📊 Total closed issues: {len(all_issues)}")

# Identify duplicates
duplicates = []
legitimate = []

for issue in all_issues:
    desc = issue.description or ""
    if "Synced from Huly" in desc or "Source: Huly" in desc or "<!-- huly-sync" in desc:
        duplicates.append(issue)
    else:
        legitimate.append(issue)

print(f"\n📊 Duplicate issues (to delete): {len(duplicates)}")
print(f"📊 Legitimate issues (keep): {len(legitimate)}")

if not duplicates:
    print("✅ No duplicate issues to delete!")
    exit(0)

# Show preview
print("\n📋 First 10 duplicates:")
for issue in duplicates[:10]:
    print(f"   #{issue.iid}: {issue.title[:40]}")

print("\n⚠️  WARNING: This will delete duplicate closed issues ONLY!")
print("   Legitimate issues (without 'Synced from Huly' marker) will be kept.")
print("   Press Ctrl+C to cancel, or wait 10 seconds to continue...")

import time
for i in range(10, 0, -1):
    print(f"   {i}...", end="\r")
    time.sleep(1)
print("\n🚀 Starting deletion...\n")

deleted = 0
failed = 0

for issue in duplicates:
    try:
        issue.delete()
        deleted += 1
        print(f"✅ Deleted #{issue.iid}: {issue.title[:40]}")
    except Exception as e:
        failed += 1
        print(f"❌ Failed #{issue.iid}: {e}")

print(f"\n🎉 Done! Deleted {deleted} duplicate issues. Failed: {failed}")