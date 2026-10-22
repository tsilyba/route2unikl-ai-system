# backend/services/recommendation_service.py
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("recommendation_service")

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
TESTPLAN_JSON_PATH = ROOT_DIR / "frontend" / "src" / "assets" / "unikl_foundation_testplan.json"

GRADE_SCALE = {
    "A+": 100, "A": 100, "A-": 90,
    "B+": 80, "B": 75,
    "C+": 65, "C": 60,
    "D": 45, "E": 40, "G": 0
}

CREDIT_GRADES = {"A+", "A", "A-", "B+", "B", "C+", "C"}


def load_foundation_programs() -> List[Dict[str, Any]]:
    """Loads foundation programmes strictly from unikl_foundation_testplan.json."""
    if not TESTPLAN_JSON_PATH.exists():
        logger.error(f"Testplan JSON not found at: {TESTPLAN_JSON_PATH}")
        return []
    with open(TESTPLAN_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_subject_name(name: str) -> str:
    """Normalizes subject names for consistent matching."""
    n = name.upper().strip()
    if "INGGERIS" in n or "ENGLISH" in n:
        return "BAHASA INGGERIS"
    if "MELAYU" in n or "MALAYSIA" in n:
        return "BAHASA MELAYU"
    if "TAMBAHAN" in n or "ADDITIONAL MATH" in n:
        return "MATEMATIK TAMBAHAN"
    if "MATEMATIK" in n or "MATH" in n:
        return "MATEMATIK"
    if "SEJARAH" in n or "HISTORY" in n:
        return "SEJARAH"
    return n


def evaluate_academic_match(grades: List[Dict[str, str]], program: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates SPM academic eligibility and calculates an academic score (0-100)
    against the program's minimum requirements.
    """
    if not grades:
        return {"score": 75, "is_eligible": True, "reasons": ["Default baseline eligibility assumed."]}

    # Map normalized subject to grade
    grade_map = {}
    credits_count = 0
    total_points = 0
    graded_count = 0

    for item in grades:
        sub = normalize_subject_name(item.get("subject", ""))
        grd = item.get("grade", "").upper().strip()
        if grd:
            grade_map[sub] = grd
            if grd in CREDIT_GRADES:
                credits_count += 1
            if grd in GRADE_SCALE:
                total_points += GRADE_SCALE[grd]
                graded_count += 1

    unmet_requirements = []

    # 1. Minimum Credits check
    min_credits = program.get("min_spm_credits", 5)
    if credits_count < min_credits:
        unmet_requirements.append(f"Requires minimum {min_credits} credits (currently {credits_count} credits).")

    # 2. BM Grade check
    bm_min = program.get("min_bm_grade", "C")
    bm_actual = grade_map.get("BAHASA MELAYU", "")
    if bm_min and bm_min != "NONE":
        bm_pts = GRADE_SCALE.get(bm_actual, 0)
        bm_req_pts = GRADE_SCALE.get(bm_min, 60)
        if bm_pts < bm_req_pts:
            unmet_requirements.append(f"Bahasa Melayu must be grade {bm_min} or higher (current: {bm_actual or 'N/A'}).")

    # 3. BI Grade check
    bi_min = program.get("min_bi_grade", "C")
    bi_actual = grade_map.get("BAHASA INGGERIS", "")
    if bi_min and bi_min != "NONE":
        bi_pts = GRADE_SCALE.get(bi_actual, 0)
        bi_req_pts = GRADE_SCALE.get(bi_min, 60)
        if bi_pts < bi_req_pts:
            unmet_requirements.append(f"Bahasa Inggeris must be grade {bi_min} or higher (current: {bi_actual or 'N/A'}).")

    # 4. Math Grade check
    math_min = program.get("min_math_grade", "C")
    math_actual = grade_map.get("MATEMATIK", "")
    if math_min and math_min != "NONE":
        math_pts = GRADE_SCALE.get(math_actual, 0)
        math_req_pts = GRADE_SCALE.get(math_min, 60)
        if math_pts < math_req_pts:
            unmet_requirements.append(f"Matematik must be grade {math_min} or higher (current: {math_actual or 'N/A'}).")

    # Base academic score calculation
    base_avg = (total_points / graded_count) if graded_count > 0 else 70

    # Specific bonuses for domain subjects
    bonus = 0
    if "computer" in program.get("program_id", "").lower():
        if grade_map.get("MATEMATIK") in {"A+", "A", "A-"}:
            bonus += 8
        if grade_map.get("MATEMATIK TAMBAHAN") in CREDIT_GRADES:
            bonus += 5
    elif "business" in program.get("program_id", "").lower():
        if grade_map.get("MATEMATIK") in CREDIT_GRADES:
            bonus += 5
        if grade_map.get("BAHASA INGGERIS") in {"A+", "A", "A-"}:
            bonus += 5

    raw_score = min(100, base_avg + bonus)

    if unmet_requirements:
        # Deduct if hard requirements are not met
        adjusted_score = max(45, raw_score - (len(unmet_requirements) * 15))
        return {
            "score": round(adjusted_score),
            "is_eligible": False,
            "reasons": unmet_requirements
        }

    return {
        "score": round(raw_score),
        "is_eligible": True,
        "reasons": [
            f"✓ All minimum requirements met ({credits_count} credits achieved).",
            f"✓ Core language & STEM prerequisites satisfied."
        ]
    }


def evaluate_interest_match(interests: List[str], program: Dict[str, Any]) -> float:
    """Calculates interest alignment score (0-100)."""
    if not interests:
        return 70.0

    user_text = " ".join(interests).lower()
    pathway = program.get("pathway_category", "").lower()
    major = program.get("major_category", "").lower()
    specialisation = program.get("specialisation", "").lower()

    # Exact or high keyword overlap
    if pathway in user_text or any(i.lower() in pathway for i in interests):
        return 98.0
    if major in user_text or specialisation in user_text:
        return 92.0

    # Domain specific matching
    if "computer" in program.get("program_id", "").lower():
        if any(w in user_text for w in ["computing", "software", "it", "technology", "multimedia", "digital"]):
            return 96.0
        elif any(w in user_text for w in ["engineering", "science"]):
            return 80.0
        else:
            return 60.0
    elif "business" in program.get("program_id", "").lower():
        if any(w in user_text for w in ["business", "management", "logistics", "marketing", "finance", "accounting"]):
            return 96.0
        elif any(w in user_text for w in ["arts", "social"]):
            return 80.0
        else:
            return 60.0

    return 70.0


def calculate_program_recommendations(
    interests: List[str],
    grades: List[Dict[str, str]],
    assessment_score: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Computes weighted match percentages and compiles customized
    preparation plans focused strictly on unikl_foundation_testplan.json.
    """
    programs = load_foundation_programs()
    if not programs:
        return []

    # If assessment_score is not passed, default to a neutral positive 85%
    if assessment_score is None:
        assessment_score = 85.0

    recommendations = []

    for prog in programs:
        prog_id = prog.get("program_id")
        title = prog.get("title")

        # 1. Academic evaluation (Weight: 35%)
        acad_eval = evaluate_academic_match(grades, prog)
        acad_score = acad_eval["score"]
        is_eligible = acad_eval["is_eligible"]

        # 2. Interest alignment (Weight: 35%)
        interest_score = evaluate_interest_match(interests, prog)

        # 3. Cognitive & Strengths score (Weight: 30%)
        # Add slight domain affinity
        is_computer = "computer" in prog_id.lower()
        has_tech_interest = any("comput" in i.lower() or "tech" in i.lower() for i in interests)
        if is_computer and has_tech_interest:
            adjusted_assessment = min(100.0, assessment_score + 5.0)
        else:
            adjusted_assessment = assessment_score

        # Weighted calculation
        final_pct = round((0.35 * acad_score) + (0.35 * interest_score) + (0.30 * adjusted_assessment))

        # Clamp between 50 and 98
        final_pct = max(50, min(98, final_pct))

        # Determine Match Quality Label
        if is_eligible and final_pct >= 85:
            match_label = "Strong Match"
            badge_color = "emerald"
        elif is_eligible and final_pct >= 70:
            match_label = "Good Match"
            badge_color = "blue"
        else:
            match_label = "Alternative Pathway" if not is_eligible else "Moderate Match"
            badge_color = "amber"

        # Construct specific AI fit explanations
        fit_reasons = []
        if interest_score >= 85:
            fit_reasons.append(f"Highly aligns with your chosen interest in {prog.get('pathway_category')}.")
        if is_eligible:
            fit_reasons.append("Your SPM grades fully meet all core academic requirements.")
        else:
            fit_reasons.extend(acad_eval["reasons"])

        if is_computer:
            fit_reasons.append("Demonstrated solid performance in algorithmic logic & problem-solving dimensions.")
        else:
            fit_reasons.append("Demonstrated analytical deduction and collaborative leadership strengths.")

        recommendations.append({
            "program_id": prog_id,
            "title": title,
            "level": prog.get("level", "Foundation"),
            "campuses": prog.get("campuses", "UniKL"),
            "major_category": prog.get("major_category"),
            "pathway_category": prog.get("pathway_category"),
            "specialisation": prog.get("specialisation"),
            "short_description": prog.get("short_description"),
            "knowledge_context": prog.get("knowledge_context"),
            "link": prog.get("link"),
            "min_requirements_text": prog.get("min_requirements_text"),
            "match_percentage": final_pct,
            "match_label": match_label,
            "badge_color": badge_color,
            "is_eligible": is_eligible,
            "fit_reasons": fit_reasons,
            "score_breakdown": {
                "academic": round(acad_score),
                "interest": round(interest_score),
                "assessment": round(adjusted_assessment)
            },
            "preparatory_guideline": prog.get("preparatory_guideline", []),
            "alternative_pathway_ids": prog.get("alternative_pathway_ids", [])
        })

    # Rank by match percentage descending
    recommendations.sort(key=lambda x: x["match_percentage"], reverse=True)
    return recommendations

