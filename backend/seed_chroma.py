# backend/seed_chroma.py
import os
import json
import csv
from pathlib import Path
from core.chroma import get_chroma_client, get_program_collection, COLLECTION_NAME, CHROMA_DATA_PATH

# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent

# Data File Paths
JSON_DATA_PATH = ROOT_DIR / "frontend" / "src" / "assets" / "unikl_foundation_testplan.json"
CSV_DATA_PATH = ROOT_DIR / "scripts" / "unikl_programmes.csv"


def create_program_document(program: dict) -> str:
    """
    Constructs a rich text document for embedding.
    Combines academic metadata, overview, knowledge context, and requirements
    to maximize semantic retrieval accuracy.
    """
    parts = [
        f"Program Title: {program.get('title', '')}",
        f"Study Level: {program.get('level', '')}",
        f"Campus: {program.get('campuses', '')}",
        f"Major Category: {program.get('major_category', '')}",
        f"Pathway Category: {program.get('pathway_category', '')}",
        f"Specialisation: {program.get('specialisation', '')}",
        f"Overview: {program.get('short_description', '')}",
    ]

    knowledge = program.get("knowledge_context")
    if knowledge:
        parts.append(f"Knowledge & Skills: {knowledge}")

    min_reqs = program.get("min_requirements_text")
    if min_reqs:
        parts.append(f"Entry Requirements: {min_reqs}")

    return "\n".join(part for part in parts if part)


def sanitize_metadata(program: dict, program_id: str) -> dict:
    """
    Ensures all metadata fields conform to ChromaDB's allowed types:
    str, int, float, or bool. Complex structures are serialized to JSON strings.
    """
    metadata = {
        "program_id": str(program_id),
        "title": str(program.get("title", "")),
        "level": str(program.get("level", "")),
        "campuses": str(program.get("campuses", "")),
        "major_category": str(program.get("major_category", "")),
        "pathway_category": str(program.get("pathway_category", "")),
        "specialisation": str(program.get("specialisation", "")),
        "min_spm_credits": int(program.get("min_spm_credits", 0)),
        "min_math_grade": str(program.get("min_math_grade", "")),
        "min_bm_grade": str(program.get("min_bm_grade", "")),
        "min_bi_grade": str(program.get("min_bi_grade", "")),
        "requires_science": bool(program.get("requires_science", False)),
        "link": str(program.get("link", ""))
    }

    # Serialize complex array fields to JSON strings
    if "alternative_pathway_ids" in program:
        metadata["alternative_pathway_ids"] = json.dumps(program["alternative_pathway_ids"])
    if "preparatory_guideline" in program:
        metadata["preparatory_guideline"] = json.dumps(program["preparatory_guideline"])

    return metadata


def load_programs_from_json(file_path: Path) -> list:
    """Loads detailed programmes from JSON."""
    if not file_path.exists():
        print(f"⚠️ JSON file not found at: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        print(f"📖 Loaded {len(data)} programme(s) from JSON ({file_path.name})")
        return data


def load_programs_from_csv(file_path: Path, existing_ids: set, existing_titles: set) -> list:
    """
    Loads supplementary programmes from CSV for any programmes
    not already defined in the JSON file.
    """
    if not file_path.exists():
        return []

    supplementary = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "").strip()
            if not title:
                continue

            # Generate a normalized program_id slug
            clean_title = title.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace("__", "_")
            prog_id = f"unikl_{clean_title}"

            if prog_id in existing_ids or title in existing_titles:
                continue

            supplementary.append({
                "program_id": prog_id,
                "title": title,
                "level": row.get("level", ""),
                "campuses": row.get("campuses", ""),
                "major_category": row.get("specialisation", ""),
                "pathway_category": row.get("specialisation", ""),
                "specialisation": row.get("specialisation", ""),
                "min_spm_credits": 3 if row.get("level") == "Diploma" else 5,
                "min_math_grade": "C",
                "min_bm_grade": "C",
                "min_bi_grade": "C",
                "requires_science": False,
                "min_requirements_text": f"Pass SPM for {row.get('level', 'Diploma')}",
                "short_description": row.get("short_description", ""),
                "knowledge_context": row.get("short_description", ""),
                "link": row.get("link", "")
            })

    if supplementary:
        print(f"📖 Loaded {len(supplementary)} additional programme(s) from CSV ({file_path.name})")
    return supplementary


def seed_chroma(include_csv: bool = True):
    """
    Main seeding routine:
    1. Connects to persistent ChromaDB at backend/chroma_db.
    2. Loads programmes from unikl_foundation_testplan.json.
    3. Optionally supplements with additional programmes from unikl_programmes.csv.
    4. Upserts all documents, embeddings, and metadata into ChromaDB.
    5. Runs a test search to verify the collection.
    """
    print("=" * 60)
    print("🚀 Initializing ChromaDB Seeder for Route2UniKL...")
    print(f"📁 Database Path: {CHROMA_DATA_PATH}")
    print("=" * 60)

    collection = get_program_collection()

    # 1. Load primary JSON programmes
    json_programs = load_programs_from_json(JSON_DATA_PATH)
    all_programs = list(json_programs)
    existing_ids = {p.get("program_id") for p in json_programs if p.get("program_id")}
    existing_titles = {p.get("title") for p in json_programs if p.get("title")}

    # 2. Optionally load supplementary CSV programmes
    if include_csv:
        csv_programs = load_programs_from_csv(CSV_DATA_PATH, existing_ids, existing_titles)
        all_programs.extend(csv_programs)

    if not all_programs:
        print("❌ No programmes found to seed.")
        return

    # 3. Prepare data lists for ChromaDB batch upsert
    ids = []
    documents = []
    metadatas = []

    for prog in all_programs:
        prog_id = prog.get("program_id")
        if not prog_id:
            continue

        doc_text = create_program_document(prog)
        metadata = sanitize_metadata(prog, prog_id)

        ids.append(prog_id)
        documents.append(doc_text)
        metadatas.append(metadata)

    # 4. Upsert into ChromaDB
    print(f"\n📦 Upserting {len(ids)} programmes into collection '{COLLECTION_NAME}'...")
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )

    print(f"✅ Successfully seeded {collection.count()} total programmes in ChromaDB!")

    # 5. Run verification similarity query
    print("\n🔍 Running verification test search...")
    sample_queries = [
        "I love software development, coding and cybersecurity",
        "Business management, finance, accounting and marketing"
    ]

    for query in sample_queries:
        results = collection.query(
            query_texts=[query],
            n_results=1
        )
        matched_id = results["ids"][0][0] if results["ids"] and results["ids"][0] else "N/A"
        matched_meta = results["metadatas"][0][0] if results["metadatas"] and results["metadatas"][0] else {}
        matched_dist = results["distances"][0][0] if "distances" in results and results["distances"] else 0.0

        print(f"\n  Query: \"{query}\"")
        print(f"  → Best Match: {matched_meta.get('title')} (ID: {matched_id})")
        print(f"  → Campus: {matched_meta.get('campuses')} | Distance: {matched_dist:.4f}")

    print("\n🎉 ChromaDB Seeding and Verification Complete!")
    print("=" * 60)


if __name__ == "__main__":
    seed_chroma(include_csv=True)