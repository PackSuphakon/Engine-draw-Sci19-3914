from pydantic import BaseModel
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