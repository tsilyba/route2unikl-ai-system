# backend/services/rag_orchestrator.py
import os
import json
import logging
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from core.chroma import get_program_collection

# Load environment variables from backend/.env
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger("rag_orchestrator")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMMA_CLOUD_MODEL = os.getenv("GEMMA_CLOUD_MODEL", "gemma-4-31b-it")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

ROOT_DIR = BACKEND_DIR.parent
TESTPLAN_JSON_PATH = ROOT_DIR / "frontend" / "src" / "assets" / "unikl_foundation_testplan.json"


def get_all_testplan_ids() -> List[str]:
    """Dynamically loads all program_ids from unikl_foundation_testplan.json."""
    if TESTPLAN_JSON_PATH.exists():
        try:
            with open(TESTPLAN_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                ids = [p["program_id"] for p in data if p.get("program_id")]
                if ids:
                    return ids
        except Exception as e:
            logger.warning(f"Failed to read testplan JSON IDs: {e}")
    return ["unikl_miit_foundation_computer", "unikl_bis_foundation_business"]


def retrieve_program_context(interests: List[str]) -> Dict[str, Any]:
    """
    Queries ChromaDB using the student's declared interest(s).
    Prioritizes programmes matching the student's declared pathway_category,
    with fallback across all programmes in unikl_foundation_testplan.json.
    """
    collection = get_program_collection()
    testplan_ids = get_all_testplan_ids()
    query_str = " ".join(interests) if interests else "General Academic Studies"

    try:
        # 1. Try filtering by exact pathway_category if student selected from the 8 categories
        results = None
        if interests:
            try:
                results = collection.query(
                    query_texts=[query_str],
                    n_results=1,
                    where={"pathway_category": {"$in": interests}}
                )
            except Exception:
                results = None

        # 2. Fallback to querying across all testplan programme IDs
        if not (results and results.get("metadatas") and results["metadatas"][0]):
            results = collection.query(
                query_texts=[query_str],
                n_results=1,
                where={"program_id": {"$in": testplan_ids}}
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
- Declared Academic Interests: 
{declared_interest_str}

[MATCHED UNIKL FOUNDATION PROGRAMME (FROM VECTOR DATABASE)]
- Programme: 
{program_context.get('title')} ({program_context.get('campuses')})
- Pathway Category: 
{program_context.get('pathway_category')}
- Specialisation: 
{program_context.get('specialisation')}
- Academic Scope & Context: 
{program_context.get('document_text')}

[TARGET AUDIENCE & TONE - CRITICAL]
1. Target Level: Malaysian high school graduates and SPM leavers (ages 16–18).
2. Language Standard: Simple, clear, everyday English (CEFR B1/B2 level).
3. Complexity Guardrails:
   - STRICTLY AVOID undergraduate/workplace jargon (e.g., do NOT mention "concurrency", "distributed architectures", "supply chain ERP", "clinical pharmacology", or advanced formulas).
   - Base questions on relatable real-world or secondary school situations (e.g., smartphone apps, sports events, school project teamwork, saving pocket money, organizing a club event, or troubleshooting everyday household gadgets).
   - Test natural curiosity and foundational logic, NOT technical knowledge they have not been taught yet.

[TASK: MALAYSIAN QUALIFICATIONS FRAMEWORK (MQF) ALIGNMENT]
Generate EXACTLY 10 Multiple-Choice Questions (MCQ) tailored to {program_context.get('title')} that align with the 5 MQF Learning Outcome Clusters:

- Questions 1 to 5: MQF Clusters 1, 2 & 3 (Knowledge, Cognitive Skills & Functional/Practical Skills)
  * Dimension: "MQF C1-C3: Cognitive & Practical"
  * Focus on basic conceptual understanding, step-by-step logic, pattern recognition, cause-and-effect, and practical problem-solving application.
  * Keep the problem statement concise (2 to 3 sentences maximum).

- Questions 6 to 10: MQF Clusters 4 & 5 (Personal Skills, Ethics & Professionalism)
  * Dimension: "MQF C4-C5: Personal & Ethics"
  * Focus on resilience when facing errors, study habits, time management, handling group members ethically, academic integrity, and self-directed curiosity.

[RULES]
1. Relate each question contextually to the field of {program_context.get('title')} without making it technically intimidating.
2. Provide exactly 4 clear, plausible options (A, B, C, D) per question.
3. Set "correctIndex" to the single best/optimal answer (integer: 0, 1, 2, or 3).
4. Provide a brief 1-sentence "explanation" written in encouraging language.
5. Return ONLY a valid JSON object matching the exact schema below, with no markdown code fences or conversational text.

[JSON SCHEMA]
{{
  "matched_program": "{program_context.get('title')}",
  "campus": "{program_context.get('campuses')}",
  "questions": [
    {{
      "id": 1,
      "dimension": "MQF C1-C3: Cognitive & Practical",
      "category": "Cognitive Skills",
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


def extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
    """Safely extracts and parses JSON from an LLM response string."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        # Locate the outermost JSON object braces if extra text was included
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
    return None


async def call_openai_cloud(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls OpenAI Cloud API (Automatically used when OPENAI_API_KEY is configured in .env).
    """
    if not OPENAI_API_KEY:
        return None

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a specialized JSON-only generator for psychometric academic assessments. Output strictly valid JSON."
            },
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                parsed = extract_json_payload(content)
                if parsed and "questions" in parsed and len(parsed["questions"]) > 0:
                    parsed["_model_used"] = OPENAI_MODEL
                    print(f"✅ [AI Assessment] Generated 10 MCQs via OpenAI Cloud (Model: {OPENAI_MODEL})")
                    return parsed
            else:
                logger.warning(f"OpenAI Cloud ({OPENAI_MODEL}) returned {response.status_code}: {response.text[:120]}")
        except Exception as e:
            logger.error(f"Error calling OpenAI Cloud: {e}")

    return None


async def call_gemma_cloud(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls the free-tier Gemma 4 (31B) Cloud model (gemma-4-31b-it) via Google Cloud API.
    """
    if not GEMINI_API_KEY:
        return None

    cloud_models = list(dict.fromkeys([GEMMA_CLOUD_MODEL, "gemma-4-31b-it", "gemma-4-26b-a4b-it", "gemini-2.5-flash"]))

    async with httpx.AsyncClient(timeout=45.0) as client:
        for model in cloud_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            gen_config: Dict[str, Any] = {"temperature": 0.4}
            # gemini-* models support native JSON MIME type enforcement
            if model.startswith("gemini-"):
                gen_config["responseMimeType"] = "application/json"

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": gen_config
            }

            try:
                response = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
                if response.status_code == 200:
                    candidates = response.json().get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        raw_text = "".join(p.get("text", "") for p in parts)
                        parsed = extract_json_payload(raw_text)
                        if parsed and "questions" in parsed and len(parsed["questions"]) > 0:
                            parsed["_model_used"] = model
                            print(f"✅ [AI Assessment] Generated 10 MCQs via Cloud Model: {model}")
                            return parsed
                else:
                    logger.warning(f"Cloud Model ({model}) returned {response.status_code}: {response.text[:120]}")
            except Exception as e:
                logger.error(f"Error calling Cloud Model ({model}): {e}")

    return None


async def call_ollama_cloud(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls the Ollama Cloud chat API (https://api.ollama.com/api/chat).
    """
    if not OLLAMA_API_KEY:
        return None

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json"
    }

    models_to_try = list(dict.fromkeys([OLLAMA_MODEL, "gemma4:31b"]))

    async with httpx.AsyncClient(timeout=35.0) as client:
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
                    parsed = extract_json_payload(raw_content)
                    if parsed and "questions" in parsed and len(parsed["questions"]) > 0:
                        parsed["_model_used"] = model
                        print(f"✅ [AI Assessment] Generated 10 MCQs via Ollama Cloud (Model: {model})")
                        return parsed
                elif response.status_code == 402:
                    logger.info(f"Ollama Cloud ({model}) quota reached (402). Switching immediately to Free Cloud Gemma 4 ({GEMMA_CLOUD_MODEL})...")
                    break
                else:
                    logger.warning(f"Ollama Cloud ({model}) returned {response.status_code}: {response.text[:120]}")
            except Exception as e:
                logger.error(f"Error calling Ollama Cloud with {model}: {e}")
                break

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
    RAG Orchestration Pipeline (Strictly Cloud-Only):
    1. Query ChromaDB for the matching UniKL programme.
    2. Extract context and construct prompt incorporating declared interests.
    3. Call Cloud LLM to generate 10 MCQs:
       - Priority 1: OpenAI Cloud (if OPENAI_API_KEY is set in backend/.env)
       - Priority 2: Free Cloud Gemma 4 31B (gemma-4-31b-it via GEMINI_API_KEY)
       - Priority 3: Ollama Cloud (gemma4:31b via OLLAMA_API_KEY)
    4. Fall back to structured baseline questions if offline.
    """
    # 1. Retrieve ChromaDB context
    program_context = retrieve_program_context(interests)

    # 2. Build prompt
    prompt = build_assessment_prompt(interests, program_context)

    # 3. Call Cloud LLM Providers (OpenAI Cloud -> Free Cloud Gemma 4 31B -> Ollama Cloud)
    ai_response = None
    source = "RAG_CONTEXT_ENHANCED_FALLBACK"

    if OPENAI_API_KEY:
        ai_response = await call_openai_cloud(prompt)
        if ai_response:
            source = "OPENAI_CLOUD_RAG"

    if not ai_response and GEMINI_API_KEY:
        ai_response = await call_gemma_cloud(prompt)
        if ai_response:
            source = "GEMMA_4_31B_CLOUD_RAG"

    if not ai_response and OLLAMA_API_KEY:
        ai_response = await call_ollama_cloud(prompt)
        if ai_response:
            source = "OLLAMA_CLOUD_RAG"

    if ai_response and "questions" in ai_response and len(ai_response["questions"]) >= 5:
        questions = ai_response["questions"][:10]
        model_used = ai_response.get("_model_used", "unknown")
    else:
        fallback = get_static_fallback_questions(interests, program_context)
        questions = fallback["questions"]
        source = "RAG_CONTEXT_ENHANCED_FALLBACK"
        model_used = "static_fallback"
        print("⚠️ [AI Assessment] Using static fallback questions (Cloud API unreachable)")

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
        "model_used": model_used,
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