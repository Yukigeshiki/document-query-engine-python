---
name: feedback_docstrings
description: Multi-line docstring formatting — first line must be on its own line after the opening quotes
type: feedback
---

For multi-line docstrings, the summary should NOT start on the same line as the opening triple quotes. Put it on the next line.

**Why:** User preference for readability and consistency.

**How to apply:**
```python
# Wrong
"""Ingest documents from an external source into the knowledge graph.

This is an admin endpoint for bulk data loading.
"""

# Correct
"""
Ingest documents from an external source into the knowledge graph.

This is an admin endpoint for bulk data loading.
"""
```

Single-line docstrings stay on one line: `"""Return the thing."""`