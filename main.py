import os
import json
import asyncio

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
import google.generativeai as genai

from schemas import (
    DrawingUploadRequest,
    DrawingReviewReport,
    ChecklistItem,
    RouterDecision,
    SpecialistFindings,
    JudgeDecision,
)

load_dotenv()
app = FastAPI(title="Engineering Drawing Reviewer API")

api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))


# ---------------------------------------------------------
# 🔁 Retry wrapper — free-tier Gemini quota is 15 requests/min.
# One /review call already uses 5 requests (router + 3 specialists + judge),
# so a 429 mid-pipeline is expected under load, not a one-off fluke.
# Retry with backoff instead of letting the whole request die.
# ---------------------------------------------------------
async def generate_with_retry(prompt: str, generation_config, max_retries: int = 4):
    delay = 15  # seconds — matches the retry_delay Gemini itself reports
    for attempt in range(max_retries + 1):
        try:
            return await model.generate_content_async(prompt, generation_config=generation_config)
        except Exception as e:
            is_rate_limit = "429" in str(e) or "quota" in str(e).lower()
            if not is_rate_limit or attempt == max_retries:
                raise
            print(f"⏳ Rate limited (attempt {attempt + 1}/{max_retries}), waiting {delay}s before retry...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)  # exponential backoff, capped at 60s
    raise RuntimeError("unreachable")

# ---------------------------------------------------------
# 📚 Knowledge Base (RAG) — real 20-item instructor checklist
# ---------------------------------------------------------
KB_PATH = "knowledge_base.json"

# Which checklist categories each specialist is responsible for.
SPECIALIST_CATEGORIES = {
    "title_block": ["GENERAL_METADATA"],
    "dimension": ["DIMENSIONING_RULES", "GDT_AND_TOLERANCING"],
    "notes": ["VIEW_INTEGRITY", "MANUFACTURABILITY"],
}


def load_kb() -> dict:
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"categories": {}}


def retrieve_items(categories: list[str]) -> list[dict]:
    """Pull the checklist items (id, item text, standard) for the given
    KB categories. This is the RAG lookup — deterministic, no hallucination."""
    kb = load_kb()
    items = []
    for cat in categories:
        items.extend(kb.get("categories", {}).get(cat, []))
    return items


def kb_lookup_by_id() -> dict:
    """Flat item_id -> {item, standard} map, used to fill description/
    standard_ref deterministically after the LLM only returns status+evidence."""
    kb = load_kb()
    flat = {}
    for cat_items in kb.get("categories", {}).values():
        for entry in cat_items:
            flat[entry["id"]] = entry
    return flat


# ---------------------------------------------------------
# 🤖 Agent 1: The Router
# ---------------------------------------------------------
async def router_agent(drawing_id: str, drawing_type: str, description: str) -> RouterDecision:
    prompt = f"""
    คุณคือ Router Agent ผู้เชี่ยวชาญด้านการจัดหมวดหมู่งานวิศวกรรม
    แบบแปลนรหัส: {drawing_id} ประเภท: {drawing_type}
    รายละเอียดที่พบในแบบแปลน: {description or "(ไม่มีรายละเอียดเพิ่มเติม)"}

    จงวิเคราะห์ว่างานประเภทนี้ควรส่งให้ specialist ด้านใดตรวจต่อเป็นพิเศษ
    และมีจุดไหนที่ต้องระวังเป็นพิเศษจากรายละเอียดที่ให้มา
    """
    response = await generate_with_retry(
        prompt,
        genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=RouterDecision,
            temperature=0.1,
        ),
    )
    return RouterDecision.model_validate_json(response.text)


