# Huly-GitLab Sync Service

A webhook-based integration service that syncs issues between GitLab and Huly.

## Features

- ✅ **GitLab Webhook Receiver** - Secure webhook endpoint for GitLab events
- ✅ **Token Validation** - Supports both signing and secret tokens
- ✅ **Issue Processing** - Parses GitLab issue data
- ✅ **Logging** - Logs all issues for review
- ✅ **Ngrok Support** - Public URL for testing

## Limitations

Huly's public REST API does not currently support creating issues. The service:
1. Attempts to connect via WebSocket (experimental)
2. Logs issues when Huly API is unavailable

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt