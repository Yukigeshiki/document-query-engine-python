---
name: project_roadmap
description: 16-step build roadmap for the agent query engine — LlamaIndex KG service with Neo4j, called via HTTPS from a Kotlin LangGraph4j agent
type: project
---

Building a LlamaIndex-based Knowledge Graph query engine as a Python/FastAPI microservice. The Kotlin agent (LangGraph4j + LangChain4j) calls this service over HTTPS (not gRPC). Neo4j is the graph store. Deployed on GKE with Traefik + cert-manager.

**Why:** The Kotlin agent needs access to large amounts of data via a knowledge graph. LlamaIndex excels at KG indexing and multi-document synthesis. Python sidecar is justified by the KG complexity.

**How to apply:** All 16 roadmap items build toward this architecture. Item #1 (structured logging) is complete. Next up is #2 (request/response middleware).

## Roadmap Status (as of 2026-03-24)
1. ~~Structured Logging with structlog~~ — DONE
2. Request/Response Middleware — pending
3. Error Handling Framework — pending
4. LlamaIndex Core Integration — pending
5. Neo4j Graph Store — pending
6. Dependency Injection — pending
7. Document Connectors & Ingestion Pipeline — pending
8. Background Task Processing — pending
9. Hybrid Retrieval (KG + Vector) — pending
10. Authentication & API Key Management — pending
11. Rate Limiting — pending
12. Caching Layer — pending
13. Observability — Metrics & Tracing — pending
14. Multi-Index Support — pending
15. Kubernetes Readiness & Deployment — pending