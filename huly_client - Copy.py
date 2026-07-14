import os
import json
import asyncio
from typing import Optional
from src.config import settings

class HulyClient:
    """Client for interacting with Huly"""
    
    def __init__(self):
        self.email = settings.HULY_EMAIL
        self.password = settings.HULY_PASSWORD
        self.workspace = settings.HULY_WORKSPACE
        self.url = settings.HULY_URL
        self.connected = False
        self.token = None
    
    async def create_issue(self, title: str, description: str, status: str = "Todo") -> bool:
        """Create an issue in Huly"""
        
        if not self.email or not self.password:
            print("⚠️ Huly credentials not configured")
            return False
        
        print(f"📤 Creating issue in Huly: {title[:50]}...")
        return await self._create_with_cli(title, description, status)
    
    async def _create_with_cli(self, title: str, description: str, status: str) -> bool:
        """Create issue using Huly CLI"""
        import subprocess
        
        cmd = [
            "npx", "-y", "@bgx4k3p/huly-mcp-server",
            "create-issue",
            "--title", title,
            "--description", description,
            "--workspace", self.workspace,
            "--email", self.email,
            "--password", self.password
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print(f"✅ Huly issue created!")
                return True
            else:
                print(f"❌ CLI failed: {result.stderr[:200]}")
                return False
                
        except Exception as e:
            print(f"❌ Error with CLI: {e}")
            return False