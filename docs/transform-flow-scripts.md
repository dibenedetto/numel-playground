# Writing Python in `transform_flow` scripts

A reference for anyone authoring inline Python in workflow `transform_flow` nodes. Read this **before** putting non-trivial logic into a script — there's a Python `exec` quirk that breaks function-to-function references in ways that are easy to miss in unit tests.

---

## TL;DR

Inside a `transform_flow` script you can use:

* top-level statements, expressions, and variables freely
* `import` statements (top-level imports are visible only to top-level code, **not** to functions defined in the script)
* simple top-level **function calls**

You **cannot** rely on a function defined in the script to reference any other name from the same script — including:

* recursing on its own name
* calling another helper defined above
* reading a top-level constant or imported module

If your transform is more than ~30 lines, **move the logic into a real Python module under `app/`** and call it from a thin shim. That's what the Phase 3 substrate workflows do (`proactive.middleware`, `proactive.governor`, `proactive.persistence`, `proactive.quarantine`).

---

## Why this happens

The engine runs every `transform_flow` script via:

```python
# app/nodes.py:295
exec(script, None, local_vars)
```

This is Python's two-namespace `exec` form. The semantics:

* `globals` is `None`, so Python uses the calling frame's globals — which is `app/nodes.py`'s module-level dict.
* `locals` is `local_vars`, the dict containing `input`, `variables`, `context`, `output`.
* The script runs at "module top level" with `local_vars` as the local namespace.

The result:

| Where the name lives                              | Visible to top-level code | Visible inside a script-defined function |
| :------------------------------------------------ | :-----------------------: | :--------------------------------------: |
| Top-level `def`, `name = ...`, `import name`      | ✅                        | ❌                                       |
| `nodes.py` module globals                         | ✅                        | ✅                                       |
| Python builtins (`len`, `dict`, `isinstance`, …)  | ✅                        | ✅                                       |
| Function parameters / locals                      | n/a                       | ✅                                       |
| Closure cells from an enclosing nested `def`      | n/a                       | ✅                                       |

