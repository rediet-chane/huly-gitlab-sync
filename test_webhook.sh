#!/bin/bash
# A simple script to test your webhook locally

curl -X POST http://localhost:8000/webhook/gitlab \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Token: my_super_secret_token_123" \
  -d '{
    "object_kind": "issue",
    "project": {
      "name": "Test Project"
    },
    "object_attributes": {
      "id": 12345,
      "title": "Test Issue from Script",
      "description": "This is a test issue",
      "state": "opened",
      "author": {
        "username": "testuser"
      }
    }
  }'