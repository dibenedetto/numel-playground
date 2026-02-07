# Event Source API Examples (curl)

These examples show how to interact with the Event Source API using curl.

## Base URL

```bash
BASE_URL="http://localhost:5000"
```

---

## List All Event Sources

```bash
curl -X POST "$BASE_URL/event-sources/list"
```

---

## Get Registry Status

```bash
curl -X POST "$BASE_URL/event-sources/status"
```

---

## Create Timer Source

```bash
# Main timer - triggers every 2 seconds
curl -X POST "$BASE_URL/event-sources/timer" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "timer_main",
    "name": "Main Timer",
    "interval_ms": 2000,
    "max_triggers": -1,
    "immediate": false
  }'

# Heartbeat timer - triggers every 5 seconds
curl -X POST "$BASE_URL/event-sources/timer" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "timer_heartbeat",
    "name": "Heartbeat",
    "interval_ms": 5000,
    "max_triggers": -1
  }'
```

---

## Create Filesystem Watcher Source

```bash
# Watch the ./data directory for any file changes
curl -X POST "$BASE_URL/event-sources/fswatch" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "fswatch_data",
    "name": "Data Folder Watcher",
    "path": "./data",
    "recursive": true,
    "patterns": ["*"],
    "events": ["created", "modified", "deleted"],
    "debounce_ms": 300
  }'

# Watch for new files in inbox (non-recursive, create only)
curl -X POST "$BASE_URL/event-sources/fswatch" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "fswatch_inbox",
    "name": "Inbox Watcher",
    "path": "./inbox",
    "recursive": false,
    "patterns": ["*"],
    "events": ["created"]
  }'

# Watch for JSON files only
curl -X POST "$BASE_URL/event-sources/fswatch" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "fswatch_json",
    "name": "JSON File Watcher",
    "path": "./data",
    "recursive": true,
    "patterns": ["*.json"],
    "events": ["created", "modified"]
  }'
```

---

## Create Webhook Source

```bash
curl -X POST "$BASE_URL/event-sources/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "webhook_api",
    "name": "API Webhook",
    "endpoint": "/hook/api-events",
    "methods": ["POST"]
  }'
```

---

## Create Browser Source (Webcam/Microphone)

```bash
# Webcam source (event mode - frontend processes, sends events)
curl -X POST "$BASE_URL/event-sources/browser" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "webcam_main",
    "name": "Main Webcam",
    "device_type": "webcam",
    "mode": "event",
    "interval_ms": 1000
  }'

# Microphone source
curl -X POST "$BASE_URL/event-sources/browser" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "mic_main",
    "name": "Main Microphone",
    "device_type": "microphone",
    "mode": "event"
  }'
```

---

## Get Specific Source

```bash
curl -X POST "$BASE_URL/event-sources/get/timer_main"
```

---

## Start/Stop Source

```bash
# Manually start a source
curl -X POST "$BASE_URL/event-sources/timer_main/start"

# Manually stop a source
curl -X POST "$BASE_URL/event-sources/timer_main/stop"
```

---

## Delete Source

```bash
curl -X POST "$BASE_URL/event-sources/delete/timer_main"
```

---

## Complete Setup Script (Bash)

```bash
#!/bin/bash
BASE_URL="http://localhost:5000"

echo "Setting up event sources..."

# Create directories
mkdir -p ./data ./inbox

# Create timer sources
curl -s -X POST "$BASE_URL/event-sources/timer" \
  -H "Content-Type: application/json" \
  -d '{"id":"timer_main","name":"Main Timer","interval_ms":2000}' | jq .

curl -s -X POST "$BASE_URL/event-sources/timer" \
  -H "Content-Type: application/json" \
  -d '{"id":"timer_heartbeat","name":"Heartbeat","interval_ms":5000}' | jq .

# Create fswatch sources
curl -s -X POST "$BASE_URL/event-sources/fswatch" \
  -H "Content-Type: application/json" \
  -d "{\"id\":\"fswatch_data\",\"name\":\"Data Watcher\",\"path\":\"$(pwd)/data\"}" | jq .

curl -s -X POST "$BASE_URL/event-sources/fswatch" \
  -H "Content-Type: application/json" \
  -d "{\"id\":\"fswatch_inbox\",\"name\":\"Inbox Watcher\",\"path\":\"$(pwd)/inbox\"}" | jq .

echo "Done! Listing sources:"
curl -s -X POST "$BASE_URL/event-sources/list" | jq .
```

---

## Testing File Watcher

After setting up the fswatch source, test it by creating files:

```bash
# Trigger file creation events
echo "test content" > ./data/test1.txt
echo "more content" > ./data/test2.json

# Trigger modification events
echo "updated" >> ./data/test1.txt

# Trigger in inbox
touch ./inbox/new_file.txt
```
