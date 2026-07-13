### 4. Agent Architecture

```mermaid
flowchart LR
    A[Router] --> B[Title Block Agent]
    A --> C[Dimension Agent]
    A --> D[Notes & Symbols Agent]
    B --> E[Standards RAG Agent]
    C --> E
    D --> E
    E --> F[Compliance Judge]