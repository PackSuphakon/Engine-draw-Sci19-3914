from fastapi import FastAPI
from schemas import ChecklistItem, DrawingReviewReport

# สร้างแอป FastAPI
app = FastAPI(title="Engineering Drawing Reviewer API")

# 1. Endpoint: /review (อัปโหลดแปลน -> ได้รับรายงานผล)
@app.post("/review", response_model=DrawingReviewReport)
def review_drawing():
    mock_items = [
        ChecklistItem(
            item_id="Title-01",
            description="ตรวจสอบความครบถ้วนของ Title Block",
            status="pass",
            evidence="พบบล็อกชื่อที่มุมขวาล่าง ระบุชื่อโปรเจกต์ชัดเจน",
            standard_ref="ISO 128"
        ),
        ChecklistItem(
            item_id="Dim-01",
            description="ตรวจสอบหน่วยของการให้ขนาด (Dimensioning)",
            status="fail",
            evidence="ไม่พบการระบุหน่วย (mm/inch) ในจุดบอกขนาดรวม",
            standard_ref="ASME Y14.5"
        )
    ]
    
    return DrawingReviewReport(
        drawing_id="DWG-2026-001",
        overall_status="review_required",
        items=mock_items,
        open_questions=["หน่วยที่หายไปควรเป็นมิลลิเมตรหรือนิ้ว?"]
    )

# 2. Endpoint: /checklist (ดึงข้อมูลโครงสร้าง Checklist)
@app.get("/checklist")
def get_checklist():
    return {"message": "Return active checklist definition (Mock Data)"}

# 3. Endpoint: /review/{id}/feedback (ส่ง Feedback แก้ไขกลับเข้าระบบ)
@app.post("/review/{id}/feedback")
def submit_feedback(id: str):
    return {"message": f"Received human correction for drawing ID: {id} (Mock Data)"}

# 4. Endpoint: /evaluate (สั่งประเมินผลเทียบกับ Gold Standard)
@app.post("/evaluate")
def batch_evaluate():
    return {"message": "Batch evaluation process completed (Mock Data)"}