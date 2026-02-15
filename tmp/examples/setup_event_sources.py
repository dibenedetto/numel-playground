#!/usr/bin/env python3
"""
Event Source Setup Script

This script sets up event sources for testing the new event trigger system.
Run this after starting the backend server.

Usage:
    python setup_event_sources.py [--base-url URL]

Examples:
    python setup_event_sources.py
    python setup_event_sources.py --base-url http://localhost:8000
"""

import argparse
import json
import os
import requests
import sys


DEFAULT_BASE_URL = "http://localhost:8000"


def api_post(base_url: str, endpoint: str, data: dict = None) -> dict:
    """Make a POST request to the API"""
    url = f"{base_url}{endpoint}"
    try:
        response = requests.post(url, json=data or {})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {base_url}")
        print("Make sure the backend server is running.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: {e}")
        print(f"Response: {response.text}")
        return None


def list_sources(base_url: str):
    """List all registered event sources"""
    print("\n=== Current Event Sources ===")
    result = api_post(base_url, "/event-sources/list")
    if result and result.get("sources"):
        for source in result["sources"]:
            status = source.get("status", "unknown")
            source_type = source.get("source_type", "?")
            source_id = source.get("id", "?")
            print(f"  [{status:8}] {source_type:10} {source_id}")
    else:
        print("  (no sources registered)")
    print()


def create_timer_source(base_url: str, source_id: str, name: str, interval_ms: int):
    """Create a timer event source"""
    print(f"Creating timer source: {source_id} ({interval_ms}ms interval)")
    result = api_post(base_url, "/event-sources/timer", {
        "id": source_id,
        "name": name,
        "interval_ms": interval_ms,
        "max_triggers": -1,
        "immediate": False
    })
    if result:
        print(f"  -> Created: {result.get('status')}")
    return result


def create_fswatch_source(base_url: str, source_id: str, name: str, path: str, patterns: list = None):
    """Create a filesystem watcher event source"""
    # Ensure directory exists
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        print(f"  Creating directory: {abs_path}")
        os.makedirs(abs_path, exist_ok=True)

    print(f"Creating fswatch source: {source_id} (watching {abs_path})")
    result = api_post(base_url, "/event-sources/fswatch", {
        "id": source_id,
        "name": name,
        "path": abs_path,
        "recursive": True,
        "patterns": patterns or ["*"],
        "events": ["created", "modified", "deleted"],
        "debounce_ms": 300
    })
    if result:
        print(f"  -> Created: {result.get('status')}")
    return result


def delete_source(base_url: str, source_id: str):
    """Delete an event source"""
    print(f"Deleting source: {source_id}")
    result = api_post(base_url, f"/event-sources/delete/{source_id}")
    if result:
        print(f"  -> Deleted")
    return result


def setup_demo_sources(base_url: str):
    """Set up all demo event sources"""
    print("\n" + "="*60)
    print("Setting up Demo Event Sources")
    print("="*60)

    # Timer sources
    create_timer_source(base_url, "timer_main", "Main Timer (2s)", 2000)
    create_timer_source(base_url, "timer_heartbeat", "Heartbeat Timer (5s)", 5000)

    # Filesystem watcher sources
    create_fswatch_source(base_url, "fswatch_data", "Data Folder Watcher", "./data")
    create_fswatch_source(base_url, "fswatch_inbox", "Inbox Watcher", "./inbox")

    print("\n" + "="*60)
    print("Setup Complete!")
    print("="*60)

    list_sources(base_url)

    print("Next steps:")
    print("  1. Open the workflow UI in your browser")
    print("  2. Load one of the event workflow examples:")
    print("     - workflow_event_timer_example.json")
    print("     - workflow_event_fswatch_example.json")
    print("     - workflow_event_multi_source_example.json")
    print("  3. Run the workflow")
    print("  4. For fswatch, create/modify files in ./data or ./inbox")
    print()


def cleanup_demo_sources(base_url: str):
    """Remove all demo event sources"""
    print("\n" + "="*60)
    print("Cleaning up Demo Event Sources")
    print("="*60)

    for source_id in ["timer_main", "timer_heartbeat", "fswatch_data", "fswatch_inbox"]:
        delete_source(base_url, source_id)

    print("\nCleanup complete!")
    list_sources(base_url)


def main():
    parser = argparse.ArgumentParser(description="Setup event sources for testing")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend API base URL")
    parser.add_argument("--cleanup", action="store_true", help="Remove demo sources instead of creating them")
    parser.add_argument("--list", action="store_true", help="Just list current sources")

    args = parser.parse_args()

    if args.list:
        list_sources(args.base_url)
    elif args.cleanup:
        cleanup_demo_sources(args.base_url)
    else:
        setup_demo_sources(args.base_url)


if __name__ == "__main__":
    main()
