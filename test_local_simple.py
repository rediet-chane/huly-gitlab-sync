# test_local_simple.py - Uses Secret Token (simpler)
import httpx
import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv()

async def test_local():
    url = "http://localhost:8000/webhook/gitlab"

    payload = {
        "object_kind": "work_item",
        "project": {
            "name": "redichane-project",
            "id": 83669199
        },
        "object_attributes": {
            "id": 999,
            "iid": 1,
            "title": "Test Local Webhook",
            "description": "This is a test from local script",
            "state": "opened",
            "url": "https://gitlab.com/redichane-group/redichane-project/-/issues/1",
            "author": {
                "username": "testuser"
            }
        }
    }

    # Use SECRET token (simpler than HMAC)
    headers = {
        "Content-Type": "application/json",
        "X-Gitlab-Token": os.getenv("GITLAB_WEBHOOK_SECRET", "my_super_secret_token_123")
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

asyncio.run(test_local())