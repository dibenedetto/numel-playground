"""
Example 8: Full API Showcase
=============================
A single script that exercises every major area of the Numel API:

  1. Connection & Status     — ping, status, schema
  2. Workflow CRUD           — add, get, list, remove
  3. Execution               — start, state, results, wait
  4. Batch Execution         — parallel runs
  5. Composition             — sequential pipeline
  6. Real-time Events        — WebSocket event stream
  7. Templates               — save, list, rename, delete
  8. Event Sources           — create timer, start, stop, delete
  9. Console Agent           — toolkits, start, chat, stop
  10. Persistence            — save, load
  11. Documentation          — list, read
  12. Workflow Generation     — generate from description

Prerequisites:
    pip install httpx websockets
    python app/app.py          # start the server

Run:
    python examples/api/08_full_api_showcase.py
"""

import asyncio
import json
import os
import sys
import textwrap
import traceback

import websockets

from client import NumelClient


# ── Helpers ─────────────────────────────────────────────────────

BASE_URL = os.environ.get("NUMEL_URL", "http://localhost:11360")
WS_URL   = BASE_URL.replace("http", "ws") + "/events"

_PASS = 0
_FAIL = 0


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def ok(msg: str):
    global _PASS
    _PASS += 1
    print(f"  [OK] {msg}")


def fail(msg: str, err=None):
    global _FAIL
    _FAIL += 1
    print(f"  [FAIL] {msg}")
    if err:
        for line in traceback.format_exception_only(type(err), err):
            print(f"         {line.rstrip()}")


def preview(data, max_len=120):
    """Pretty-print data, truncated."""
    s = json.dumps(data, default=str) if not isinstance(data, str) else data
    return s[:max_len] + ("..." if len(s) > max_len else "")


