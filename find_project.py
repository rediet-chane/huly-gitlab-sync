import gitlab
import os
from dotenv import load_dotenv

load_dotenv()

PRIVATE_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com")

gl = gitlab.Gitlab(GITLAB_URL, private_token=PRIVATE_TOKEN)
try:
    projects = gl.projects.list(owned=True, per_page=20)
    print("📂 Your projects:")
    for p in projects:
        print(f"   - {p.path_with_namespace} (ID: {p.id})")
except Exception as e:
    print(f"⚠️  Could not list projects: {e}")
    
    known_ids = [83669199, 83673004]
    for pid in known_ids:
        try:
            project = gl.projects.get(pid)
            print(f"✅ Found project: {project.path_with_namespace} (ID: {project.id})")
        except:
            print(f"❌ Project {pid} not found")