# Tutorial 4: Loops and Iteration

Repeat operations using while loops and iterate over lists with for-each.

## What You Will Learn

- While loops with Loop Start/End
- For-each iteration over lists
- Loop-back edges (`"loop": true`)
- The `iteration`, `current`, and `index` outputs
- Using Delay to slow down loops for observation

## Part A: While Loop

```
Start ──> Loop Start (5x) ──> Transform ──> Preview ──> Delay (500ms) ──> Loop End ──┐
               ^                                                                      │
               └──────────────────── loop edge ───────────────────────────────────────┘
              (then) ──> End
```

The Loop Start node repeats its body up to `max_iter` times. On each iteration:

1. `iteration` output gives the current count (0, 1, 2, ...)
2. The Transform formats a message: `"Tick #0"`, `"Tick #1"`, etc.
3. The Preview displays the message
4. The Delay pauses 500ms so you can watch each tick
5. Loop End signals to repeat

After 5 iterations, execution continues to End.

### Loop-Back Edges

The edge from Loop End back to Loop Start must include `"loop": true`. This tells the engine it's a backward reference for looping, not a forward dependency.

## Part B: For-Each

```
Start ──> ForEach Start ──> Transform ──> Preview ──> ForEach End ──┐
               ^            (formats)                                │
               └──────────── loop edge ─────────────────────────────┘
              (then) ──> End
```

The ForEach Start node takes an `items` list and iterates over each element:

- `current` output is the current item (`"alpha"`, `"beta"`, `"gamma"`)
- `index` output is the position (0, 1, 2)

The Transform formats each item: `"Item 0: ALPHA"`, `"Item 1: BETA"`, etc.

## Steps

1. **Import** `tutorial-04-loops.json`.
2. Click **Start**. Watch the while loop section execute 5 times with 500ms delays.
3. After the while loop completes, the for-each section iterates over three items.
4. Check the Preview nodes — they update on each iteration.

## Experimenting

- **Change iteration count**: Edit `max_iter` on the Loop Start node.
- **Change items**: Edit the `items` field on the ForEach Start node.
- **Add Break/Continue**: Insert a Break node in the loop body to exit early, or Continue to skip an iteration.

## What's Next

In [Tutorial 5](tutorial-05-events.md), you'll use timer sources and event listeners for reactive workflows.
