# test_webhook.py
import httpx
import asyncio

async def test_webhook():
    url = "https://unworried-reptilian-election.ngrok-free.dev/webhook/gitlab"

    payload = {
        "object_kind": "work_item",
        "project": {"name": "redichane-project"},
        "object_attributes": {
            "id": 999,
            "iid": 1,
            "title": "Test Webhook",
            "state": "opened"
        }
    }

    print("🔑 Testing with Signing Token...")
    headers_signing = {
        "Content-Type": "application/json",
        "X-Gitlab-Webhook-Signature": "whsec_jPcvbkW4PBu0p0BexwEtser7yNmzyi0CS5C1Yjfg0o8="
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers_signing)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}\n")

    print("🔑 Testing with Secret Token...")
    headers_secret = {
        "Content-Type": "application/json",
        "X-Gitlab-Token": "my_super_secret_token_123"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers_secret)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

asyncio.run(test_webhook())