# ---------------------------------------------------------
# 🤖 Agent 2: Generic Specialist — grounded in real checklist items
# ---------------------------------------------------------
async def specialist_agent(
    name: str,
    checklist_items: list[dict],
    router_info: RouterDecision,
    drawing_id: str,
    description: str,
) -> SpecialistFindings:
    items_json = json.dumps(checklist_items, ensure_ascii=False, indent=2)
    prompt = f"""
    คุณคือ {name} Specialist Agent มีหน้าที่ตรวจแบบแปลนตามรายการเช็คลิสต์ที่กำหนดเท่านั้น

    คำแนะนำจากหัวหน้า (Router): {router_info.category} - {router_info.specialist_instructions}

    แบบแปลนรหัส: {drawing_id}
    รายละเอียด/ปัญหาที่พบในแบบแปลนนี้: {description or "(ไม่มีรายละเอียดเพิ่มเติม ให้ถือว่าไม่มีปัญหาที่ชัดเจน)"}

    รายการเช็คลิสต์ที่ต้องตรวจ (ต้องตอบให้ครบทุก item_id ในนี้ ห้ามขาด ห้ามเพิ่ม id ใหม่):
    {items_json}

    กติกา:
    - ถ้ารายละเอียดของแบบแปลนไม่ได้พูดถึงปัญหาของ item นั้นเลย ให้ถือว่า status เป็น "pass"
    - ถ้ารายละเอียดตรงกับปัญหาของ item ไหน ให้ item นั้น status เป็น "fail" และเขียน evidence อ้างอิงจากรายละเอียดที่ให้มา
    - ทุก item ต้องมี field "evidence" เสมอ ห้ามเว้นว่างหรือข้าม แม้ status จะเป็น "pass" ก็ต้องเขียน evidence สั้นๆ
      (เช่น "ไม่พบปัญหาที่เกี่ยวข้องในรายละเอียดที่ให้มา")
    - ห้ามสร้าง standard_ref หรือ description เอง ระบบจะเติมให้เองจากฐานข้อมูล
    """
    response = await generate_with_retry(
        prompt,
        genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=SpecialistFindings,
            temperature=0.1,
        ),
    )
    # Gemini's response_schema converter rejects a JSON-schema "default"
    # keyword outright (500 before the model even runs), so `evidence` can't
    # carry a Pydantic default. But the model still sometimes omits the
    # "evidence" key entirely for status="pass" — so model_validate_json()
    # would raise a "Field required" error before assemble_items() ever gets
    # a chance to apply a fallback. Patch the raw dict here, before
    # validation, so a missing key never reaches Pydantic at all.
    raw = json.loads(response.text)
    for finding in raw.get("findings", []):
        if not finding.get("evidence", "").strip():
            finding["evidence"] = "ตรวจสอบแล้วไม่พบปัญหาตามเกณฑ์นี้"
    return SpecialistFindings.model_validate(raw)


def assemble_items(all_findings: list[SpecialistFindings]) -> list[ChecklistItem]:
    """Deterministically merge specialist findings with KB metadata.
    Guarantees every checklist item the specialists were asked about ends up
    with a correct description/standard_ref regardless of what the LLM wrote."""
    kb_flat = kb_lookup_by_id()
    items: list[ChecklistItem] = []
    seen_ids = set()

    for findings in all_findings:
        for f in findings.findings:
            if f.item_id in seen_ids:
                continue
            seen_ids.add(f.item_id)
            kb_entry = kb_flat.get(f.item_id)
            # Fallback guard (moved here from the schema's `default`, which
            # Gemini's response_schema rejects): the model sometimes returns
            # an empty/whitespace-only evidence string for status="pass".
            evidence = f.evidence.strip() if f.evidence and f.evidence.strip() else "ตรวจสอบแล้วไม่พบปัญหาตามเกณฑ์นี้"
            items.append(
                ChecklistItem(
                    item_id=f.item_id,
                    description=kb_entry["item"] if kb_entry else "Unknown checklist item.",
                    status=f.status,
                    evidence=evidence,
                    standard_ref=kb_entry["standard"] if kb_entry else None,
                )
            )

    # Any checklist item that no specialist reported on at all (model skipped
    # it) still needs to show up, rather than silently vanishing.
    all_assigned_ids = {
        entry["id"]
        for cats in SPECIALIST_CATEGORIES.values()
        for entry in retrieve_items(cats)
    }
    for missing_id in all_assigned_ids - seen_ids:
        kb_entry = kb_flat.get(missing_id)
        items.append(
            ChecklistItem(
                item_id=missing_id,
                description=kb_entry["item"] if kb_entry else "Unknown checklist item.",
                status="unclear",
                evidence="No finding returned by any specialist agent.",
                standard_ref=kb_entry["standard"] if kb_entry else None,
            )
        )

    items.sort(key=lambda i: i.item_id)
    return items


