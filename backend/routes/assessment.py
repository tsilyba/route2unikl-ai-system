# backend/routes/assessment.py
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from services.rag_orchestrator import generate_rag_assessment
from services.recommendation_service import calculate_program_recommendations
from core.firebase import initialize_firebase

logger = logging.getLogger("assessment_route")
router = APIRouter()


class MCQOption(BaseModel):
    id: int
    dimension: str
    category: str
    question: str
    options: List[str]
    correctIndex: int
    explanation: Optional[str] = None


class AssessmentRequest(BaseModel):
    interests: Optional[List[str]] = Field(default_factory=list, description="Declared student academic interests")
    userId: Optional[str] = Field(default=None, description="Firebase User UID")


class RecommendationRequest(BaseModel):
    userId: Optional[str] = Field(default=None, description="Firebase User UID")
    interests: Optional[List[str]] = Field(default_factory=list, description="Declared interests")
    grades: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="SPM / exam grades")
    assessmentScore: Optional[float] = Field(default=None, description="Score on AI assessment out of 100")


@router.post("/generate-questions")
async def generate_questions_endpoint(payload: AssessmentRequest):
    """
    RAG Orchestration Endpoint:
    1. Reads declared interests from payload.
    2. Queries ChromaDB for matching Foundation programme in unikl_foundation_testplan.json.
    3. Calls Ollama Cloud with the retrieved context.
    4. Returns 10 MCQs covering Cognitive & Strengths dimensions.
    """
    try:
        interests = payload.interests or []
        result = await generate_rag_assessment(interests)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate assessment: {str(e)}")


@router.post("/recommend")
async def recommend_endpoint(payload: RecommendationRequest):
    """
    Recommendation & Preparation Plan Endpoint:
    1. Evaluates student academic grades, declared interests, and cognitive assessment score.
    2. Calculates multi-factor match percentages against unikl_foundation_testplan.json.
    3. Returns ranked recommendations with preparatory learning guidelines.
    """
    try:
        interests = payload.interests or []
        grades = payload.grades or []
        assessment_score = payload.assessmentScore

        # Auto-fetch from Firestore if missing and userId is given
        if payload.userId and (not interests or not grades or assessment_score is None):
            try:
                db = initialize_firebase()
                # 1. Fetch user doc for interests
                if not interests:
                    u_doc = db.collection("users").document(payload.userId).get()
                    if u_doc.exists:
                        interests = u_doc.to_dict().get("chosenInterests", [])

                # 2. Fetch results doc for grades
                if not grades:
                    r_doc = db.collection("results").document(payload.userId).get()
                    if r_doc.exists:
                        grades = r_doc.to_dict().get("results", [])

                # 3. Fetch assessment doc for score
                if assessment_score is None:
                    a_doc = db.collection("ai_assessments").document(payload.userId).get()
                    if a_doc.exists:
                        answers = a_doc.to_dict().get("answers", [])
                        if answers:
                            correct_cnt = sum(1 for a in answers if a.get("isCorrect") is True)
                            assessment_score = (correct_cnt / len(answers)) * 100
            except Exception as fe:
                logger.warning(f"Firestore auto-fetch fallback: {fe}")

        recommendations = calculate_program_recommendations(
            interests=interests,
            grades=grades,
            assessment_score=assessment_score
        )

        return {
            "status": "success",
            "userId": payload.userId,
            "declared_interests": interests,
            "total_recommendations": len(recommendations),
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


