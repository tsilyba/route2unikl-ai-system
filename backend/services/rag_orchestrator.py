# backend/services/rag_orchestrator.py
import os
import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from core.chroma import get_program_collection

# Load environment variables
load_dotenv()

logger = logging.getLogger("rag_orchestrator")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "861d89acd7f24138a3a4f438c1e463f5.-Baxl5z7Cwg9iVqdQcFOWZ0T")
# Free Ollama Cloud model (verified free tier: minimax-m3.1-flash, gpt-oss:20b, nemotron-3-nano:30b)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "minimax-m3.1-flash")

# Restrict specifically to Foundation Testplan programs
FOUNDATION_TESTPLAN_IDS = [
    "unikl_miit_foundation_computer",
    "unikl_bis_foundation_business"
]


def retrieve_program_context(interests: List[str]) -> Dict[str, Any]:
    """
    Queries ChromaDB using the student's declared interest(s).
    Specifically filters for the Foundation testplan programmes to return the
    matching programme context for RAG generation.
    """
    collection = get_program_collection()

    query_str = " ".join(interests) if interests else "General Academic Studies"

    try:
        results = collection.query(
            query_texts=[query_str],
            n_results=1,
            where={"program_id": {"$in": FOUNDATION_TESTPLAN_IDS}}
        )

        if results and results["metadatas"] and results["metadatas"][0]:
            matched_meta = results["metadatas"][0][0]
            matched_doc = results["documents"][0][0] if results.get("documents") else ""
            matched_id = results["ids"][0][0]

            return {
                "program_id": matched_id,
                "title": matched_meta.get("title", "Foundation Studies"),
                "campuses": matched_meta.get("campuses", "UniKL"),
                "pathway_category": matched_meta.get("pathway_category", ""),
                "specialisation": matched_meta.get("specialisation", ""),
                "document_text": matched_doc,
                "distance": results["distances"][0][0] if results.get("distances") else 0.0
            }
    except Exception as e:
        logger.error(f"ChromaDB query error: {e}")

    # Default fallback to Foundation in Computer Technology if query fails
    return {
        "program_id": "unikl_miit_foundation_computer",
        "title": "Foundation in Computer Technology",
        "campuses": "UniKL MIIT",
        "pathway_category": "Computing & Digital Technology",
        "specialisation": "Information Technology",
        "document_text": "Foundation in Computer Technology introduces programming logic, computational thinking, discrete structures, and computer architecture.",
        "distance": 0.0
    }


def build_assessment_prompt(interests: List[str], program_context: Dict[str, Any]) -> str:
    """
    Constructs the prompt embedding both the student's declared interests
    and the retrieved ChromaDB programme context.
    """
    declared_interest_str = ", ".join(interests) if interests else "General Technology & Business"

    return f"""You are an expert psychometric evaluator and academic advisor for Universiti Kuala Lumpur (UniKL).

[STUDENT CONTEXT]
- Declared Academic Interests: {declared_interest_str}

[MATCHED UNIKL FOUNDATION PROGRAMME (FROM VECTOR DATABASE)]
- Programme: {program_context.get('title')} ({program_context.get('campuses')})
- Pathway Category: {program_context.get('pathway_category')}
- Specialisation: {program_context.get('specialisation')}
- Academic Scope & Context: {program_context.get('document_text')}

[TASK]
Generate EXACTLY 10 Multiple-Choice Questions (MCQ) for this student's AI Assessment:
- Questions 1 to 5: Cognitive Ability (Logical deduction, analytical thinking, computational or business logic, pattern identification, structured problem-solving relevant to {program_context.get('title')}).
- Questions 6 to 10: Strengths & Workstyle (Grit, learning agility, prioritization, adaptability, collaborative mindset, and intrinsic motivation required to excel in this field).

[RULES]
1. Relate each question contextually to the student's declared interests ({declared_interest_str}) and the matched foundation programme.
2. Provide exactly 4 realistic options (A, B, C, D) per question.
3. Indicate the single best/optimal answer via "correctIndex" (integer: 0, 1, 2, or 3).
4. Return ONLY a valid JSON object matching the exact schema below, with no markdown code fences or conversational text.

[JSON SCHEMA]
{{
  "matched_program": "{program_context.get('title')}",
  "campus": "{program_context.get('campuses')}",
  "questions": [
    {{
      "id": 1,
      "dimension": "Cognitive",
      "category": "Logical Reasoning",
      "question": "Scenario-based question text...",
      "options": [
        "First option",
        "Second option",
        "Third option",
        "Fourth option"
      ],
      "correctIndex": 1,
      "explanation": "Why this answer demonstrates the strongest aptitude."
    }}
  ]
}}
"""


