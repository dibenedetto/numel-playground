# Example Workflows

These JSON files are meant to be loaded into the **current space**. In the
GUI, use **Workflow -> Import** or the Gallery actions to replace the current
canvas, then save and run that one workflow for the selected space.

Canvas tags inside the editor still work as visual organization aids, but the
persisted backend model is now **one current workflow per space**.

## webcam-frontend-ml.json
**Nodes**: `start` -> `browser_source` (webcam) -> `end`

Shows client-side (browser-only) pose detection with zero backend involvement:
- Minimal workflow, just enough to instantiate the webcam overlay node
- No backend workflow execution needed for pose rendering
- After loading it into the current space, click **Start** on the webcam overlay to enable the camera, then click **ML On** to start MediaPipe inference in the browser
- Skeleton is drawn directly on the overlay canvas; keypoints can also be forwarded to the backend via WebSocket

Requires: browser with webcam and internet access for the MediaPipe CDN on first load.

---

## webcam-pose-detection.json
**Nodes**: `start` -> `browser_source` (webcam) -> `loop_start` -> `event_listener` -> `transform` (extract frame) -> `pose_detector` -> `stream_display` -> `loop_end`

Shows:
- `browser_source_flow` with `device_type="webcam"`, `mode="event"`, `interval_ms=150`, explicit `source_id="cam_pose"`
- **Explicit `source_id` is required**: the workflow and browser overlay must use the same ID so `stream_display_flow` can route overlay events back via `/ws/stream/cam_pose`
- `event_listener_flow` waiting on `sources.cam` (multi-input dotted slot)
- `pose_detector_flow` receiving a bare-base64 JPEG frame and outputting `keypoints`
- `stream_display_flow` with `render_type="pose"` routing the skeleton back to the browser
- Transform handling both event-mode frames (`data`) and stream-mode frames (`frame`)
- `loop_start_flow` / `loop_end_flow` for continuous capture; the `loop=true` edge is a visual hint

Requires: browser with webcam and `pip install mediapipe Pillow numpy` on the backend.

---

## timer-driven-agent.json
**Nodes**: `start` -> `backend/model/agent_options/agent_config` (wired) -> `timer_source` (10s) -> `loop_start` -> `event_listener` -> `transform` (build prompt) -> `agent_flow` -> `transform` (extract reply) -> `preview` -> `loop_end`

Shows:
- `timer_source_flow` with `interval_ms=10000`, `immediate=true`
- `event_listener_flow` collecting timer ticks
- Full agent subgraph: `backend_config` -> `model_config` -> `agent_options_config` -> `agent_config` -> `agent_flow`
- Periodic LLM analysis driven by a timer

Requires: Ollama + Mistral, or adjust `model_config` for your provider.

---

## foreach-list-processor.json
**Nodes**: `start` -> `user_input` -> `transform` (split CSV) -> `for_each_start` -> `transform` (uppercase + index) -> `preview` -> `for_each_end` -> `end`

Shows:
- `user_input_flow` collecting a comma-separated string from the user
- `for_each_start_flow` iterating over a list; `current` carries the current item
- Per-iteration `preview_flow` so each processed item is shown as the loop runs
- `loop=true` edge from `for_each_start` to `for_each_end` as a UI loop hint

---

## webhook-json-handler.json
**Nodes**: `start` -> `webhook_source` (`/hook/events`) -> `loop_start` -> `event_listener` -> `transform` (process payload) -> `preview` (JSON) -> `loop_end`

Shows:
- `webhook_source_flow` listening on a custom HTTP endpoint (`/hook/events`)
- `event_listener_flow` blocking until an HTTP POST arrives
- Transform annotating the payload with a timestamp and extracting keys
- `preview_flow` with `hint="json"` for pretty JSON display

Test:
`curl -X POST http://localhost:11360/hook/events -H "Content-Type: application/json" -d '{"msg":"hello"}'`

---

## microphone-audio-gate.json
**Nodes**: `start` -> `browser_source` (microphone, 0.5s chunks) -> `loop_start` -> `event_listener` -> `gate` (threshold=6, fires every 3s) -> `transform` (check gate state) -> `preview` (JSON) -> `loop_end`

Shows:
- `browser_source_flow` with `device_type="microphone"` and `mode="event"`
- `gate_flow` accumulating 6 chunks (= 3 seconds of audio) before firing
- `gate_flow` outputs: `accumulated`, `triggered`, and `count`
- Transform differentiating accumulating vs batch-ready state
- A batch-triggering pattern you can later replace with an agent or transcription node

Requires: browser microphone permission.
