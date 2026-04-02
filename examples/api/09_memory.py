"""
Example 9: Persistent Agent Memory
====================================
Demonstrates the persistent memory system that lets the console agent
remember information across sessions.

The memory store supports:
  - Adding memories (facts, preferences, conversation summaries)
  - Semantic search (ChromaDB) or keyword search (JSON fallback)
  - Retrieving recent memories by type
  - Memory statistics

Prerequisites:
    pip install httpx
    python app/app.py          # start the server

By default the example signs in as `demo` / `demo-pass`.
Override with `NUMEL_USERNAME`, `NUMEL_EMAIL`, and `NUMEL_PASSWORD`.

Run:
    python examples/api/09_memory.py
"""

import asyncio
from client import NumelClient


async def main():
    async with NumelClient() as c:
        await c.ensure_auth()
        print("=== Persistent Agent Memory ===\n")

        # 1. Check memory stats
        stats = await c.memory_stats()
        print(f"1. Memory backend: {stats['backend']}, total entries: {stats['total']}")

        # 2. Add some memories
        print("\n2. Adding memories...")

        m1 = await c.memory_add(
            content="User prefers concise responses and dark theme",
            type="preference",
            importance=0.9,
        )
        print(f"   Added preference: {m1['id']}")

        m2 = await c.memory_add(
            content="Last session we built a webcam pose detection pipeline with MediaPipe",
            type="conversation",
            importance=0.7,
        )
        print(f"   Added conversation: {m2['id']}")

        m3 = await c.memory_add(
            content="Project uses FastAPI backend with vanilla JS frontend and schemagraph for visual editing",
            type="fact",
            importance=0.8,
        )
        print(f"   Added fact: {m3['id']}")

        m4 = await c.memory_add(
            content="Deployment target is a local Windows machine with GPU support via CUDA",
            type="project",
            importance=0.6,
        )
        print(f"   Added project: {m4['id']}")

        # 3. Search memories
        print("\n3. Searching for 'webcam pipeline'...")
        results = await c.memory_search("webcam pipeline", n=3)
        for r in results:
            entry = r["entry"]
            print(f"   [{r['score']:.2f}] ({entry['type']}) {entry['content'][:80]}")

        # 4. Search by type
        print("\n4. Searching preferences...")
        prefs = await c.memory_search("theme style", n=3, type="preference")
        for r in prefs:
            entry = r["entry"]
            print(f"   [{r['score']:.2f}] {entry['content'][:80]}")

        # 5. Get recent memories
        print("\n5. Recent memories:")
        recent = await c.memory_recent(n=5)
        for entry in recent:
            print(f"   [{entry['type']}] {entry['content'][:70]}...")

        # 6. Updated stats
        stats = await c.memory_stats()
        print(f"\n6. Total memories: {stats['total']}")

        # 7. Delete a memory
        print(f"\n7. Deleting memory {m4['id']}...")
        result = await c.memory_delete(m4["id"])
        print(f"   Deleted: {result['deleted']}")

        # 8. Chat with memory context
        # The console agent automatically retrieves relevant memories
        # when processing messages. Start the agent and send a message.
        print("\n8. Starting console agent (memories will be included in context)...")
        try:
            await c.console_start()
            resp = await c.console_chat("What do you remember about our previous work?")
            print(f"   Agent: {resp['response'][:200]}...")
            await c.console_stop()
        except Exception as e:
            print(f"   (Agent not available: {e})")

        print("\n=== Memory example complete ===")


if __name__ == "__main__":
    asyncio.run(main())
