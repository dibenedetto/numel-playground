This tutorial shows how to make a deployment act on events instead of only on a timer.

The key idea is:

- a proactive deployment does not need to wake up every N seconds
- it can also wake up when a real event arrives

That is now part of Numel’s workflow-backed deployment model.

## What You Will Learn

- how to think about event-driven proactive tasks
- how to configure a webhook-triggered proactive deployment
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

Examples of event-driven triggers now include:

- `webhook`
- `channel`
- `fswatch`
- `browser`

So a proactive assistant can now behave more like:

- “wake up when an incident webhook arrives”

instead of only:

- “wake up every 15 minutes”

## Part 1: Start From The Example Config

Numel now includes an event-driven deployment example here:

- [assistant-deployment-webhook-proactive.json](../examples/assistant-deployment-webhook-proactive.json)

Read it as an operator-facing reference, not as a workflow file.

The important parts are:

- `trigger_kind: "webhook"`
- `interval_sec: 0`
- `trigger.endpoint`
- `trigger.methods`
- delivery `channel_id`
- delivery `recipient_id`

That tells Numel:

- this task is not timer-driven
- it should wake up from a webhook event
- when it responds, it should deliver through the configured channel and recipient

## Part 2: Create The Deployment

Open **Assistant Deployments** and create a deployment with values like:

- **Name**: `Webhook Incident Triage`
- **Profile**: `ops`
- **Instructions**: summarize webhook incidents and surface next actions
- **Channels**: choose the delivery channel
- **Proactive Delivery**: `Require approval before sending`
- **Tool Execution**: `Require approval before each tool call`

Then add a proactive task with:

- **Name**: `Inbound Incident Webhook`
- **Trigger**: `Webhook`
- **Endpoint**: `/hook/incidents`
- **Methods**: `POST`
- **Prompt**: summarize the incident payload and propose the next operator action
- **Send response**: enabled

Important detail:

- leave the timer interval at `0` for this kind of task

because the task is event-driven, not schedule-driven.

## Part 3: Send A Test Event

Once the deployment is active, send a test webhook request.

Example:

```bash
curl -X POST http://localhost:11360/hook/incidents \
  -H "Content-Type: application/json" \
  -d "{\"severity\":\"high\",\"service\":\"billing-api\",\"message\":\"Refund processing backlog exceeded threshold\"}"
```

If you configured a webhook secret in the trigger, include the matching header or auth mechanism used by your setup.

What should happen:

1. the event wakes the proactive task
2. the deployment processes the payload
3. if proactive delivery approval is enabled, the outgoing response pauses for approval
4. after approval, the response is delivered to the configured channel/recipient

## Part 4: Operate It From The Panel

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

## Part 5: See The Workflow-Backed Trigger Shape

Open the live network in the workbench:

1. open **Assistant Deployments**
2. click **Open Live Network In Workbench**

Around the proactive task, you should now see a trigger-driven subgraph rather than hidden timer metadata.

For a webhook-driven task, the shape is conceptually:

- `webhook_source_flow`
- `event_listener_flow`
- proactive runtime node

That matters because the trigger is now represented through the same workflow language as the rest of Numel.

## Suggested Variations

After the webhook version works, try one of these:

- switch the trigger to `channel` so the deployment reacts to incoming channel events
- switch the trigger to `fswatch` so it reacts to file-system changes
- keep the same deployment but add both a timer-driven task and an event-driven task

This is a good way to build intuition for when the assistant should:

- poll on a schedule
- versus wake only when something real happens

## What You Built

At the end of this tutorial, you have:

- a deployment with an event-driven proactive task
- a real webhook-triggered operator flow
- approval support for outgoing proactive delivery
- an inspectable workflow-backed trigger shape

That is the important shift:

- proactive assistants in Numel are no longer only scheduled helpers
- they can now behave like event-driven runtime services

## Where To Go Next

- [assistant-deployments.md](assistant-deployments.md)
- [assistant-deployment-operations.md](assistant-deployment-operations.md)
- [tutorial-12-workflow-backed-runtime.md](tutorial-12-workflow-backed-runtime.md)
