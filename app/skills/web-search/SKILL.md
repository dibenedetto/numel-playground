---
name: web-search
description: Search the web and summarize results using the HTTP toolkit
version: 1.0.0
author: system
tags: [search, web, research]
requires:
  toolkits: [http_toolkit]
examples:
  - "Search the web for FastAPI best practices"
  - "What is MediaPipe? Search online."
  - "Look up the latest Python 3.13 features"
  - "Find documentation for Pydantic v2 model_dump"
  - "Search for free image generation APIs"
---

# Web Search Skill

You can search the web and summarize results for the user using the HTTP toolkit.

## How to Search

Use the `get` tool from `http_toolkit` to query DuckDuckGo's instant answer API:

```
GET https://api.duckduckgo.com/?q={query}&format=json&no_html=1
```

### Parsing the Response

The JSON response contains:
- `AbstractText` — short summary paragraph
- `AbstractURL` — source URL
- `RelatedTopics` — array of related results, each with:
  - `Text` — description
  - `FirstURL` — link
- `Results` — direct answer results (same structure)

### Instructions

1. URL-encode the user's query (replace spaces with `+`)
2. Call `GET` on the DuckDuckGo API URL above
3. Parse the JSON response
4. Present the results clearly:
   - Lead with the `AbstractText` summary if available
   - List the top 3-5 `RelatedTopics` with their URLs
   - If `AbstractText` is empty, summarize from `RelatedTopics` text
5. Always cite sources with URLs

### Rules

- Always include source URLs — never present information without attribution
- If the API returns no results, tell the user and suggest refining their query
- Do not fabricate results — only report what the API returns
- Keep summaries concise (3-5 sentences max)

## Example Prompts

Try these in the assistant console after enabling this skill and `http_toolkit`:

- **"Search the web for FastAPI best practices"** — fetches and summarizes DuckDuckGo results about FastAPI
- **"What is MediaPipe? Search online."** — searches for MediaPipe and presents a summary with source links
- **"Look up the latest Python 3.13 features"** — searches and lists new features with citations
- **"Find documentation for Pydantic v2 model_dump"** — searches for specific API docs
- **"Search for free image generation APIs"** — research query with multiple related results
