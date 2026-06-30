# test_local.py
import httpx
import asyncio
import os
import json
import hmac
import hashlib
import base64
import time
import uuid
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

    # Sign the EXACT bytes we're about to send — if httpx re-serializes a
    # dict differently than json.dumps did here, the signature won't match.
    body = json.dumps(payload).encode("utf-8")

    signing_token = os.getenv("GITLAB_WEBHOOK_SIGNING_TOKEN")
    webhook_id = str(uuid.uuid4())
    webhook_timestamp = str(int(time.time()))

    raw_key = base64.b64decode(signing_token.removeprefix("whsec_"))
    message = f"{webhook_id}.{webhook_timestamp}.{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(raw_key, message, hashlib.sha256).digest()
    signature = "v1," + base64.b64encode(digest).decode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "webhook-id": webhook_id,
        "webhook-timestamp": webhook_timestamp,
        "webhook-signature": signature,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, content=body, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")


asyncio.run(test_local())