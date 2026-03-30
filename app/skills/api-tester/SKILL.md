---
name: api-tester
description: Test and debug REST APIs interactively using the HTTP toolkit
version: 1.0.0
author: system
tags: [api, http, testing, debug]
requires:
  toolkits: [http_toolkit]
examples:
  - "Test the /schema endpoint on localhost:11360"
  - "Hit https://httpbin.org/get and show me the response"
  - "POST to https://httpbin.org/post with body {\"hello\": \"world\"}"
  - "Check if https://api.github.com/repos/fastapi/fastapi returns valid data"
  - "Test my API at localhost:8000/api/users with Bearer token abc123"
  - "Send a DELETE to https://httpbin.org/delete and tell me what it returns"
---

# API Tester Skill

You can help the user test, debug, and explore REST APIs using the HTTP toolkit.

## How to Test APIs

### Basic Request Flow

1. **Understand the request**: Ask the user for the URL, method, headers, and body (if not provided)
2. **Execute**: Use the appropriate HTTP toolkit method (`get`, `post`, `put`, `delete`)
3. **Analyze**: Parse the response and present results clearly

### Request Methods

| User Intent | HTTP Method | Tool |
|-------------|-------------|------|
| "fetch", "get", "read" | GET | `get(url, headers)` |
| "create", "send", "post" | POST | `post(url, data, headers)` |
| "update", "modify" | PUT | `put(url, data, headers)` |
| "remove", "delete" | DELETE | `delete(url, headers)` |

### Response Analysis

After each request, present:
1. **Status code** with meaning (200 OK, 404 Not Found, etc.)
2. **Response body** — formatted JSON (truncated if >50 lines), or text
3. **Key observations** — error messages, pagination info, rate limit headers
4. **Suggestions** — next steps based on the response

### Common Patterns

**Authentication**: When the user provides an API key or token:
- Bearer token: `{"Authorization": "Bearer TOKEN"}`
- API key header: `{"X-API-Key": "KEY"}`
- Basic auth: `{"Authorization": "Basic BASE64"}`

**Pagination**: If the response includes `next`, `page`, `cursor`, or `offset` fields, mention it and offer to fetch the next page.

**Error debugging**: On 4xx/5xx errors:
1. Show the full error response body
2. Check for common issues (missing auth, wrong content-type, malformed JSON)
3. Suggest fixes

## Rules

- Always show the full URL, method, and status code for each request
- Format JSON responses with proper indentation
- Never hardcode or guess API keys — ask the user
- Warn before making destructive requests (DELETE, PUT that overwrites)
- For large response bodies, show a summary and offer the full response on request
- If the API returns HTML instead of JSON, note this and show the first few lines

## Example Prompts

Try these in the assistant console after enabling this skill and `http_toolkit`:

- **"Test the /schema endpoint on localhost:11360"** — sends a POST to the local Numel server and shows the response
- **"Hit https://httpbin.org/get and show me the response"** — simple GET request with response analysis
- **"POST to https://httpbin.org/post with body {"hello": "world"}"** — tests a POST request with JSON body
- **"Check if https://api.github.com/repos/fastapi/fastapi returns valid data"** — fetches a public API and analyzes the structure
- **"Test my API at localhost:8000/api/users with Bearer token abc123"** — authenticated request with token header
- **"Send a DELETE to https://httpbin.org/delete and tell me what it returns"** — tests destructive HTTP method with response analysis
