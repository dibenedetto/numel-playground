"""
Example 09 — Memory, Channels, and Self-Improving Agent
========================================================
Demonstrates the new Numel Playground features:
  1. Persistent agent memory (store, search, recall)
  2. Channel adapters (list types, add webhook channel)
  3. Self-improving agent (via code_toolkit)

Prerequisites:
  - Server running at http://localhost:11360
  - An authenticated user (defaults to demo / demo-pass)

Usage:
  cd examples/api
  python 09_memory_channels.py
"""

import asyncio
from client import NumelClient


async def main():
	async with NumelClient() as c:
		await c.ensure_auth()
		print("=" * 60)
		print("Example 09: Memory, Channels, Self-Improving Agent")
		print("=" * 60)

		# ─────────────────────────────────────────────────────────
		# 1. PERSISTENT MEMORY
		# ─────────────────────────────────────────────────────────
		print("\n── 1. Persistent Memory ──")

		# Check memory stats
		stats = await c.memory_stats()
		print(f"Memory backend: {stats.get('backend', '?')}, entries: {stats.get('total', 0)}")

		# Add some memories
		m1 = await c.memory_add(
			"User prefers dark theme and concise responses",
			type="preference",
			importance=0.8,
		)
		print(f"Added preference memory: {m1['id']}")

		m2 = await c.memory_add(
			"Last session: built a webcam pose detection pipeline with 10 nodes",
			type="conversation",
			importance=0.6,
		)
		print(f"Added conversation memory: {m2['id']}")

		m3 = await c.memory_add(
			"Project uses FastAPI backend with vanilla JS frontend",
			type="fact",
			importance=0.7,
		)
		print(f"Added fact memory: {m3['id']}")

		# Search memories
		results = await c.memory_search("webcam pose detection", n=3)
		print(f"\nSearch 'webcam pose detection': {len(results)} results")
		for r in results:
			score = r.get("score", 0)
			text  = r["entry"]["content"][:80]
			print(f"  [{score:.2f}] {text}")

		# Get recent memories
		recent = await c.memory_recent(n=5)
		print(f"\nRecent memories: {len(recent)}")
		for m in recent:
			print(f"  [{m['type']}] {m['content'][:60]}")

		# Updated stats
		stats = await c.memory_stats()
		print(f"\nTotal memories: {stats['total']}")

		# ─────────────────────────────────────────────────────────
		# 2. CHANNEL ADAPTERS
		# ─────────────────────────────────────────────────────────
		print("\n── 2. Channel Adapters ──")

		# List available channel types
		types = await c.channel_types()
		print("Available channel types:")
		for t in types:
			print(f"  {t['type']}: {t['doc']}")

		# List active channels
		channels = await c.channel_list()
		print(f"\nActive channels: {len(channels)}")

		# Add a webhook channel (no external service needed)
		webhook = await c.channel_add(
			name="test-webhook",
			channel_type="webhook",
			auto_start=True,
			secret="my_secret",
			response_format="json",
		)
		print(f"\nAdded webhook channel: {webhook['id']} ({webhook['status']})")

		# Start it
		started = await c.channel_start(webhook["id"])
		print(f"Channel status: {started['status']}")

		# List channels again
		channels = await c.channel_list()
		print(f"Active channels: {len(channels)}")
		for ch in channels:
			print(f"  [{ch['channel_type']}] {ch['name']} — {ch['status']}")

		# Stop and remove
		await c.channel_stop(webhook["id"])
		await c.channel_remove(webhook["id"])
		print("Webhook channel removed")

		# ─────────────────────────────────────────────────────────
		# 3. CONSOLE AGENT (with memory + toolkits)
		# ─────────────────────────────────────────────────────────
		print("\n── 3. Console Agent with Memory ──")

		# Check available toolkits
		toolkits = await c.console_toolkits()
		print("Available toolkits:")
		for tk in toolkits:
			status = "enabled" if tk["enabled"] else "disabled"
			label  = "(built-in)" if tk["builtin"] else ""
			print(f"  [{status}] {tk['name']} {label} — {tk['description'][:50]}")

		# Start agent with code_toolkit enabled
		try:
			start = await c.console_start(
				model_source="ollama",
				model_name="mistral:latest",
				toolkit_names=["console_toolkit", "code_toolkit"],
			)
			print(f"\nAgent started on port {start['port']}")
			print(f"Toolkits: {start['toolkit_names']}")

			# Chat — the agent has memory context injected automatically
			result = await c.console_chat("What do you remember about me?")
			print(f"\nAgent response: {result['response'][:200]}")
			if result.get("tool_calls"):
				print(f"Tool calls: {[tc['name'] for tc in result['tool_calls']]}")

		except Exception as e:
			print(f"Agent start failed (expected if ollama not running): {e}")

		# ─────────────────────────────────────────────────────────
		# CLEANUP
		# ─────────────────────────────────────────────────────────
		print("\n── Cleanup ──")

		# Delete test memories
		for m in [m1, m2, m3]:
			await c.memory_delete(m["id"])
		stats = await c.memory_stats()
		print(f"Memories after cleanup: {stats['total']}")

		print("\nDone!")


if __name__ == "__main__":
	asyncio.run(main())
