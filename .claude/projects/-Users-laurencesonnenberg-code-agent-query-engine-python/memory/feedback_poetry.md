---
name: feedback_poetry
description: Use bare `poetry` command, not `python3 -m poetry`
type: feedback
---

Now that poetry is installed, use `poetry` directly (e.g. `poetry run pytest`), not `python3 -m poetry`.

**Why:** It's installed and on PATH after the pip3 install. No need for the module invocation.

**How to apply:** Always use `poetry` as the command prefix.