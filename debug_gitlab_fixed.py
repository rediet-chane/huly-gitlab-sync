# debug_gitlab_fixed.py
import gitlab
import os
from dotenv import load_dotenv

load_dotenv()

PRIVATE_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com")

print(f"🔑 Token: {PRIVATE_TOKEN[:10]}...")
print(f"📍 URL: {GITLAB_URL}")

if not PRIVATE_TOKEN:
    print("❌ No token found!")
    exit(1)

try:
    # Try to connect
    gl = gitlab.Gitlab(GITLAB_URL, private_token=PRIVATE_TOKEN)
    
    # Try to get projects directly (doesn't need user info)
    print("\n📂 Fetching your projects...")
    projects = gl.projects.list(membership=True, per_page=20)
    
    if projects:
        print(f"✅ Found {len(projects)} projects:")
        for project in projects:
            print(f"   - {project.path_with_namespace} (ID: {project.id})")
            
        # Try to get issues from the first project
        first_project = projects[0]
        print(f"\n📋 Fetching issues from: {first_project.name}")
        issues = first_project.issues.list(state="closed", per_page=5)
        print(f"   Closed issues found: {len(issues)}")
        
    else:
        print("⚠️  No projects found. Make sure you're a member of at least one project.")
        
except gitlab.exceptions.GitlabAuthenticationError:
    print("❌ Authentication failed! Check your token.")
except gitlab.exceptions.GitlabGetError as e:
    print(f"❌ GitLab API error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")