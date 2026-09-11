import asyncio
import json
import httpx

GOLD_SET_PATH = "gold_set.json"
API_URL = "http://127.0.0.1:8000/review"

# Subset of 6 (within the 5-10 range the spec asks for), balanced pass/fail.
SUBSET_IDS = ["DRW-001", "DRW-003", "DRW-005", "DRW-007", "DRW-009", "DRW-011"]


def load_subset() -> list[dict]:
    with open(GOLD_SET_PATH, "r", encoding="utf-8") as f:
        gold = json.load(f)
    by_id = {d["drawing_id"]: d for d in gold["drawings"]}
    return [by_id[i] for i in SUBSET_IDS if i in by_id]


async def run_evaluation():
    test_cases = load_subset()
    print(f"🚀 เริ่มรันการทดสอบ Evaluation Script บน {len(test_cases)} แบบแปลน...\n")

    results_log = []
    status_correct = 0
    item_exact_matches = 0

    async with httpx.AsyncClient(timeout=90.0) as client:
        for case in test_cases:
            drawing_id = case["drawing_id"]
            print(f"กำลังทดสอบแบบแปลน: {drawing_id}...")
            try:
                response = await client.post(
                    API_URL,
                    json={
                        "drawing_id": drawing_id,
                        "drawing_type": case["drawing_type"],
                        "description": case["description"],
                    },
                )
                data = response.json()

                if response.status_code != 200:
                    detail = data.get("detail", "ไม่ทราบสาเหตุ")
                    print(f"❌ Server Error ({response.status_code}) ตอนรัน {drawing_id}: {detail}\n")
                    results_log.append(f"- **{drawing_id}**: ❌ Server Error ({response.status_code}) — {detail}")
                    continue

                actual_status = data.get("overall_status")
                expected_status = case["expected_status"]
                status_is_correct = actual_status == expected_status
                if status_is_correct:
                    status_correct += 1

                actual_failed_ids = sorted(
                    item["item_id"] for item in data.get("items", []) if item["status"] == "fail"
                )
                expected_failed_ids = sorted(case["expected_failed_items"])
                items_match = actual_failed_ids == expected_failed_ids
                if items_match:
                    item_exact_matches += 1

                mark = "✅ Pass" if status_is_correct else "❌ Failed"
                items_mark = "✅" if items_match else "⚠️"
                log_entry = (
                    f"- **{drawing_id}**: status expected `{expected_status}`, got `{actual_status}` -> {mark} | "
                    f"failed items expected `{expected_failed_ids}`, got `{actual_failed_ids}` -> {items_mark}"
                )
                results_log.append(log_entry)

            except Exception as e:
                results_log.append(f"- **{drawing_id}**: ⚠️ API Error - {str(e)}")

            # Each /review call burns 5 Gemini requests (router + 3 specialists + judge).
            # Free tier = 15 req/min, so pace test cases to stay under that even
            # before the in-app retry/backoff has to kick in.
            print("⏳ พัก 20 วินาทีก่อนยิงไฟล์ถัดไป (กัน rate limit)...")
            await asyncio.sleep(20)

    total = len(test_cases)
    status_accuracy = (status_correct / total) * 100 if total else 0
    item_accuracy = (item_exact_matches / total) * 100 if total else 0

    report_content = f"""# Engineering Drawing Reviewer - Evaluation Report

**Test Set:** Instructor bundle gold set — subset of {total}/12 drawings

## 📊 Metrics
- **Overall Status Accuracy:** {status_accuracy:.2f}% ({status_correct}/{total})
- **Exact Failed-Item-Set Accuracy:** {item_accuracy:.2f}% ({item_exact_matches}/{total})

## 📝 Detailed Results
{chr(10).join(results_log)}
"""
    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    print("\n✅ สร้างไฟล์ eval_report.md เสร็จสมบูรณ์!")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
