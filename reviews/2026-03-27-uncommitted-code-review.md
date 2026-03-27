## Code Review: Step 18 — Upload Document Page with Graph Visualization

### Summary

Adds a complete document upload flow (drag & drop, async ingestion with polling, Cytoscape.js graph visualization) to the Vue frontend, plus supporting backend endpoints (document listing, full graph, per-document graph). Well-structured with clean separation of concerns, but has a few issues around error silencing, shared state, and code duplication.

**Verdict:** 🟡 Approve with comments

### Files Reviewed

| File | Changes |
|------|---------|
| `services/query-engine/app/api/v1/knowledge_graph.py` | New endpoints: list documents, full graph, document graph |
| `services/query-engine/app/models/knowledge_graph.py` | New `DocumentInfo` model |
| `services/query-engine/app/services/knowledge_graph.py` | `list_documents()`, `get_document_graph()`, `get_full_graph()`, metadata cleanup, case-insensitive subgraph search |
| `services/query-engine/tests/test_knowledge_graph.py` | Tests for full graph endpoint |
| `ui/src/views/UploadView.vue` | Full rewrite — upload, progress, graph, document list |
| `ui/src/services/queryEngine.ts` | API functions for all new endpoints |
| `ui/src/services/api.ts` | FormData Content-Type fix, array params serializer |
| `ui/src/types/queryEngine.ts` | TypeScript interfaces |
| `ui/src/composables/useFileUpload.ts` | Upload + polling lifecycle |
| `ui/src/composables/useDocumentHistory.ts` | Document list state |
| `ui/src/components/graph/KnowledgeGraph.vue` | Cytoscape.js graph component |
| `ui/src/components/upload/FileDropZone.vue` | Drag & drop file input |
| `ui/src/components/upload/IngestionProgress.vue` | Task status display |
| `ui/src/components/upload/DocumentList.vue` | Clickable document list |

**Excluded:** `pnpm-lock.yaml` (lock file), `package.json` (trivial dep addition)

---

### Critical 🔴

> Must fix before merge

_None found._

### Major 🟠

> Should fix before merge

- **MJ-1: `services/query-engine/app/services/knowledge_graph.py:614`** — Access to private internal `_index._index_struct.table` couples the service to LlamaIndex's internal implementation. If LlamaIndex changes the struct layout, this breaks silently (returns empty results, no error).
  - Why: Fragile coupling to framework internals. This already bit you when `include_metadata=False` behaved unexpectedly — internal assumptions about LlamaIndex structures are risky.
  - Fix: Add a guard: `if not hasattr(self._index, '_index_struct') or not hasattr(self._index._index_struct, 'table')` log a warning and return empty. This way a LlamaIndex upgrade surfaces as a warning, not silent empty graphs.
  - > Implementation note from developer: Fix this.

- **MJ-2: `ui/src/composables/useDocumentHistory.ts:9-10`** — `documents` and `isLoading` refs are declared at **module scope** outside the composable function, making them shared singletons across all component instances. If `useDocumentHistory()` is ever called from two components simultaneously, they share the same array and loading state.
  - Why: Works today because only `UploadView` uses it, but will cause subtle bugs if reused. Shared mutable state outside a composable is the Vue equivalent of a global variable.
  - Fix: Move the refs inside the `useDocumentHistory()` function. If you genuinely want singleton state (like a cache), document that intent explicitly with a comment and export as `useDocumentHistoryStore`.
  - > Implementation note from developer: Fix this.

- **MJ-3: `ui/src/views/UploadView.vue:146-157`** — `searchSubgraph()` swallows errors with only `console.error`. If the backend returns 503 (Neo4j down) or 422 (validation error), the user sees "No graph data available" with no indication of the actual failure.
  - Why: Applies to `loadFullGraph()` (line 133-144) and `onSelectDocument()` (line 160-173) too. Users will think the graph is empty when the backend is actually erroring.
  - Fix: Add a `graphError` ref. In catch blocks, set `graphError.value = err instanceof Error ? err.message : 'Failed to load graph'`. Display it in the template where the "No graph data" message is.
  - > Implementation note from developer: Fix this.

