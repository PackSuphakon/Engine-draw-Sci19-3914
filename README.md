### Agent Architecture

```mermaid
flowchart LR
    A[Router] --> B[Title Block Agent]
    A --> C[Dimension Agent]
    A --> D[Notes & Symbols Agent]
    B --> E[Standards RAG Agent]
    C --> E
    D --> E
    E --> F[Compliance Judge]

```
   ## Milestone Mapping

- [x] **Week 2:** Checklist schema + architecture diagram
- [x] **Week 3:** `/review` stub with mock responses
- [ ] **Week 4–5:** Standards RAG ingestion
- [ ] **Week 6–7:** Specialist agents + multimodal pipeline
- [ ] **Week 8:** Judge + gold-set evaluation
- [ ] **Week 9–12:** UI with annotated findings overlay