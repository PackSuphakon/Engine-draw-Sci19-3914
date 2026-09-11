from pydantic import BaseModel, Field
from typing import Literal


class ChecklistItem(BaseModel):
    item_id: str
    description: str
    status: Literal["pass", "fail", "na", "unclear"]
    evidence: str
    standard_ref: str | None


class DrawingReviewReport(BaseModel):
    drawing_id: str
    overall_status: Literal["pass", "fail", "review_required"]
    items: list[ChecklistItem]
    open_questions: list[str]


class DrawingUploadRequest(BaseModel):
    drawing_id: str
    drawing_type: Literal["manufacturing", "structural", "piping", "other"] = "manufacturing"
    # Text description of the drawing content (from the instructor bundle / gold set).
    # This is what grounds the specialist agents instead of letting them guess from the ID alone.
    description: str = ""


class RouterDecision(BaseModel):
    category: str = Field(description="หมวดหมู่ของแบบแปลน เช่น เครื่องกล (Mechanical), โครงสร้าง (Structural)")
    complexity: str = Field(description="ระดับความซับซ้อน เช่น High, Medium, Low")
    specialist_instructions: str = Field(description="คำแนะนำหรือจุดที่ Specialist ต้องโฟกัสเป็นพิเศษ")


class SpecialistFinding(BaseModel):
    """One checklist item verdict from a specialist agent.
    Only status + evidence come from the LLM — item_id must match a real
    checklist id given in the prompt. description/standard_ref are filled
    deterministically from knowledge_base.json afterwards, so the model
    can't hallucinate the standard reference."""
    item_id: str
    status: Literal["pass", "fail", "na", "unclear"]
    # No default here on purpose: Gemini's response_schema converter rejects
    # any JSON-schema "default" keyword outright (500 error before the model
    # is even called). The omitted-evidence guard lives in assemble_items()
    # instead, as a post-processing fallback on the raw parsed value.
    evidence: str


class SpecialistFindings(BaseModel):
    findings: list[SpecialistFinding]


class JudgeDecision(BaseModel):
    """LLM-as-judge grounding check: only decides the overall verdict and
    open questions from the already-assembled (deterministic) item list —
    it does not re-generate item content, so it can't drop or invent items."""
    overall_status: Literal["pass", "fail", "review_required"]
    open_questions: list[str]
    reasoning: str = Field(description="เหตุผลสั้นๆ ที่ตัดสินผลนี้ อ้างอิง item ที่ fail ถ้ามี")
