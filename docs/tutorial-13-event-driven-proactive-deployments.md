This tutorial shows how to make a deployment act on events instead of only on a timer.

The key idea is:

- a proactive deployment does not need to wake up every N seconds
- it can also wake up when real events arrive from one or more sources

That is now part of Numel’s workflow-backed deployment model.

## What You Will Learn

- how to think about event-driven proactive tasks
- how to configure an event-driven proactive deployment with one listener and one or more sources
- how to inspect that behavior in the deployment panel
- how to recognize the workflow-backed trigger shape in the workbench

## Before You Start

You should already have:

- Numel running locally
- a channel available for delivery
- basic familiarity with assistant deployments

If you have not created a deployment yet, do [tutorial-11-assistant-deployments.md](tutorial-11-assistant-deployments.md) first.

## The Mental Model

There are now two broad proactive styles:

- **time-driven**
  The deployment wakes up on a schedule.
- **event-driven**
  The deployment wakes up because something happened.

Examples of event-driven sources now include:

- `webhook`
- `channel`
- `fswatch`
- `browser`

So a proactive assistant can now behave more like:

- “wake up when an incident webhook arrives”
- “wake up when an incident webhook arrives or when the intake channel receives a matching message”

instead of only:

- “wake up every 15 minutes”

The important modeling rule is:

- source nodes produce events
- one `event_listener_flow` fans those sources in
- the listener mode decides whether the task wakes up on `any`, `all`, or `race`

So a single event listener absolutely can do the job.
What it should listen to is a set of source nodes, not only one hard-coded trigger.

## Part 1: Start From The Example Config

Numel now includes an event-driven deployment example here:

- [assistant-deployment-webhook-proactive.json](../examples/assistant-deployment-webhook-proactive.json)

Read it as an operator-facing reference, not as a workflow file.

The important parts are:

- `trigger_mode: "any"`
- `trigger_sources`
- one `webhook` source
- one `channel` source
- delivery `channel_id`
- delivery `recipient_id`

That tells Numel:

- this task is not timer-driven
- it should wake up from either configured source
- when it responds, it should deliver through the configured channel and recipient

## Part 2: Create The Deployment

Open **Assistant Deployments** and create a deployment with values like:

- **Name**: `Webhook Incident Triage`
- **Profile**: `ops`
- **Instructions**: summarize webhook incidents and surface next actions
- **Channels**: choose the delivery channel
- **Proactive Delivery**: `Require approval before sending`
- **Tool Execution**: `Require approval before each tool call`

Then add a proactive task seed with:

- **Name**: `Inbound Incident Fan-In`
- **Trigger**: any simple event source you want as the first seed
- **Prompt**: summarize the triggering event and propose the next operator action
- **Send response**: enabled

Important detail:

- leave the timer interval at `0` for event-driven sources

because the task is event-driven, not schedule-driven.

The deployment edit dialog is still intentionally simple.
The full multi-source fan-in shape belongs in the network workflow view.

## Part 3: Turn The Seed Into A Real Fan-In Listener

1. Open **Assistant Deployments**.
2. Click **Open Live Network In Workbench**.
3. Find your proactive task.
4. Make sure the trigger side looks like this:

- one `webhook_source_flow`
- optionally one `channel_receive_flow` or another source node
- one `event_listener_flow`
- one proactive runtime node

Wire every source into the same listener through its `sources.trigger_*` inputs.

Set the listener mode to one of:

- `any`
  The task wakes up when any source fires.
- `all`
  The task waits until all sources have fired.
- `race`
  The first source wins and wakes the task immediately.

For the common incident-response case, `any` is the right default.

## Part 4: Send A Test Event

Once the deployment is active, send a test webhook request.

Example:

```bash
curl -X POST http://localhost:11360/hook/incidents \
  -H "Content-Type: application/json" \
  -d "{\"severity\":\"high\",\"service\":\"billing-api\",\"message\":\"Refund processing backlog exceeded threshold\"}"
```

If you configured a webhook secret in the trigger, include the matching header or auth mechanism used by your setup.

What should happen:

1. the event wakes one source node
2. the listener receives that event
3. the proactive task wakes up
4. the deployment processes the payload
5. if proactive delivery approval is enabled, the outgoing response pauses for approval
6. after approval, the response is delivered to the configured channel/recipient

Then, if you also configured a channel source, send a matching message into that channel and confirm the same task can wake up from that second source too.

## Part 5: Operate It From The Panel

The deployment panel is now the easiest way to supervise this flow.

Use:

- `Inspect` on the deployment
- `Inspect Network` for the full live system

Look especially at:

- `Proactive Runs`
- `Approvals`
- `Recent Activity`
- `Failures`

If you want a clean record of what happened, use:

- `Copy Snapshot`

That gives you a text summary you can paste into notes, tickets, or an incident thread.

## Part 6: See The Workflow-Backed Trigger Shape

Open the live network in the workbench:

1. open **Assistant Deployments**
2. click **Open Live Network In Workbench**

Around the proactive task, you should now see the real fan-in subgraph rather than hidden single-trigger metadata.

For a multi-source task, the shape is conceptually:

- one or more source nodes such as:
  - `webhook_source_flow`
  - `channel_receive_flow`
  - `fswatch_source_flow`
  - `browser_source_flow`
- one `event_listener_flow`
- one proactive runtime node

That matters because the trigger is now represented through the same workflow language as the rest of Numel.

## Suggested Variations

After the basic version works, try one of these:

- keep the webhook + channel pair and change the listener mode from `any` to `race`
- replace the channel source with `fswatch`
- keep the same listener and add a third source
- keep the same deployment but add both a timer-driven task and an event-driven fan-in task

This is a good way to build intuition for when the assistant should:

- poll on a schedule
- wake only when one source fires
- or coordinate multiple sources through one listener

## What You Built

At the end of this tutorial, you have:

- a deployment with an event-driven proactive task
- a real multi-source listener shape
- one proactive task that can wake from more than one event source
- approval support for outgoing proactive delivery
- an inspectable workflow-backed trigger shape

That is the important shift:

- proactive assistants in Numel are no longer only scheduled helpers
- and event-driven tasks are no longer flattened into one hidden trigger
- they can now behave like runtime services built from source nodes plus one listener

## Where To Go Next

- [assistant-deployments.md](assistant-deployments.md)
- [assistant-deployment-operations.md](assistant-deployment-operations.md)
- [tutorial-12-workflow-backed-runtime.md](tutorial-12-workflow-backed-runtime.md)