async def call_ollama_cloud(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls the Ollama Cloud chat API using the free-tier model.
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json"
    }

    # Free tier candidate models on Ollama Cloud
    models_to_try = [OLLAMA_MODEL, "gpt-oss:20b", "nemotron-3-nano:30b"]

    async with httpx.AsyncClient(timeout=45.0) as client:
        for model in models_to_try:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a specialized JSON-only generator for psychometric academic assessments. Output strictly valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": False,
                "format": "json"
            }

            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    raw_content = response.json().get("message", {}).get("content", "").strip()
                    # Strip any potential markdown wrappers if returned
                    if raw_content.startswith("```json"):
                        raw_content = raw_content[7:]
                    if raw_content.startswith("```"):
                        raw_content = raw_content[3:]
                    if raw_content.endswith("```"):
                        raw_content = raw_content[:-3]
                    raw_content = raw_content.strip()

                    parsed = json.loads(raw_content)
                    if "questions" in parsed and len(parsed["questions"]) > 0:
                        return parsed
                else:
                    logger.warning(f"Ollama Cloud ({model}) returned {response.status_code}: {response.text[:120]}")
            except Exception as e:
                logger.error(f"Error calling Ollama Cloud with {model}: {e}")

    return None


def get_static_fallback_questions(interests: List[str], program_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    High-quality offline fallback questions tailored specifically to the
    Foundation testplan programs if the cloud API is unreachable.
    """
    is_computer = "computer" in program_context.get("program_id", "").lower()
    interest_name = interests[0] if interests else ("Computing" if is_computer else "Business")

    if is_computer:
        questions = [
            # 5 Cognitive
            {
                "id": 1,
                "dimension": "Cognitive",
                "category": "Algorithmic Logic",
                "question": "A sorting process compares adjacent items and swaps them if out of order. If a list of 5 items is in reverse order, what is the maximum number of swaps required in the worst-case scenario?",
                "options": ["5 swaps", "10 swaps", "15 swaps", "20 swaps"],
                "correctIndex": 1,
                "explanation": "In bubble sort logic, n(n-1)/2 swaps are needed for reverse order, which is 5*4/2 = 10 swaps."
            },
            {
                "id": 2,
                "dimension": "Cognitive",
                "category": "Pattern Recognition",
                "question": "Analyze the sequence: 2, 6, 12, 20, 30, ?. What is the next logical value in this computational growth pattern?",
                "options": ["38", "40", "42", "44"],
                "correctIndex": 2,
                "explanation": "The differences are +4, +6, +8, +10, +12. Thus 30 + 12 = 42 (n*(n+1))."
            },
            {
                "id": 3,
                "dimension": "Cognitive",
                "category": "Problem Decomposition",
                "question": "When debugging a software application that crashes only when submitting a form with large file attachments, what is the most systematic first troubleshooting step?",
                "options": [
                    "Rewrite the entire form submission code from scratch.",
                    "Isolate the file size limits by testing with gradually increasing payloads.",
                    "Restart the computer and assume it was a memory glitch.",
                    "Remove file uploading entirely from the application."
                ],
                "correctIndex": 1,
                "explanation": "Isolating variables systematically determines the threshold failure point without introducing new bugs."
            },
            {
                "id": 4,
                "dimension": "Cognitive",
                "category": "Conditional Logic",
                "question": "If Condition A is TRUE and Condition B is FALSE, which of the following logical boolean expressions evaluates to TRUE?",
                "options": [
                    "A AND B",
                    "NOT(A) OR B",
                    "A OR B",
                    "NOT(A OR NOT B)"
                ],
                "correctIndex": 2,
                "explanation": "An OR operation evaluates to TRUE if at least one operand is TRUE."
            },
            {
                "id": 5,
                "dimension": "Cognitive",
                "category": "Data Flow & Architecture",
                "question": "In a distributed digital system, what is the primary purpose of a cache between a web application and its central database?",
                "options": [
                    "To permanently store all system logs.",
                    "To reduce latency and decrease database load for frequently accessed data.",
                    "To encrypt passwords before transmission.",
                    "To replace the database entirely."
                ],
                "correctIndex": 1,
                "explanation": "Caching stores high-frequency data in rapid memory to minimize expensive database queries."
            },
            # 5 Strengths
            {
                "id": 6,
                "dimension": "Strengths",
                "category": "Learning Agility",
                "question": f"Given your interest in {interest_name}, how do you approach learning a completely unfamiliar programming library or framework required for an upcoming project?",
                "options": [
                    "Review official documentation and build a small test prototype to explore how it works.",
                    "Wait until someone else in the group figures it out and explains it to me.",
                    "Avoid using the new tool and stick strictly to older tools I already know.",
                    "Copy and paste random code snippets from online forums until it compiles."
                ],
                "correctIndex": 0,
                "explanation": "Proactive hands-on prototyping from authoritative docs is the hallmark of technical agility."
            },
            {
                "id": 7,
                "dimension": "Strengths",
                "category": "Persistence & Grit",
                "question": "You have spent 3 hours trying to fix an enigmatic syntax error in your code without success. How do you respond?",
                "options": [
                    "Abandon the task and choose an easier topic.",
                    "Step away briefly, re-trace the execution line-by-line, and use targeted logging.",
                    "Submit the broken project and explain that the tool was faulty.",
                    "Rely on guesswork changes to arbitrary lines of code."
                ],
                "correctIndex": 1,
                "explanation": "Structured debugging paired with emotional resilience demonstrates engineering grit."
            },
            {
                "id": 8,
                "dimension": "Strengths",
                "category": "Collaborative Mindset",
                "question": "During a technical team project, a teammate proposes a solution that differs significantly from your architecture. How do you handle this?",
                "options": [
                    "Insist on your approach without reviewing their proposal.",
                    "Objectively evaluate both approaches against the project requirements and performance benchmarks.",
                    "Complain to the instructor that team members disagree.",
                    "Disengage from the discussion and let them do all the work."
                ],
                "correctIndex": 1,
                "explanation": "Data-driven and criteria-based collaboration leads to the highest quality technical outcomes."
            },
            {
                "id": 9,
                "dimension": "Strengths",
                "category": "Prioritization",
                "question": "You have 3 deadlines in 48 hours: a major programming assignment (40%), an online quiz (5%), and code documentation (10%). How do you allocate your time?",
                "options": [
                    "Complete the 5% quiz first and spend the remaining time doing leisure activities.",
                    "Prioritize the high-weight assignment first while blocking fixed windows for the quiz and documentation.",
                    "Try to do all three simultaneously in the same browser window.",
                    "Ask for an extension on all three without attempting any."
                ],
                "correctIndex": 1,
                "explanation": "High-impact task prioritization balances maximum academic yield with schedule adherence."
            },
            {
                "id": 10,
                "dimension": "Strengths",
                "category": "Analytical Ethics",
                "question": "You find an open-source security vulnerability in a campus web portal. What is the professional course of action?",
                "options": [
                    "Share the exploit publicly on social media for recognition.",
                    "Use the exploit to modify student records.",
                    "Responsibly report the vulnerability privately to the institution's IT security team.",
                    "Ignore it completely and pretend you never saw it."
                ],
                "correctIndex": 2,
                "explanation": "Responsible disclosure demonstrates cyber ethics and professional accountability."
            }
        ]
    else:
        # Foundation in Business
        questions = [
            # 5 Cognitive
            {
                "id": 1,
                "dimension": "Cognitive",
                "category": "Numerical Reasoning",
                "question": "A product costs RM 80 to produce and is sold at a 25% markup on cost. What is the retail selling price?",
                "options": ["RM 95", "RM 100", "RM 105", "RM 120"],
                "correctIndex": 1,
                "explanation": "Markup = 25% of RM 80 = RM 20. Selling price = RM 80 + RM 20 = RM 100."
            },
            {
                "id": 2,
                "dimension": "Cognitive",
                "category": "Market Analysis",
                "question": "If the market supply of an agricultural commodity decreases sharply due to drought while consumer demand remains constant, what is the expected market effect?",
                "options": [
                    "Price increases and equilibrium quantity decreases.",
                    "Both price and quantity decrease.",
                    "Price decreases and quantity increases.",
                    "Both price and quantity remain unchanged."
                ],
                "correctIndex": 0,
                "explanation": "A leftward shift in supply increases equilibrium price and lowers quantity."
            },
            {
                "id": 3,
                "dimension": "Cognitive",
                "category": "Operational Logic",
                "question": "A retail business has high revenue but faces a severe cash shortage to pay immediate supplier invoices. What financial dynamic explains this situation?",
                "options": [
                    "High customer credit sales with long collection periods tying up liquidity.",
                    "Excessive net profit margins.",
                    "Underpriced goods selling out too quickly for cash.",
                    "Decreased operational overhead."
                ],
                "correctIndex": 0,
                "explanation": "Accrual revenue does not equate to liquid cash when receivables are delayed."
            },
            {
                "id": 4,
                "dimension": "Cognitive",
                "category": "Strategic Deductions",
                "question": "A competitor enters the market offering a 30% discount on a substitute product. What is the most sustainable strategic initial response?",
                "options": [
                    "Immediately cut prices by 50% without analyzing unit margins.",
                    "Analyze competitor cost structure and emphasize our product's unique value differentiation.",
                    "Exit the market immediately.",
                    "File a legal injunction without commercial justification."
                ],
                "correctIndex": 1,
                "explanation": "Value differentiation and margin analysis prevent destructive price wars."
            },
            {
                "id": 5,
                "dimension": "Cognitive",
                "category": "Decision Matrix",
                "question": "When choosing between two supplier contracts with identical prices, which metric best reveals reliability?",
                "options": [
                    "Supplier headquarters building size.",
                    "On-time in-full (OTIF) historical delivery rate and defect percentage.",
                    "The font style used in their quotation.",
                    "Number of social media followers."
                ],
                "correctIndex": 1,
                "explanation": "OTIF and defect rates are objective quantitative indicators of supply chain capability."
            },
            # 5 Strengths
            {
                "id": 6,
                "dimension": "Strengths",
                "category": "Leadership & Initiative",
                "question": f"As someone passionate about {interest_name}, your study group has stalled because no one wants to lead the presentation preparation. What do you do?",
                "options": [
                    "Propose a structured agenda, outline key milestones, and volunteer to coordinate section deliverables.",
                    "Wait for the lecturer to assign roles forcefully.",
                    "Do only your individual slides and ignore the group flow.",
                    "Switch to another group without communicating."
                ],
                "correctIndex": 0,
                "explanation": "Constructive initiative and structuring clarity define leadership potential."
            },
            {
                "id": 7,
                "dimension": "Strengths",
                "category": "Negotiation & Empathy",
                "question": "Two key stakeholders disagree sharply on a marketing budget allocation. How do you facilitate consensus?",
                "options": [
                    "Vote for the loudest stakeholder to finish the meeting quickly.",
                    "Identify shared organizational objectives and propose a phased budget with review milestones.",
                    "Dismiss both stakeholders' concerns as irrelevant.",
                    "Cancel the marketing campaign entirely."
                ],
                "correctIndex": 1,
                "explanation": "Focusing on shared goals and phased validation builds sustainable alignment."
            },
            {
                "id": 8,
                "dimension": "Strengths",
                "category": "Adaptability",
                "question": "A sudden supply chain regulation renders your preferred packaging material unusable one week before launch. How do you respond?",
                "options": [
                    "Halt operations indefinitely and blame the regulatory authorities.",
                    "Quickly audit pre-qualified compliant alternative suppliers and adjust timelines transparently.",
                    "Use the banned material anyway and hope regulators do not check.",
                    "Resign from the project."
                ],
                "correctIndex": 1,
                "explanation": "Agile compliance auditing mitigates disruption while upholding corporate governance."
            },
            {
                "id": 9,
                "dimension": "Strengths",
                "category": "Grit & Resilience",
                "question": "Your team's business plan pitch was rejected by a simulated investor panel with critical feedback on financial forecasts. What is your reaction?",
                "options": [
                    "Dismiss the judges as uninformed.",
                    "Break down the panel's feedback, refine the unit economics, and prepare a strengthened revision.",
                    "Give up on business studies entirely.",
                    "Argue aggressively during the feedback session."
                ],
                "correctIndex": 1,
                "explanation": "Receptivity to critical critique and iterative refinement characterizes growth mindset."
            },
            {
                "id": 10,
                "dimension": "Strengths",
                "category": "Customer Centricity",
                "question": "A customer posts negative feedback about an order fulfillment delay. What is the most effective managerial approach?",
                "options": [
                    "Delete the customer's comment and block their account.",
                    "Acknowledge the delay sincerely, explain corrective steps taken, and provide a prompt resolution.",
                    "Blame the third-party delivery rider publicly.",
                    "Ignore the review completely."
                ],
                "correctIndex": 1,
                "explanation": "Transparent accountability and prompt resolution convert negative friction into brand trust."
            }
        ]

    return {
        "matched_program": program_context.get("title"),
        "campus": program_context.get("campuses"),
        "questions": questions
    }


async def generate_rag_assessment(interests: List[str]) -> Dict[str, Any]:
    """
    RAG Orchestration Pipeline:
    1. Query ChromaDB for the matching Foundation testplan program.
    2. Extract context and construct prompt incorporating declared interests.
    3. Call Ollama Cloud to generate 10 MCQs (5 Cognitive, 5 Strengths).
    4. Fall back to structured baseline questions if Ollama Cloud is offline.
    """
    # 1. Retrieve ChromaDB context
    program_context = retrieve_program_context(interests)

    # 2. Build prompt
    prompt = build_assessment_prompt(interests, program_context)

    # 3. Call Ollama Cloud
    ai_response = await call_ollama_cloud(prompt)

    if ai_response and "questions" in ai_response and len(ai_response["questions"]) == 10:
        questions = ai_response["questions"]
        source = "OLLAMA_CLOUD_RAG"
    else:
        fallback = get_static_fallback_questions(interests, program_context)
        questions = fallback["questions"]
        source = "RAG_CONTEXT_ENHANCED_FALLBACK"

    # Normalize IDs (1 to 10) and ensure consistent dimensions (1-5 Cognitive, 6-10 Strengths)
    for idx, q in enumerate(questions):
        q["id"] = idx + 1
        dim = str(q.get("dimension", "")).lower()
        if "strength" in dim or "behavior" in dim or "workstyle" in dim or idx >= 5:
            q["dimension"] = "Strengths"
        else:
            q["dimension"] = "Cognitive"

    return {
        "status": "success",
        "source": source,
        "declared_interests": interests,
        "matched_program": {
            "program_id": program_context.get("program_id"),
            "title": program_context.get("title"),
            "campuses": program_context.get("campuses"),
            "pathway_category": program_context.get("pathway_category"),
            "specialisation": program_context.get("specialisation")
        },
        "total_questions": len(questions),
        "questions": questions
    }