# Tutorial 5: Events and Timers

React to periodic events using timer sources and event listeners.

## What You Will Learn

- How Timer Source emits periodic events
- How Event Listener waits for events inside a loop
- Linking sources to listeners via `source_id`
- Timeout handling for listeners
- Combining event sources with loops

## The Workflow

```
Start ──> Timer Source (2s) ──> Loop Start ──> Event Listener ──> Transform ──> Preview ──> Loop End ──┐
                                    ^                                                                    │
                                    └──────────────────────── loop edge ────────────────────────────────┘
                                   (then) ──> End
```

1. **Start** kicks off the workflow
2. **Timer Source** registers a timer that fires every 2 seconds (up to 5 times)
3. **Loop Start** repeats up to 10 iterations (more than the timer will fire)
4. **Event Listener** waits for the next event from the timer (with a 5-second timeout)
5. **Transform** formats the event data into a readable string
6. **Preview** displays the formatted message
7. **Loop End** sends execution back to Loop Start

## Key Concepts

### Timer Source

The Timer Source node registers a periodic event emitter:

| Field | Value | Purpose |
|-------|-------|---------|
| `source_id` | `"heartbeat"` | Unique identifier for this source |
| `interval_ms` | `2000` | Fire every 2 seconds |
| `max_triggers` | `5` | Stop after 5 events |
| `immediate` | `true` | Fire the first event immediately |

Each event carries `count` (how many times it has fired) and `elapsed_ms` (time since the source started).

### Event Listener

The Event Listener waits for events from one or more sources:

| Field | Value | Purpose |
|-------|-------|---------|
| `sources` | `["heartbeat"]` | List of source IDs to listen to |
| `mode` | `"any"` | Fire when any source emits (alternatives: `"all"`, `"race"`) |
| `timeout_ms` | `5000` | Give up after 5 seconds of silence |

The `event` output contains the event data from the source that triggered.

### Source–Listener Linking

The `source_id` field on the Timer Source must match an entry in the `sources` list on the Event Listener. This is how the engine knows which events to deliver where.

### Listener Modes

| Mode | Behavior |
|------|----------|
| `any` | Fire when any listed source emits an event |
| `all` | Wait until every listed source has emitted at least one event |
| `race` | Fire on the first event, then ignore subsequent sources |

## Steps

1. **Import** `tutorial-05-events.json`.
2. Click **Start**. The timer begins firing immediately.
3. Watch the Preview update every 2 seconds: `"Event #1 at 0ms"`, `"Event #2 at 2000ms"`, etc.
4. After 5 timer events, the listener times out and the loop exits.
5. Execution reaches End.

## Other Event Sources

Numel supports several event source types beyond timers:

| Source | What it watches |
|--------|-----------------|
| **Timer Source** | Periodic time intervals |
| **FS Watch Source** | Filesystem changes (file created, modified, deleted) |
| **Webhook Source** | Incoming HTTP requests to a custom endpoint |
| **Browser Source** | Webcam, microphone, or screen capture from the browser |

All sources follow the same pattern: set a `source_id`, then reference it in an Event Listener's `sources` list.

## Experimenting

- **Change the interval**: Edit `interval_ms` on the Timer Source for faster or slower events.
- **Add a second timer**: Add another Timer Source with a different `source_id` and interval. Add it to the listener's `sources` list and switch `mode` to `"all"` to wait for both.
- **Use a timeout**: Set a very short `timeout_ms` on the listener and observe the `timed_out` output.

## What's Next

In [Tutorial 6](tutorial-06-agent.md), you'll wire together configuration nodes to build a full AI agent with tools and chat.