- **MJ-4: `services/query-engine/app/services/knowledge_graph.py:282-316`** — The `list_documents()` method calls `get_all_ref_doc_info()` which loads all document metadata into memory. For a large docstore (thousands of documents), this could be slow and memory-intensive.
  - Why: No pagination support. The endpoint returns all documents in one response.
  - Fix: Not urgent for current scale, but add a `limit`/`offset` parameter to the endpoint and method now so the API contract supports pagination from day one. Frontend can paginate later.
  - > Implementation note from developer: Fix this, add infinite scroll on the frontend.

### Minor 🟡

> Fix or acknowledge

- **MN-1: `services/query-engine/app/services/knowledge_graph.py:580-740`** — `get_document_graph()`, `get_full_graph()`, and `get_subgraph()` all share nearly identical record-to-node/edge mapping logic (lines ~540-570, ~634-660, ~710-740). Three copies of the same `for record in records` → `node_map`/`edges` loop.
  - Why: DRY violation. A bug fix to the mapping (e.g., handling missing fields) must be applied in three places.
  - Fix: Extract a private `_records_to_graph(records) -> tuple[list[SubgraphNode], list[SubgraphEdge]]` helper.
  - > Implementation note from developer: Fix this.

- **MN-2: `services/query-engine/tests/test_knowledge_graph.py`** — Tests added for `get_full_graph` but none for `list_documents` or `get_document_graph` endpoints.
  - Why: New endpoints without test coverage.
  - Fix: Add basic tests: `test_list_documents` (mock returns list), `test_document_graph` (mock returns nodes/edges), `test_document_graph_missing_ids` (returns empty).
  - > Implementation note from developer: Fix this.

- **MN-3: `ui/src/services/queryEngine.ts:91`** — JSDoc says `@param docId` (singular) but the actual parameter is `docIds: string[]`. Stale doc from when this was a single-ID endpoint.
  - Why: Misleading documentation.
  - Fix: Update the JSDoc to match: `@param docIds - The document IDs to fetch the graph for (supports multi-chunk docs).`
  - > Implementation note from developer: Fix this.

- **MN-4: `ui/src/components/graph/KnowledgeGraph.vue`** — The `watch` uses `{ deep: true }` on `props.nodes` and `props.edges`. Deep watching arrays of objects is expensive — it recursively compares every property on every node/edge on every reactive update.
  - Why: Performance concern for large graphs. A 500-node graph with deep watch means Vue's reactivity system walks ~1000+ objects per tick.
  - Fix: The parent always replaces the entire array reference (`.value = response.nodes`), so a shallow watch is sufficient. Remove `{ deep: true }`.
  - > Implementation note from developer: Fix this.

- **MN-5: `ui/src/views/UploadView.vue:184-207`** — The `watch(status)` handler has a race condition: `fetchDocuments()` completes, then accesses `documents.value[0]`. But `documents` is a shared module-scope ref (see MJ-2). If another component called `fetchDocuments()` between the await and the access, the array could be stale or different.
  - Why: Tied to MJ-2. The fix for MJ-2 also fixes this.
  - Fix: See MJ-2. Alternatively, have `fetchDocuments()` return the fetched array so the caller uses the fresh value directly.
  - > Implementation note from developer: Ok, so this will be fixed in MJ2 then. Otherwise fix.

### Nitpicks 🔵

> Consider for future

- **NP-1:** `KnowledgeGraph.vue` layout config is duplicated in `initGraph()` and `updateGraph()`. Could be a `const LAYOUT_OPTIONS` at the top.
  - Why: Consistency if you tweak layout params later.
  - Fix: Extract to a constant.
  - > Implementation note from developer: Fix this.

- **NP-2:** `FileDropZone.vue` file extension validation splits on `.` and takes the last segment. A file named `report.2024.txt` works fine, but a file with no extension (just `report`) would produce `undefined` from `.pop()`, and the optional chain `?.toLowerCase()` would make `ext = '.undefined'`.
  - Why: Edge case — unlikely but defensive.
  - Fix: `const parts = file.name.split('.'); const ext = parts.length > 1 ? '.' + parts.pop()!.toLowerCase() : ''`
  - > Implementation note from developer: Fix this.

- **NP-3:** The `getDocumentGraph` JSDoc comment's `@param` still says `docId` singular. The function signature says `docIds: string[]`.
  - Why: Confusing for other developers.
  - Fix: Already covered by MN-3.
  - > Implementation note from developer: Ok.

---

### Highlights ✅

