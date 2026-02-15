# Tutorial 7: Preview and Media Types

Explore the Preview node's ability to display text, JSON, images, audio, video, and 3D models — including live browser media capture.

## What You Will Learn

- How Preview auto-detects data types
- Displaying text, JSON, and images
- Using the `hint` field to override auto-detection
- Capturing live media from webcam, microphone, and screen
- Supported media formats (audio, video, 3D)
- Alt+click edge shortcut for quick previews

## The Workflow

```
         ┌──> Text Output ──> Text Preview ──────────────────┐
         ├──> JSON Output ──> JSON Preview ──────────────────┤
         ├──> Image Output ──> Image Preview ────────────────┤
Start ──┤  ├──> Dict as Text ──> Hint: Text ──────────────────┤──> End
         ├──> Webcam Capture ──> Webcam Listener ──> Webcam Preview ──┤
         ├──> Mic Capture ──> Mic Listener ──> Audio Preview ─────────┤
         └──> Screen Capture ──> Screen Listener ──> Screen Preview ──┘
```

Seven parallel branches demonstrate different preview types. The first four use Transform nodes to produce data, while the last three use Browser Source nodes to capture live media from your browser. All branches converge at End.

## Preview Types

### Text

The Transform outputs a plain string:

```python
output = 'Hello! This is plain text displayed in a Preview node.'
```

The Preview auto-detects it as text and renders it in a text area.

### JSON

The Transform outputs a dictionary:

```python
output = {
    'name': 'Numel Playground',
    'version': '1.0',
    'features': ['workflows', 'agents', 'tools'],
    'stats': {'nodes': 42, 'edges': 56}
}
```

The Preview auto-detects it as JSON and renders a formatted, syntax-highlighted view.

### Image

The Transform builds a data URL with a base64-encoded PNG:

```python
output = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode()
```

The Preview detects the `data:image/` prefix and renders an inline image. In this tutorial, it's a tiny 8x8 red square — but any PNG, JPEG, or GIF data URL works.

### Hint Override

The Transform outputs a dictionary (normally shown as JSON), but the Preview's `hint` field is set to `"text"`:

```json
{ "type": "preview_flow", "hint": "text" }
```

This forces the Preview to render the dict as plain text instead of formatted JSON.

## Browser Media Capture

The last three branches use **Browser Source** nodes to capture live media from the browser and display it in Preview nodes.

### Webcam

The Webcam Capture node requests camera access from your browser and takes a snapshot every 3 seconds:

| Field | Value | Purpose |
|-------|-------|---------|
| `device_type` | `"webcam"` | Capture from the camera |
| `mode` | `"event"` | Emit snapshots as events |
| `interval_ms` | `3000` | Capture every 3 seconds |
| `source_id` | `"webcam_src"` | ID for the event listener |

The Event Listener waits for the next snapshot, and the Preview displays it as an inline image (the webcam frame is delivered as a `data:image/...` data URL).

### Microphone

The Mic Capture node requests microphone access and records audio clips every 5 seconds:

| Field | Value | Purpose |
|-------|-------|---------|
| `device_type` | `"microphone"` | Capture from the microphone |
| `mode` | `"event"` | Emit audio clips as events |
| `interval_ms` | `5000` | Record a 5-second clip |
| `audio_format` | `"wav"` | Encode as WAV |
| `source_id` | `"mic_src"` | ID for the event listener |

The Preview renders an HTML5 audio player for the captured clip.

### Screen

The Screen Capture node requests screen-sharing permission and takes a screenshot every 3 seconds:

| Field | Value | Purpose |
|-------|-------|---------|
| `device_type` | `"screen"` | Capture the screen |
| `mode` | `"event"` | Emit screenshots as events |
| `interval_ms` | `3000` | Capture every 3 seconds |
| `source_id` | `"screen_src"` | ID for the event listener |

The Preview displays the screenshot as an inline image.

### Browser Permissions

Each Browser Source triggers a browser permission prompt the first time it runs:

- **Webcam**: "Allow access to your camera?"
- **Microphone**: "Allow access to your microphone?"
- **Screen**: "Share your screen?" (you pick a window, tab, or entire screen)

These permissions are per-session. The browser remembers your choice until you close the tab.

## Auto-Detection Rules

The Preview node detects the data type automatically:

| Data | Detection | Display |
|------|-----------|---------|
| String (plain) | No special prefix | Text area |
| String (JSON-like) | Starts with `{` or `[` | Formatted JSON |
| Dict or List | Object type | Formatted JSON |
| `data:image/...` | Data URL prefix | Inline image |
| `data:audio/...` | Data URL prefix | Audio player |
| `data:video/...` | Data URL prefix | Video player |
| URL ending in `.glb`/`.gltf` | File extension | 3D model viewer (Three.js) |

## Additional Media Types

These types are supported but not included in the tutorial workflow (they require external files or larger data):

### Audio

Pass a data URL with an audio MIME type:

```python
output = 'data:audio/wav;base64,' + base64.b64encode(wav_bytes).decode()
```

The Preview renders an HTML5 audio player with play/pause controls.

### Video

Pass a data URL or a URL to a video file:

```python
output = 'data:video/mp4;base64,' + base64.b64encode(mp4_bytes).decode()
```

The Preview renders an HTML5 video player.

### 3D Models

Pass a URL (or data URL) to a `.glb` or `.gltf` file:

```python
output = '/path/to/model.glb'
```

The Preview renders an interactive 3D viewer powered by Three.js with orbit controls.

## Quick Preview Shortcut

You don't need to add Preview nodes manually. **Alt+click** on any edge to insert a Preview node inline. This is useful for debugging — quickly see what data flows between two nodes without modifying the workflow structure.

## Steps

1. **Import** `tutorial-07-preview-media.json`.
2. Click **Start**.
3. Observe seven Preview nodes, each showing a different type:
   - **Text Preview**: Plain string
   - **JSON Preview**: Formatted dictionary with syntax highlighting
   - **Image Preview**: A small red square image
   - **Hint: Text**: A dictionary rendered as text (not JSON)
   - **Webcam Preview**: Live camera snapshot (grant permission when prompted)
   - **Audio Preview**: Recorded microphone clip with playback controls
   - **Screen Preview**: Screenshot of your selected screen/window
4. Click on each Preview to expand it for a larger view.

## Experimenting

- **Try your own image**: Replace the hex bytes in the Image Output transform with a base64-encoded image of your choice.
- **Drop a file**: Drag an image, audio, or video file onto the canvas — a Preview node is created automatically.
- **Change hints**: Edit the `hint` field on any Preview node. Valid values: `text`, `json`, `image`, `audio`, `video`, `3d`.
- **Edge preview**: Alt+click on an edge between any two nodes to see intermediate data.

## What's Next

In [Tutorial 8](tutorial-08-generate.md), you'll learn to use the `/gen` command to generate entire workflows from natural language descriptions.