The standard LEGB lookup applies. The catch is that **L for a function defined in the script is its own locals** (not the script's `local_vars`), and **G for that function is `nodes.py` module globals** (not `local_vars`). So when an inside-function lookup falls through to G, it never finds names you defined in the script.

---

## What doesn't work

```python
# ❌ Top-level constant referenced from inside a function
import re
PATTERN = re.compile(r"\d+")

def f(s):
    return PATTERN.findall(s)        # NameError: PATTERN

result = f("abc123")
```

```python
# ❌ Helper-to-helper call
def lower(s):
    return s.lower()

def first_token(s):
    return lower(s).split()[0]       # NameError: lower

result = first_token("Hello World")
```

```python
# ❌ Direct recursion
def fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)           # NameError: fact

result = fact(5)
```

```python
# ❌ Generator-expression body referencing a top-level name
SCOPES = {"write", "external-network"}
target = ["read-only", "write"]

result = any(s in SCOPES for s in target)   # NameError: SCOPES
                                            # (genexp body has the same scope rules
                                            #  as a nested function)
```

---

## What works

### 1. Top-level statements only

```python
import re
PATTERN = re.compile(r"\d+")
output = PATTERN.findall(input)
```

If everything is at the top level, lookups go to `local_vars` and succeed.

### 2. Self-contained function (parameters + builtins only)

```python
def caps_only(text):
    return "".join(c for c in text if c.isupper())

output = caps_only(input)
```

`text` is a parameter, `c` is the loop variable, `.isupper()` is a method call. No outer-scope name lookups. Genexp inside is OK because `c` is its own loop variable.

### 3. Capture dependencies via default arguments

Default arguments are evaluated **eagerly** at `def` time, in the script's top-level scope. They become the function's defaults — i.e. parameters — so inside the function they're locals, not lookups.

```python
import re
PATTERN = re.compile(r"\d+")

def find_digits(text, _pat=PATTERN, _re=re):
    return _pat.findall(text)         # _pat and _re are parameters

output = find_digits(input)
```

This is the workhorse pattern when you must define a function that needs script-level state. It is also the cleanest way to make a script-defined function recursive — pass the function to itself:

```python
def fact(n, _self):
    if n <= 1:
        return 1
    return n * _self(n - 1, _self)

output = fact(5, fact)               # top-level call site sees `fact`
```

### 4. `import` inside the function

The import statement binds the name into the function's locals at call time:

```python
def is_email(text):
    import re
    return bool(re.fullmatch(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))

output = is_email(input)
```

A bit slower than a top-level import (one fresh `import` per call), but always correct.

### 5. Closures (nested `def`)

Enclosing-scope lookup uses the closure cell mechanism, not `__globals__`. So a nested `def` can see names from its enclosing `def`:

```python
def make_walker():
    import re
    PATTERN = re.compile(r"\d+")
    def walk(text):
        return PATTERN.findall(text)   # enclosing scope, via closure
    return walk

walk   = make_walker()
output = walk(input)
```

Heavier than necessary for simple cases, but works for arbitrarily complex helpers.

### 6. Iterative loops + explicit stack (instead of recursion)

When the natural shape is recursive — walking a tree, deep-redacting nested data — keep all of it at the top level using an explicit stack. This is what the Phase 1/2 Privacy gates do after the M3-fix:

```python
import re
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

env      = dict(input) if isinstance(input, dict) else {"raw": input}
_targets = [(env, k) for k in ("payload", "body", "message") if k in env]

while _targets:
    parent, key = _targets.pop()
    val = parent[key]
    if isinstance(val, str):
        parent[key] = EMAIL.sub("[email]", val)
    elif isinstance(val, dict):
        for k in list(val.keys()):
            _targets.append((val, k))
    elif isinstance(val, list):
        for i in range(len(val)):
            _targets.append((val, i))

output = env
```

No nested `def`, so nothing has the wrong globals. The `EMAIL.sub(…)` call is at top level — `EMAIL` is in `local_vars` and looked up correctly.

---

## The recommended pattern: move logic into a real module

For anything more than a few lines, the cleanest fix is to write a normal Python module under `app/` and import it from a thin shim in the transform script. Modules don't have the `exec` problem — recursion, helpers, and constants all behave normally — and the logic becomes testable in isolation.

```python
# In examples/your-workflow.json — the transform script
try:
    from your_module import do_thing
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.join(os.getcwd(), 'app'))
    from your_module import do_thing

env    = dict(input) if isinstance(input, dict) else {"raw": input}
output = do_thing(env)
```

```python
# In app/your_module.py — a normal Python module
def do_thing(env):
    return _walk(env)            # recursion works, helpers work

def _walk(value):
    if isinstance(value, dict):
        return {k: _walk(v) for k, v in value.items()}
    return _redact(value)

def _redact(value):
    ...
```

The `try/except ImportError` block makes the script work both inside the engine (where `app/` is on `sys.path`) and from ad-hoc smoke tests run from the repo root.

Reference implementations in this repo:

| Module                        | Used by                                   |
| :---------------------------- | :---------------------------------------- |
| `app/proactive/middleware.py` | `proactive-substrate-persistent.json` — Veracity / Privacy / Adversarial gates |
| `app/proactive/persistence.py`| same — durable JSON / JSONL state         |
| `app/proactive/quarantine.py` | same — quarantine + snapshots             |

---

## Diagnosing a script that "should work"

Symptoms of this class of bug:

* `NameError: name 'X' is not defined` from a function or comprehension body, where `X` is something you defined or imported at the top of the same script.
* Works in a quick smoke test using `exec(script, ns)` (single argument), fails in the actual engine.

The single-argument form, `exec(code, globals_dict)`, uses the same dict as both globals and locals — so script-defined names *do* end up in the function's `__globals__` and lookups succeed. Smoke tests must use the engine-matching form to catch the bug:

```python
ns = {"input": ..., "variables": ..., "context": None, "output": None}
exec(node.script, None, ns)          # split namespaces — matches the engine
```

Once you switch to that form, the smoke test fails the same way the engine does, and you know whether your script is portable.
