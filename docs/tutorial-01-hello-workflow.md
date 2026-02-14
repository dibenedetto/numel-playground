# Tutorial 1: Hello Workflow

Your first workflow — the simplest possible pipeline: data flows from Start through a Preview node to End.

## What You Will Learn

- How to import a workflow
- The role of Start, Preview, and End nodes
- How to run a workflow and observe results

## The Workflow

```
Start ──> Preview ──> End
```

- **Start** outputs the workflow's initial variables (an empty dictionary `{}` by default)
- **Preview** displays whatever data passes through it — here it shows the empty dict
- **End** marks the workflow as complete

## Steps

1. **Import** the workflow file `tutorial-01-hello-workflow.json` using the Import button or by dragging it onto the canvas.
2. Three nodes appear connected in a line: Start, Preview, End.
3. Click **Start** in the execution controls to run the workflow.
4. Watch the event log — nodes light up as they execute: Start (completes) → Preview (shows `{}`) → End (completes).
5. The Preview node displays `{}` — the empty variables dictionary from Start.

## Experimenting

- **Add execution variables**: In the Execution Options panel, you can pass initial data. These become the Start node's output. Try setting `{"greeting": "Hello!"}` and re-running — the Preview will show the greeting.
- **Double-click the Preview node** to expand it into a larger text view.
- **Alt+click on an edge** to insert a new Preview node on that connection.

## What's Next

In [Tutorial 2](tutorial-02-transform.md), you'll add a Transform node to process data with Python scripts.