- **Clean composable architecture** — `useFileUpload` encapsulates the entire upload/poll lifecycle neatly, with proper `onUnmounted` cleanup for the poll timer.
- **Vector-first ingestion ordering** — The metadata cleanup approach (whitelist `keep_keys`, strip before LLM extraction) is well-considered after iterating through multiple approaches.
- **Case-insensitive subgraph search** — `toLower()` in Cypher is the right fix. Simple and effective.
- **`paramsSerializer: { indexes: null }`** — Correct fix for FastAPI array params compatibility with axios.
- **Multi-chunk document grouping** — Grouping by `file_name` in `list_documents()` is a good UX decision for PDFs that get split.
- **FormData Content-Type handling** — Detecting `FormData` in the request interceptor and deleting the header is the canonical fix.

### Questions ❓

- Is there an upper bound on how many `doc_ids` can be passed to `GET /documents/graph`? FastAPI will accept unbounded query params, and the Cypher `IN $entities` clause could get very large.
  - Let's bound it to 10 for now.
- Should `list_documents` order be deterministic? Currently it returns dict iteration order from `get_all_ref_doc_info()`, which in Python 3.7+ is insertion order but may not be meaningful to the user.
  - Yes, newest at the top.

---

### Implementation Summary

> Completed after developer notes are processed

| Item | Status | Notes |
|------|--------|-------|
| MJ-1 | ✅ Fixed | Added `getattr` guard with warning log in `get_document_graph` |
| MJ-2 | ✅ Fixed | Moved refs inside `useDocumentHistory()` function |
| MJ-3 | ✅ Fixed | Added `graphError` ref, displayed in template, cleared on each load |
| MJ-4 | ✅ Fixed | Added `limit`/`offset` to backend + `DocumentListResponse` model + "Load more" button in frontend |
| MN-1 | ✅ Fixed | Extracted `_records_to_graph()` static method, used in all 3 graph methods |
| MN-2 | ✅ Fixed | Added `test_list_documents`, `test_list_documents_pagination`, `test_document_graph`, `test_document_graph_missing_doc_ids` |
| MN-3 | ✅ Fixed | Updated JSDoc to `@param docIds` with plural description |
| MN-4 | ✅ Fixed | Removed `{ deep: true }` from watch |
| MN-5 | ✅ Fixed | Fixed by MJ-2 (instance-scoped refs) + `fetchDocuments()` now returns fresh array |
| NP-1 | ✅ Fixed | Extracted `LAYOUT_OPTIONS` constant |
| NP-2 | ✅ Fixed | Added `parts.length > 1` guard for extension-less files |
| NP-3 | ⏭️ Skipped | Covered by MN-3 |
| Q1 | ✅ Fixed | Added `max_length=10` to `doc_ids` query param |
| Q2 | ✅ Fixed | `list_documents` returns reversed (newest-first) order |

**Status key:** ✅ Fixed | ⏭️ Skipped | ⏳ Pending

### Changes Made

- **Backend `knowledge_graph.py`**: Extracted `_records_to_graph()` helper used by `get_subgraph`, `get_document_graph`, and `get_full_graph`. Added `getattr` guard for `_index._index_struct.table`. Added `limit`/`offset` pagination to `list_documents()` with newest-first ordering.
- **Backend `knowledge_graph.py` (API)**: `list_documents` endpoint now returns `DocumentListResponse` with pagination params. `doc_ids` query param bounded to max 10.
- **Backend models**: Added `DocumentListResponse` model.
- **Backend tests**: 4 new tests for `list_documents` (with pagination) and `document_graph` endpoints. All 14 tests pass.
- **Frontend `useDocumentHistory.ts`**: Refs moved inside function (no more shared singletons). Added `loadMore()` for infinite scroll. `fetchDocuments()` returns fresh array.
- **Frontend `UploadView.vue`**: Added `graphError` ref displayed in template. Uses fresh data from `fetchDocuments()` return value. Passes `hasMore`/`isLoading`/`loadMore` to `DocumentList`.
- **Frontend `DocumentList.vue`**: Added "Load more" button with `hasMore` and `isLoading` props.
- **Frontend `KnowledgeGraph.vue`**: Extracted `LAYOUT_OPTIONS` constant. Removed `{ deep: true }` from watch.
- **Frontend `FileDropZone.vue`**: Fixed extension validation for files without extensions.
- **Frontend `queryEngine.ts`**: Updated `listDocuments` for pagination. Fixed JSDoc on `getDocumentGraph`.
- **Frontend types**: Added `DocumentListResponse` interface.
