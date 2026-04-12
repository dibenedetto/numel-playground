Turn a Numel workbench into a real channel-facing AI service by combining it with an Assistant Deployment.

## What You Will Learn

- how to create a linked workbench for a deployment
- how to bind a deployment to a real channel
- how to add routing rules to specialist deployments
- how to add proactive jobs
- how to use proactive-delivery approval and tool-execution approval
- how to operate the deployment from the Assistant Deployments panel

## Prerequisites

- Numel running locally
- at least one channel available, for example a webhook channel
- a model available through your configured backend

## The Idea

An assistant deployment is not itself a workflow node. It is a persistent runtime object that sits on top of spaces, workflows, channels, tools, and skills.

The easiest mental model is:

- **space/workflow** = design surface
- **assistant deployment** = runtime product object
- **channel** = where users interact with it

This is different from plain user memory:

- **user memory** makes an assistant remember a person over time
- **assistant deployment** makes that AI behavior become a stable, named, channel-facing service

In practice:

- memory says: `this assistant remembers Marco`
- deployment says: `this is Support Front Door, it runs on these channels, uses these tools, and follows these approval rules`

If you are less technical, this is the important part:

- you do not need to redesign the workflow graph every time
- you can start from an existing workbench
- then operate the named deployment from one panel
- and only go back into the workbench when you want to improve it

## Part 1: Load The Linked Workbench

1. Create or select a space.
2. Import [tutorial-11-assistant-deployments.json](tutorial-11-assistant-deployments.json).
3. Save the space.

This gives you a support-oriented workbench with:

- an agent
- a shared knowledge manager
- file access
- a simple request/response flow you can use while iterating on the assistant

You can also load one of the gallery items instead:

- `Assistant Deployments: Support Workbench`
- `Assistant Deployments: Ops Workbench`

## Part 2: Create A Channel

Create a channel first, for example:

- a webhook channel for testing
- or a real external channel such as Telegram, Discord, Slack, or Email

## Part 3: Create The Deployment

Open **Assistant Deployments** from the Channels area and click **Add Deployment**.

Recommended starter values:

- **Name**: `Support Front Door`
- **Profile**: `triage`
- **Use Current Workbench**: click the helper button
- **Toolkits**: `channel_toolkit,knowledge_toolkit`
- **Channels**: select your test channel
- **Tool Execution**: `Require approval before each tool call`

That last setting is important when you want an operator to stay in the loop before the deployment runs tools in a live channel.

## Part 4: Add A Specialist

Create a second deployment, for example:

- **Name**: `Billing Specialist`
- **Profile**: `billing`
- **Instructions**: `Handle invoice, refund, and payment issues.`

Then edit `Support Front Door` and add a routing rule such as:

```text
billing,invoice,refund,chargeback => deploy_xxxxxxxx
```

Use the actual target deployment id shown in the panel.

## Part 5: Add A Proactive Job

For an ops-style deployment, add a proactive task like:

- **Name**: `Morning Summary`
- **Prompt**: `Summarize the most important operational events and highlight risks.`
- **Interval**: `900`
- **Send response**: enabled

Then choose one of these safety modes:

- **Send automatically**
- **Require approval before sending**

This governs the outgoing proactive message itself, separately from tool execution approval.

## Part 6: Operate It

Once the deployment is running, the panel gives you:

- status
- pending approvals
- recent activity
- recent failures
- linked workbench jump-back
- manual `Run Tasks`
- `Refresh State`

If tool execution approval is enabled, a live message can now pause before the assistant runs a tool. The operator can then:

- approve the tool call and let the run continue
- reject the tool call and let the run continue with that rejection applied

## Example Configs

Two API-oriented example deployment configs are included here:

- [assistant-deployment-front-door.json](../examples/assistant-deployment-front-door.json)
- [assistant-deployment-ops-proactive.json](../examples/assistant-deployment-ops-proactive.json)

They are not workflow files. They are deployment configuration examples you can adapt when creating deployments through the API or as operator references.

## Suggested Experiments

- keep the same linked workbench, but create two deployments with different models
- create a front-door deployment plus two specialists
- enable tool approval for the front door, but not for the specialist
- enable proactive delivery approval for an ops deployment and compare the operator flow

## What You Built

At the end of this tutorial, you have:

- a linked workbench in a Numel space
- a persistent assistant deployment
- a real channel binding
- optional routing to specialists
- optional proactive jobs
- operator-visible approvals and runtime supervision

That is the foundation of Numel’s assistant-deployment model: workflows remain the place where you build the intelligence, while deployments are the place where you run it for real users.
