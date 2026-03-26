---
name: project_roadmap
description: 16-step build roadmap for the agent query engine — LlamaIndex KG service with Neo4j, called via HTTPS from a Kotlin LangGraph4j agent
type: project
---

Building a LlamaIndex-based Knowledge Graph query engine as a Python/FastAPI microservice. The Kotlin agent (LangGraph4j + LangChain4j) calls this service over HTTPS. Neo4j is the graph store. Deployed on GKE with Traefik + cert-manager.

**Why:** The Kotlin agent needs access to large amounts of data via a knowledge graph. LlamaIndex excels at KG indexing and multi-document synthesis. Deployed as a separate service.

**How to apply:** All 16 roadmap items build toward this architecture.

## Roadmap Status (as of 2026-03-25)
1. ~~Structured Logging with structlog~~ — DONE
2. ~~Request/Response Middleware~~ — DONE
3. ~~Error Handling Framework~~ — DONE
4. ~~LlamaIndex Core Integration~~ — DONE
5. ~~Neo4j Graph Store~~ — DONE
6. ~~Dependency Injection~~ — DONE
7. ~~Document Connectors & Ingestion Pipeline~~ — DONE
8. Background Task Processing — pending
9. Hybrid Retrieval (KG + Vector) + Index Persistence — pending
10. Authentication & API Key Management — pending
11. Rate Limiting — pending
12. Caching Layer — pending
13. Observability — Metrics & Tracing — pending
14. Multi-Index Support — pending
15. Kubernetes Readiness & Deployment — pending