# ---------------------------------------------------------
# 🤖 Agent 3: Compliance Judge — LLM-as-judge grounding check
# ---------------------------------------------------------
async def compliance_judge_agent(drawing_id: str, items: list[ChecklistItem]) -> JudgeDecision:
    items_json = json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=2)
    prompt = f"""
    คุณคือ Compliance Judge หน้าที่ของคุณคือตรวจสอบผล (grounding check) ไม่ใช่สร้างผลใหม่

    รหัสแบบแปลน: {drawing_id}
    รายการผลตรวจทั้งหมดจาก Specialist (ห้ามแก้ไข แค่ตัดสินภาพรวม):
    {items_json}

    กฎเหล็ก: ถ้ามี item ใดก็ตามที่ status เป็น "fail" แม้แต่ข้อเดียว ให้ overall_status เป็น "fail" ทันที
    ถ้าไม่มี fail เลยแต่มี "unclear" ให้พิจารณาเป็น "review_required"
    ถ้าทุกข้อ "pass" หรือ "na" ให้เป็น "pass"

    เขียน open_questions เฉพาะกรณีที่มี status "unclear" หรือ evidence ที่ดูไม่ชัดเจนพอ
    """
    response = await generate_with_retry(
        prompt,
        genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=JudgeDecision,
            temperature=0.1,
        ),
    )
    return JudgeDecision.model_validate_json(response.text)


# ---------------------------------------------------------
# 🚦 Main API Endpoint
# ---------------------------------------------------------
@app.post("/review", response_model=DrawingReviewReport)
async def review_drawing(request: DrawingUploadRequest):
    try:
        print(f"\n--- เริ่มต้นตรวจสอบแบบแปลน: {request.drawing_id} ---")

        print("1. [Router] กำลังวิเคราะห์ประเภทงาน...")
        router_decision = await router_agent(
            request.drawing_id, request.drawing_type, request.description
        )

        print("2. [Specialists] กระจายงานให้ทีมผู้เชี่ยวชาญทั้ง 3 ตรวจสอบพร้อมกัน...")
        tb_findings, dim_findings, notes_findings = await asyncio.gather(
            specialist_agent(
                "Title Block",
                retrieve_items(SPECIALIST_CATEGORIES["title_block"]),
                router_decision, request.drawing_id, request.description,
            ),
            specialist_agent(
                "Dimension & GD&T",
                retrieve_items(SPECIALIST_CATEGORIES["dimension"]),
                router_decision, request.drawing_id, request.description,
            ),
            specialist_agent(
                "Notes & View Integrity",
                retrieve_items(SPECIALIST_CATEGORIES["notes"]),
                router_decision, request.drawing_id, request.description,
            ),
        )
        print("   --> ลูกน้องทั้ง 3 คนส่งรายงานครบแล้ว!")

        items = assemble_items([tb_findings, dim_findings, notes_findings])

        print("3. [Judge] ตรวจสอบภาพรวมและตัดสินผล...")
        judge_decision = await compliance_judge_agent(request.drawing_id, items)

        final_report = DrawingReviewReport(
            drawing_id=request.drawing_id,
            overall_status=judge_decision.overall_status,
            items=items,
            open_questions=judge_decision.open_questions,
        )

        print("✅ กระบวนการเสร็จสิ้น! ส่งผลลัพธ์กลับไปยังผู้ใช้งาน...\n")
        return final_report

    except Exception as e:
        print(f"Server Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
