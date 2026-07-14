import httpx
from typing import Optional, List
from src.config import settings

class GitLabClient:
    """Client for interacting with GitLab"""
    
    def __init__(self):
        self.token = settings.GITLAB_API_TOKEN
        self.url = settings.GITLAB_API_URL
    
    async def get_project(self, project_id: int):
        """Get project details"""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.url}/projects/{project_id}",
                headers=headers
            )
            return response.json() if response.status_code == 200 else None