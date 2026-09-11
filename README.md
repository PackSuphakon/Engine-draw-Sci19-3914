### Agent Architecture

```mermaid
flowchart LR
    A[Router] --> B[Title Block Agent]
    A --> C[Dimension & GD&T Agent]
    A --> D[Notes & View Integrity Agent]
    B --> E[Deterministic Item Assembly]
    C --> E
    D --> E
    E --> F[Compliance Judge]
```

## Milestone Mapping

- [x] **Week 2:** Checklist schema + architecture diagram
- [x] **Week 3:** `/review` endpoint with real LLM calls
- [x] **Week 4–5:** Standards RAG ingestion (instructor 20-item checklist)
- [x] **Week 6–7 (partial):** Specialist agents grounded in real drawing text descriptions from the instructor gold set (image/multimodal input not yet wired in)
- [x] **Week 8:** Judge + eval against instructor gold set subset
- [ ] **Week 9–12:** UI with annotated findings overlay

## Release Notes — v0.2.0 "AI core" (Iteration 2)

**Goal:** End-to-end offline pipeline that uses the instructor data pack. ✅ met, with one caveat noted below.

### Agents
- **Router Agent** — classifies the drawing and gives specialist focus instructions. Structured output via `RouterDecision` (Pydantic).
- **Title Block Specialist** — evaluates `GENERAL_METADATA` checklist items (G01–G04).
- **Dimension & GD&T Specialist** — evaluates `DIMENSIONING_RULES` + `GDT_AND_TOLERANCING` items (D01–D05, T01–T05).
- **Notes & View Integrity Specialist** — evaluates `VIEW_INTEGRITY` + `MANUFACTURABILITY` items (V01–V04, M01–M02).
  Each specialist returns structured `SpecialistFindings` (Pydantic) — only `status` + `evidence` come from the LLM; `description` and `standard_ref` are filled deterministically from the knowledge base afterward, so the model can't hallucinate a standard reference.
- **Compliance Judge (LLM-as-judge)** — receives the already-assembled, deterministic item list and only decides `overall_status` + `open_questions`. It cannot alter or invent items, which keeps the grounding check honest.

### RAG Sources
- `knowledge_base.json` — instructor checklist `SOT-ENG-DRW-020`, 20 items across 5 categories (GENERAL_METADATA, VIEW_INTEGRITY, DIMENSIONING_RULES, GDT_AND_TOLERANCING, MANUFACTURABILITY), each tagged with its ASME/ISO standard reference.
- `standards_excerpt.md` — redacted ASME Y14.5 / ISO 128 / ISO 129-1 excerpt pack from the instructor bundle, kept as background reference context.
- `gold_set.json` — the 12-drawing instructor gold set (6 compliant / 6 with known issues) with per-drawing text descriptions and ground-truth failed item IDs. Used by `eval_script.py`.

### Eval
`eval_script.py` runs a 6-drawing subset (within the 5–10 range) of the 12-drawing gold set against the live `/review` endpoint and reports two metrics in `eval_report.md`:
- Overall status accuracy (pass/fail/review_required vs. gold)
- Exact failed-item-set accuracy (does the predicted set of failed item IDs match gold exactly)

### Known caveat
Drawing "content" is currently the instructor's **text description** of each drawing's issues (or lack thereof), not the drawing image itself — there is no multimodal/vision ingestion yet. This satisfies the Iteration 2 bar ("polished UI, full security audit, prompt versioning" explicitly not required yet) but means the pipeline is not yet reading actual drawing geometry. Wiring in the drawing images (e.g. via Gemini vision, or the Roboflow object-detection set for visual reference) is the natural next step before the Week 9–12 milestone.

## System Architecture & Design Highlights

### 1. Data Validation & Schemas
ระบบใช้ **Pydantic** ในการจัดการและตรวจสอบ (Validate) โครงสร้างข้อมูลอย่างเข้มงวดทุกจุดที่มีการเรียก LLM (Router / Specialists / Judge) ป้องกันระบบพังจากการตอบกลับที่ผิดรูปแบบ

### 2. Traceability & Debugging
- `standard_ref` มาจาก knowledge base โดยตรง ไม่ได้ให้ LLM สร้างเอง จึงรับประกันว่าอ้างอิงมาตรฐานถูกต้องเสมอ
- `evidence` มาจากคำอธิบายแบบแปลนจริงที่ LLM อ้างอิง ทำให้ trace ย้อนกลับได้ว่าทำไมถึงตัดสิน fail/pass

### 3. Scalability & Maintainability
- Checklist ถูกเก็บใน `knowledge_base.json` แยกจากโค้ดทั้งหมด อัปเดตมาตรฐานใหม่ทำได้โดยไม่ต้องแก้โค้ด
- เพิ่ม specialist ตัวใหม่ทำได้ง่ายด้วยการเพิ่ม entry ใน `SPECIALIST_CATEGORIES` และเรียก `specialist_agent()` แบบเดิม
