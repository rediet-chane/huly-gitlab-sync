# delete_closed_issues_fixed.py
import gitlab
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
GITLAB_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com")
PRIVATE_TOKEN = os.getenv("GITLAB_API_TOKEN")
PROJECT_PATH = "redichane-group/redichane-project"  # Use the full path instead of ID

if not PRIVATE_TOKEN:
    print("❌ GITLAB_API_TOKEN not found in .env")
    exit(1)

print(f"🔑 Using token: {PRIVATE_TOKEN[:10]}...")
print(f"📂 Project: {PROJECT_PATH}")

# Authenticate
try:
    gl = gitlab.Gitlab(GITLAB_URL, private_token=PRIVATE_TOKEN)
    
    # Try to get project by path
    try:
        project = gl.projects.get(PROJECT_PATH)
        print(f"✅ Connected to project: {project.name} (ID: {project.id})")
    except Exception as e:
        # If that fails, try getting all projects and find by name
        print(f"⚠️  Could not find by path, searching all projects...")
        projects = gl.projects.list(search="redichane-project", all=True)
        if projects:
            project = projects[0]
            print(f"✅ Found project: {project.name} (ID: {project.id})")
        else:
            print("❌ Project not found!")
            print("   Available projects:")
            for p in gl.projects.list(membership=True, per_page=10):
                print(f"   - {p.path_with_namespace} (ID: {p.id})")
            exit(1)
            
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    exit(1)

# Get ALL closed issues
print("\n🔍 Fetching closed issues...")
all_closed = []

# Use pagination to get all closed issues
page = 1
while True:
    try:
        issues = project.issues.list(state="closed", per_page=100, page=page)
        if not issues:
            break
        all_closed.extend(issues)
        print(f"📊 Page {page}: found {len(issues)} closed issues")
        page += 1
    except Exception as e:
        print(f"❌ Error fetching page {page}: {e}")
        break

if not all_closed:
    print("✅ No closed issues found to delete!")
    exit(0)

print(f"\n📊 Total closed issues found: {len(all_closed)}")

# Separate duplicates from legitimate issues
duplicates = []
legitimate = []

for issue in all_closed:
    desc = issue.description or ""
    if "Synced from Huly" in desc or "Source: Huly" in desc or "huly-sync" in desc:
        duplicates.append(issue)
    else:
        legitimate.append(issue)

print(f"\n📊 Found {len(duplicates)} duplicate issues to delete")
print(f"📊 Found {len(legitimate)} legitimate closed issues (keeping them)")

if not duplicates:
    print("✅ No duplicate issues found!")
    exit(0)

# Show a sample of what will be deleted
print("\n📋 Sample of duplicates to delete:")
for issue in duplicates[:5]:
    print(f"   #{issue.iid}: {issue.title[:50]}")

print("\n⚠️  WARNING: This will delete duplicate closed issues only!")
print("   Legitimate issues (without 'Synced from Huly' marker) will be kept.")
print("   Press Ctrl+C to cancel, or wait 10 seconds to continue...")

import time
for i in range(10, 0, -1):
    print(f"   {i}...", end="\r")
    time.sleep(1)
print("\n🚀 Starting deletion...\n")

deleted_count = 0
failed_count = 0

for issue in duplicates:
    try:
        issue.delete()
        deleted_count += 1
        print(f"✅ Deleted #{issue.iid}: {issue.title[:50]}")
    except Exception as e:
        failed_count += 1
        print(f"❌ Failed to delete #{issue.iid}: {e}")

print(f"\n🎉 Deletion complete!")
print(f"   ✅ Successfully deleted: {deleted_count}")
print(f"   ❌ Failed: {failed_count}")
print(f"   📊 Legitimate issues kept: {len(legitimate)}")