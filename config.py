import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings"""
    
    GITLAB_API_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
    GITLAB_API_TOKEN = os.getenv("GITLAB_API_TOKEN")
    GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET")
    GITLAB_WEBHOOK_SIGNING_TOKEN = os.getenv("GITLAB_WEBHOOK_SIGNING_TOKEN")
    
    HULY_URL = os.getenv("HULY_URL", "https://huly.app")
    HULY_WORKSPACE = os.getenv("HULY_WORKSPACE")
    HULY_EMAIL = os.getenv("HULY_EMAIL")
    HULY_PASSWORD = os.getenv("HULY_PASSWORD")
    HULY_TOKEN = os.getenv("HULY_TOKEN")
    
    @property
    def huly_configured(self) -> bool:
        return bool(self.HULY_EMAIL and self.HULY_PASSWORD and self.HULY_WORKSPACE)
    
    @property
    def gitlab_configured(self) -> bool:
        return bool(self.GITLAB_API_TOKEN)

settings = Settings()