def make_workflow(name: str, script: str, description: str = "") -> dict:
    """Build a simple Start → Transform → End workflow."""
    return {
        "options": {"type": "workflow_options", "name": name, "description": description},
        "nodes": [
            {"type": "start_flow",     "extra": {"name": "Start"}},
            {"type": "transform_flow", "extra": {"name": "Compute"},
             "lang": "python", "script": script},
            {"type": "end_flow",       "extra": {"name": "End"}},
        ],
        "edges": [
            {"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
            {"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
        ],
    }


# ── 1. Connection & Status ──────────────────────────────────────

async def test_connection(c: NumelClient):
    section("1. Connection & Status")

    try:
        r = await c.ping()
        assert r.get("message") == "pong", f"Unexpected ping: {r}"
        ok(f"ping → {r['message']}")
    except Exception as e:
        fail("ping", e); return False

    try:
        r = await c.status()
        ok(f"status → uptime={r.get('uptime', '?')}s, workflows={r.get('workflow_count', '?')}")
    except Exception as e:
        fail("status", e)

    try:
        r = await c.schema()
        source = r.get("source", "")
        ok(f"schema → {len(source)} chars of Python source")
    except Exception as e:
        fail("schema", e)

    return True


# ── 2. Workflow CRUD ────────────────────────────────────────────

async def test_workflow_crud(c: NumelClient):
    section("2. Workflow CRUD")
    wf_name = "showcase-crud"

    try:
        wf = make_workflow(wf_name, 'output = {"hello": "world"}', "CRUD test")
        r = await c.add(wf, wf_name)
        ok(f"add → name={r['name']}, status={r['status']}")
    except Exception as e:
        fail("add", e); return

    try:
        r = await c.get(wf_name)
        node_count = len(r.get("workflow", {}).get("nodes", []))
        ok(f"get → {node_count} nodes")
    except Exception as e:
        fail("get", e)

    try:
        names = await c.list()
        assert wf_name in names, f"{wf_name} not in list"
        ok(f"list → {len(names)} workflow(s): {names}")
    except Exception as e:
        fail("list", e)

    try:
        r = await c.remove(wf_name)
        ok(f"remove → {r.get('status', 'done')}")
    except Exception as e:
        fail("remove", e)


# ── 3. Execution ────────────────────────────────────────────────

async def test_execution(c: NumelClient):
    section("3. Execution")
    wf_name = "showcase-exec"
    wf = make_workflow(wf_name, 'output = {"squares": [x**2 for x in range(5)]}')

    try:
        await c.add(wf, wf_name)
        exec_id = await c.start(wf_name)
        ok(f"start → execution_id={exec_id[:12]}...")
    except Exception as e:
        fail("start", e); return

    try:
        st = await c.state(exec_id)
        ok(f"state → status={st.get('state', {}).get('status', '?')}")
    except Exception as e:
        fail("state", e)

    try:
        results = await c.wait(exec_id)
        status = results.get("status", "?")
        outputs = results.get("node_outputs", {})
        ok(f"wait → status={status}, outputs={preview(outputs, 80)}")
    except Exception as e:
        fail("wait/results", e)

    await c.remove(wf_name)


# ── 4. Batch Execution ──────────────────────────────────────────

async def test_batch(c: NumelClient):
    section("4. Batch Execution")
    names = ["showcase-batch-a", "showcase-batch-b"]

    try:
        await c.add(make_workflow(names[0], 'output = {"v": "alpha"}'), names[0])
        await c.add(make_workflow(names[1], 'output = {"v": "beta"}'),  names[1])

        batch = await c.batch_start([{"name": n} for n in names])
        batch_id = batch["batch_id"]
        ok(f"batch_start → batch_id={batch_id[:12]}..., {len(batch['execution_ids'])} executions")

        r = await c.batch_wait(batch_id)
        ok(f"batch_wait → status={r.get('status', '?')}")
    except Exception as e:
        fail("batch", e)

    for n in names:
        try: await c.remove(n)
        except: pass


# ── 5. Composition ──────────────────────────────────────────────

async def test_compose(c: NumelClient):
    section("5. Composition (Pipeline)")
    names = ["showcase-pipe-1", "showcase-pipe-2"]

    try:
        await c.add(make_workflow(names[0], 'output = {"items": ["a", "b", "c"]}'), names[0])
        await c.add(make_workflow(names[1],
            'output = {"summary": f"Got {len(context.get(\\\"items\\\", []))} items"}'
        ), names[1])

        r = await c.compose([
            {"workflow_name": names[0]},
            {"workflow_name": names[1], "input_map": {"context": "prev_output"}},
        ])
        compose_id = r.get("compose_id", r.get("id", "?"))
        ok(f"compose → compose_id={str(compose_id)[:12]}...")

        # Poll for a bit
        for _ in range(10):
            st = await c.compose_state(str(compose_id))
            if st.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)
        ok(f"compose result → status={st.get('status', '?')}")
    except Exception as e:
        fail("compose", e)

    for n in names:
        try: await c.remove(n)
        except: pass


# ── 6. Real-time Events (WebSocket) ─────────────────────────────

async def test_events(c: NumelClient):
    section("6. Real-time Events (WebSocket)")
    wf_name = "showcase-events"
    wf = make_workflow(wf_name, 'output = {"step": "done"}')

    try:
        await c.add(wf, wf_name)
        exec_id = await c.start(wf_name)

        events_received = []
        try:
            async with websockets.connect(WS_URL) as ws:
                # Read events for up to 5 seconds
                async def reader():
                    while True:
                        msg = json.loads(await ws.recv())
                        if msg.get("type") == "workflow_event":
                            ev = msg["event"]
                            events_received.append(ev["event_type"])
                            if ev["event_type"] in ("workflow.completed", "workflow.failed"):
                                return

                await asyncio.wait_for(reader(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

        ok(f"events → received {len(events_received)} events: {events_received[:6]}{'...' if len(events_received) > 6 else ''}")

    except Exception as e:
        fail("events", e)

    try: await c.remove(wf_name)
    except: pass


# ── 7. Templates ────────────────────────────────────────────────

async def test_templates(c: NumelClient):
    section("7. Templates")
    tpl_id = "showcase-tpl-001"

    try:
        templates = await c.templates_list()
        ok(f"templates_list → {len(templates)} template(s)")
    except Exception as e:
        fail("templates_list", e); return

    try:
        tpl = {
            "id": tpl_id,
            "name": "Showcase Template",
            "description": "Created by API showcase",
            "nodeCount": 2,
            "edgeCount": 1,
            "nodes": [{"id": 1, "type": "start_flow"}, {"id": 2, "type": "end_flow"}],
            "links": [],
        }
        r = await c.templates_save(tpl)
        ok(f"templates_save → id={r.get('id', '?')}")
    except Exception as e:
        fail("templates_save", e); return

    try:
        r = await c.templates_rename(tpl_id, "Showcase Template (renamed)")
        ok(f"templates_rename → {r.get('status', '?')}")
    except Exception as e:
        fail("templates_rename", e)

    try:
        r = await c.templates_delete(tpl_id)
        ok(f"templates_delete → {r.get('status', '?')}")
    except Exception as e:
        fail("templates_delete", e)


# ── 8. Event Sources ────────────────────────────────────────────

async def test_event_sources(c: NumelClient):
    section("8. Event Sources")

    try:
        r = await c.event_sources_list()
        ok(f"event_sources_list → {len(r.get('sources', []))} source(s)")
    except Exception as e:
        fail("event_sources_list", e); return

    source_id = None
    try:
        r = await c.event_source_create_timer(interval=60.0, event_type="showcase_tick")
        source_id = r.get("source_id", r.get("id"))
        ok(f"create_timer → source_id={source_id}")
    except Exception as e:
        fail("create_timer", e); return

    try:
        r = await c.event_source_start(source_id)
        ok(f"start → {r.get('status', '?')}")
    except Exception as e:
        fail("event_source_start", e)

    try:
        r = await c.event_source_stop(source_id)
        ok(f"stop → {r.get('status', '?')}")
    except Exception as e:
        fail("event_source_stop", e)

    try:
        r = await c.event_sources_status()
        ok(f"status → {preview(r, 80)}")
    except Exception as e:
        fail("event_sources_status", e)

    try:
        r = await c.event_source_delete(source_id)
        ok(f"delete → {r.get('status', '?')}")
    except Exception as e:
        fail("event_source_delete", e)


# ── 9. Console Agent ────────────────────────────────────────────

async def test_console(c: NumelClient):
    section("9. Console Agent")

    try:
        toolkits = await c.console_toolkits()
        tk_names = [t["name"] for t in toolkits]
        ok(f"console_toolkits → {tk_names}")
    except Exception as e:
        fail("console_toolkits", e); return

    try:
        r = await c.console_start(model_source="ollama", model_name="mistral",
                                   toolkit_names=["console_toolkit"])
        ok(f"console_start → port={r.get('port')}, model={r.get('model_source')}/{r.get('model_name')}")
    except Exception as e:
        fail("console_start", e); return

    try:
        r = await c.console_status()
        ok(f"console_status → started={r.get('started')}, sessions={r.get('sessions', [])}")
    except Exception as e:
        fail("console_status", e)

    try:
        r = await c.console_context()
        ok(f"console_context → has_workflow={r.get('has_workflow')}, active={r.get('execution_active')}")
    except Exception as e:
        fail("console_context", e)

    try:
        r = await c.console_chat("What can you help me with?", include_context=False)
        response = r.get("response", "")[:80]
        ok(f"console_chat → {response}...")
    except Exception as e:
        fail("console_chat", e)

    try:
        r = await c.console_stop()
        ok(f"console_stop → {r.get('status', '?')}")
    except Exception as e:
        fail("console_stop", e)


# ── 10. Persistence ─────────────────────────────────────────────

async def test_persistence(c: NumelClient):
    section("10. Persistence")
    wf_name = "showcase-persist"

    try:
        wf = make_workflow(wf_name, 'output = {"saved": True}')
        await c.add(wf, wf_name)

        r = await c.save(wf_name)
        ok(f"save → {r.get('status', '?')}, path={r.get('path', '?')}")

        saved_path = r.get("path", "")
    except Exception as e:
        fail("save", e); return

    try:
        await c.remove(wf_name)
        # Reload from disk
        if saved_path and os.path.exists(saved_path):
            r = await c.load(saved_path, wf_name)
            ok(f"load → {r.get('status', '?')}")
        else:
            # Try load_all as fallback
            r = await c.load_all()
            ok(f"load_all → {r.get('status', '?')}")
    except Exception as e:
        fail("load", e)

    try: await c.remove(wf_name)
    except: pass


# ── 11. Documentation ───────────────────────────────────────────

async def test_docs(c: NumelClient):
    section("11. Documentation")

    try:
        r = await c.docs_list()
        files = r.get("files", [])
        ok(f"docs_list → {len(files)} file(s)")
        if files:
            print(f"         files: {files[:5]}{'...' if len(files) > 5 else ''}")
    except Exception as e:
        fail("docs_list", e); return

    if files:
        try:
            r = await c.docs_file(files[0])
            content = r.get("content", "")
            ok(f"docs_file({files[0]}) → {len(content)} chars")
        except Exception as e:
            fail("docs_file", e)


# ── 12. Workflow Generation ──────────────────────────────────────

async def test_generation(c: NumelClient):
    section("12. Workflow Generation")

    try:
        r = await c.generation_prompt()
        prompt = r.get("prompt", "")
        ok(f"generation_prompt → {len(prompt)} chars")
    except Exception as e:
        fail("generation_prompt", e); return

    try:
        r = await c.generate_workflow("A workflow that takes text input and converts it to uppercase")
        wf = r.get("workflow", {})
        nodes = wf.get("nodes", [])
        ok(f"generate_workflow → {len(nodes)} nodes, name={wf.get('options', {}).get('name', '?')}")
    except Exception as e:
        fail("generate_workflow", e)


# ── Main ─────────────────────────────────────────────────────────

async def main():
    print(f"Numel API Full Showcase")
    print(f"Server: {BASE_URL}")
    print(f"{'='*60}")

    async with NumelClient(BASE_URL) as c:
        # 1. Test connection first — bail if server is down
        connected = await test_connection(c)
        if not connected:
            print("\nServer not reachable. Start it with: python app/app.py")
            sys.exit(1)

        # 2-12. Run all test sections
        await test_workflow_crud(c)
        await test_execution(c)
        await test_batch(c)
        await test_compose(c)
        await test_events(c)
        await test_templates(c)
        await test_event_sources(c)
        await test_console(c)
        await test_persistence(c)
        await test_docs(c)
        await test_generation(c)

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY: {_PASS} passed, {_FAIL} failed")
    print(f"{'='*60}")
    sys.exit(1 if _FAIL > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
