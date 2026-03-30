---
name: web-search
description: Search the web and summarize results using the HTTP toolkit
version: 1.0.0
author: system
tags: [search, web, research]
requires:
  toolkits: [http_toolkit]
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

### Example

User asks: "What is FastAPI?"

1. GET `https://api.duckduckgo.com/?q=FastAPI&format=json&no_html=1`
2. Extract `AbstractText`: "FastAPI is a modern, fast web framework for building APIs with Python..."
3. List related topics with links
4. Present a concise summary

### Rules

- Always include source URLs — never present information without attribution
- If the API returns no results, tell the user and suggest refining their query
- Do not fabricate results — only report what the API returns
- Keep summaries concise (3-5 sentences max)
