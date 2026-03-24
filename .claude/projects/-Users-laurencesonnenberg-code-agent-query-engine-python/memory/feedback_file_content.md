---
name: feedback_file_content
description: Keep project files focused — don't duplicate info that's already tracked elsewhere, and omit deployment details during local dev phase
type: feedback
---

Don't put the roadmap in AGENT.md — it's tracked in memory and by the user separately. AGENT.md should stay focused on conventions, commands, and structure.

**Why:** User doesn't want duplication across files. Roadmap is living context, not a static guideline.

**How to apply:** AGENT.md = how to work in the codebase. Memory = project state and plans. Don't mix them. Also, skip deployment/infra details (GKE, Helm, Traefik) in project files while we're in local development phase.