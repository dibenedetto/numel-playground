# Numel Playground, For Humans

If the main `README.md` feels like a system inventory, this document is the friendlier version.

Numel is a place where you can design, run, and operate AI-powered workflows without having to assemble a product from scratch. You can use it to automate recurring work, build assistants that use tools and knowledge, and turn a workflow into something other people can actually use.

## What Numel Is

The shortest useful description is:

**Numel is an AI workflow workbench.**

It gives you:

- a visual canvas for building workflows
- an assistant that can help generate or refine those workflows
- tools, skills, and knowledge that can be attached to agents
- spaces so your work stays organized
- ways to run the result as an internal workflow, a channel-facing assistant, or a published app

It is not only a chatbot builder, and it is not only an automation tool. It sits in the middle:

- more product-shaped than a coding framework
- more AI-native than a generic automation platform
- more visual and operational than a plain agent SDK

## Who It Is For

Numel is useful for:

- people who want to automate a recurring process
- teams building internal AI tools
- technically curious users who want a visual way to work
- developers who want a workbench instead of a blank codebase
- operators who need to supervise something real after it is built

You do not need to understand every node type on day one. A good way to start is:

- load a tutorial or gallery workflow
- run it
- change one thing
- run it again

That is enough to start building intuition.

## What You Can Do With It

Here are the most practical use cases:

### 1. Build AI workflows

Example:

- take a user input
- transform it
- send it to an agent
- score the result
- branch or retry based on the score

### 2. Create assistants that use tools and knowledge

Example:

- an assistant that searches local documents
- an assistant that reads files or emails
- an assistant that uses a toolkit for a specific domain, like meshes or images

### 3. Set up persistent knowledge

Example:

- watch a folder or inbox
- analyze what is relevant
- ingest it into a shared knowledge base
- query that knowledge later from another workflow or assistant

### 4. Run real operational assistants

Example:

- a support front door assistant
- a specialist billing assistant
- a proactive operations assistant that sends summaries on a schedule

This is where **Assistant Deployments** matter: they turn something you designed in the workbench into a real named assistant that can run on channels, use approvals, and be supervised.

### 5. Publish a workflow as a web app

Example:

- take a workflow
- generate a page around it
- publish it for other people to use

This is useful when the workflow should feel like a product, not just a graph in your editor.

## The Main Ideas To Learn First

If you understand these ideas, the rest of Numel gets much easier.

### Space

A **space** is your working area. Think of it as the container for the current thing you are building.

### Current Workflow

Each space has one current workflow. That workflow is the thing you edit on the canvas and run.

### Nodes

Nodes are the building blocks of a workflow. Some handle control flow, some transform data, some configure agents, some connect to events, tools, or knowledge.

### Assistant

The assistant helps you think, generate, inspect, and refine workflows. It is useful, but it is only one part of Numel.

### Assistant Deployment

An **assistant deployment** is a named, persistent AI service built from work you prepared in Numel.

It answers questions like:

- which channels this assistant runs on
- which skills and toolkits it uses
- whether it needs approval before doing something risky
- whether it should run proactive jobs
- which workbench it belongs to

### Published App

A **published app** is a user-facing page generated from a workflow. It lets other people use the workflow without opening the workbench.

## A Good First 15 Minutes

1. Start Numel and open the web UI.
2. Create a new space.
3. Open the Gallery and load a simple starter.
4. Press `Run`.
5. Look at what changed in the canvas and in the Run panel.
6. Change one node value and run again.
7. Open the assistant and ask it to explain the workflow in plain language.

If you do only that, you will already understand the core loop:

**load -> inspect -> change -> run -> learn**

## Common Paths

### If you want to automate a recurring task

Start with:

- [docs/tutorial-01-hello-workflow.md](docs/tutorial-01-hello-workflow.md)
- [docs/tutorial-02-transform.md](docs/tutorial-02-transform.md)
- [docs/tutorial-03-routing.md](docs/tutorial-03-routing.md)
- [docs/tutorial-05-events.md](docs/tutorial-05-events.md)

### If you want to build an agent that can use tools or files

Start with:

- [docs/tutorial-06-agent.md](docs/tutorial-06-agent.md)
- [docs/tutorial-09-file-tools.md](docs/tutorial-09-file-tools.md)
- [docs/tutorial-10-skills.md](docs/tutorial-10-skills.md)

### If you want a channel-facing assistant that keeps running

Start with:

- [docs/assistant-deployments.md](docs/assistant-deployments.md)
- [docs/tutorial-11-assistant-deployments.md](docs/tutorial-11-assistant-deployments.md)

If you are thinking about how multiple deployments and remote agents could work together later, also see:

- [docs/assistant-network-architecture.md](docs/assistant-network-architecture.md)

### If you want a shared knowledge base you can query later

A good mental model is:

- one workflow ingests useful information
- another workflow or assistant queries it later

You can build this with knowledge-related nodes and the knowledge toolkit, plus a source such as files, events, or email.

### If you want to publish something people can use

Look at the Published Apps panel after you have a workflow that already works well. Publishing makes more sense after the workflow itself is solid.

## What You Can Ignore At First

You do not need to understand all of this immediately:

- every node category
- the planner
- production deployment details
- quotas and admin features
- channel integrations
- low-level backend choices

Those are real parts of the system, but they are not required for a good first experience.

## If You Are Non-Technical

You can still get value from Numel if someone has already prepared workbenches, assistants, or published apps for you.

You may mostly use Numel to:

- run an existing workflow
- operate an assistant deployment
- approve or reject actions
- inspect results
- use a published app

You do not have to become a workflow author to benefit from the platform.

## If You Are Technical

Numel becomes a serious platform when you want to combine:

- workflow orchestration
- agents
- tools and toolkits
- skills
- shared knowledge
- channel integrations
- approvals and operator controls
- publishable interfaces

That is where it starts to feel less like a demo canvas and more like an AI system workbench.

## A Simple Mental Model

One useful way to think about Numel is:

- **Workflow** = the logic
- **Assistant** = the collaborator
- **Knowledge** = the shared memory of documents and facts
- **Assistant Deployment** = the running service
- **Published App** = the user-facing product surface

## Where To Go Next

- For the technical reference and feature inventory, see [README.md](README.md)
- For a general introduction, see [docs/introduction.md](docs/introduction.md)
- For the product direction, see [docs/product-roadmap.md](docs/product-roadmap.md)
- For assistant operations, see [docs/assistant-deployments.md](docs/assistant-deployments.md)
- For a positioning comparison with other tools, see [docs/competitive-landscape.md](docs/competitive-landscape.md)

If you only remember one thing, make it this:

**Numel helps you move from "I have an AI idea" to "I have something real I can run, supervise, and share."**
