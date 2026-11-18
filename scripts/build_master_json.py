import csv
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PROGS_CSV = ROOT_DIR / "scripts" / "unikl_programmes.csv"
LINKS_CSV = ROOT_DIR / "scripts" / "foundation_and_diploma_online_course_links.csv"
REQ_DOCX = ROOT_DIR / "scripts" / "entry_requirements.docx"
OUTPUT_JSON = ROOT_DIR / "frontend" / "src" / "assets" / "unikl_foundation_testplan.json"

# ==============================================================================
# SPM GRADING DEFINITIONS (Malaysian Examination Standard)
# - Credit (Kepujian): Grade C or better -> ["A+", "A", "A-", "B+", "B", "C+", "C"]
# - Pass (Lulus):      Grade E or better -> ["A+", "A", "A-", "B+", "B", "C+", "C", "D", "E"]
# - Fail (Gagal):      Grade G
# ==============================================================================
CREDIT_GRADES = ["A+", "A", "A-", "B+", "B", "C+", "C"]
PASS_GRADES = ["A+", "A", "A-", "B+", "B", "C+", "C", "D", "E"]

# Normalize title mismatches between the CSV/DOCX files
TITLE_ALIASES = {
    "Foundation in Medical Science - MBBS": "Foundation in Medical Sciences - (MBBS)",
    "Foundation in Medical Science - (MBBS)": "Foundation in Medical Sciences - (MBBS)",
    "Foundation in Medical Science - Pharmacy": "Foundation in Medical Sciences - (Bachelor of Pharmacy)",
    "Foundation in Medical Science - (Bachelor of Pharmacy)": "Foundation in Medical Sciences - (Bachelor of Pharmacy)",
}

# Detailed metadata and official UniKL entry requirements derived from entry_requirements.docx
PROGRAM_CONFIG = {
    "Foundation in Science and Technology": {
        "program_id": "unikl_midi_foundation_science_tech",
        "major_category": "Science & Engineering Technology",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 5,
        "min_math_grade": "C",   # Credit in Mathematics (C or better)
        "min_bm_grade": "E",     # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",     # Pass in English (E or better)
        "requires_science": True, # Two (2) science subjects (Credit: C or better)
        "min_requirements_text": "Pass in SPM/SPMV with at least five (5) credits including Mathematics and two (2) science subjects, with a pass in Bahasa Melayu and English;",
        "knowledge_context": "Covers engineering mathematics, general chemistry, applied physics, and introductory computer technology to prepare students for engineering and technical bachelor degree programmes.",
        "alternative_pathway_ids": ["unikl_bmi_diploma_electrical_electronics", "unikl_msi_diploma_mechanical_design"]
    },
    "Foundation in Creative Art and Design": {
        "program_id": "unikl_midi_foundation_creative_art_design",
        "major_category": "Creative Arts, Design & Multimedia",
        "pathway_category": "Creative, Arts, Design & Multimedia",
        "min_spm_credits": 5,
        "min_math_grade": "NONE", # Minimum 5 credits in any subjects
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass Sijil Pelajaran Malaysia (SPM) with minimum 5 credits;",
        "knowledge_context": "Explores creative design thinking, elements and principles of visual design, storyboarding, and artistic composition for progression into multimedia, animation, and industrial design degrees.",
        "alternative_pathway_ids": ["unikl_miit_diploma_multimedia", "unikl_miit_diploma_animation"]
    },
    "Foundation in Computer Technology": {
        "program_id": "unikl_miit_foundation_computer",
        "major_category": "Information Technology & Computing",
        "pathway_category": "Computing & Digital Technology",
        "min_spm_credits": 5,
        "min_math_grade": "NONE", # Per entry_requirements.docx: Pass SPM with minimum 5 credits
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass Sijil Pelajaran Malaysia (SPM) with minimum 5 credits;",
        "knowledge_context": "Introduces programming logic, computational thinking, discrete structures, and fundamental computer systems architecture. Designed for transition into software engineering, cybersecurity, and data science majors.",
        "alternative_pathway_ids": ["unikl_miit_diploma_it", "unikl_miit_diploma_networking"]
    },
    "Foundation in Business": {
        "program_id": "unikl_bis_foundation_business",
        "major_category": "Business, Management & Logistics",
        "pathway_category": "Business Management & Logistics",
        "min_spm_credits": 5,
        "min_math_grade": "NONE", # Minimum 5 credits in any subjects
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass Sijil Pelajaran Malaysia (SPM) with minimum 5 credits;",
        "knowledge_context": "Emphasizes core principles of management, basic accounting, business mathematics, microeconomics, and organizational behavior. Prepares candidates for bachelor pathways in international business, accounting, and supply chain.",
        "alternative_pathway_ids": ["unikl_mitec_diploma_industrial_logistics", "unikl_mimet_diploma_maritime_management"]
    },
    "Foundation in Medical Sciences - (MBBS)": {
        "program_id": "unikl_rcmp_foundation_medical_mbbs",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "B",    # At least Grade B in Math or Add Math
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # At least Grade B in Physics, Chemistry, Biology
        "min_requirements_text": "Pass SPM / SPMV / O-level with at least grade B in subjects inclusive: Mathematics or Additional Mathematics, Physics, Chemistry, Biology, one (1) other subjects",
        "knowledge_context": "Rigorous pre-medical preparation covering human biology, organic and inorganic chemistry, foundation biochemistry, and medical sciences for entry into the Bachelor of Medicine and Bachelor of Surgery (MBBS).",
        "alternative_pathway_ids": ["unikl_mestech_diploma_medical_health_sciences", "unikl_rcmp_diploma_nursing"]
    },
    "Foundation in Medical Sciences - (Bachelor of Pharmacy)": {
        "program_id": "unikl_rcmp_foundation_medical_pharmacy",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "B",    # At least Grade B in Math or Add Math
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # At least Grade B in Physics, Chemistry, Biology
        "min_requirements_text": "Pass SPM / SPMV / O-level with at least grade B in subjects inclusive: Mathematics or Additional Mathematics, Physics, Chemistry, Biology, one (1) other subjects",
        "knowledge_context": "Focuses on pharmaceutical chemistry fundamentals, cellular biology, and biochemistry foundations required for progression into the Bachelor of Pharmacy (Hons) programme.",
        "alternative_pathway_ids": ["unikl_rcmp_diploma_pharmacy", "unikl_mestech_diploma_medical_lab_tech"]
    },
    "Foundation in Science": {
        "program_id": "unikl_micet_foundation_science",
        "major_category": "Chemical, Bioengineering & Pure Sciences",
        "pathway_category": "Chemical & Food Technology",
        "min_spm_credits": 5,
        "min_math_grade": "NONE", # Per entry_requirements.docx: Pass SPM with minimum 5 credits
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass Sijil Pelajaran Malaysia (SPM) with minimum 5 credits;",
        "knowledge_context": "Provides comprehensive grounding in biology, algebra, calculus, physics, and laboratory sciences tailored for chemical engineering, food technology, and applied science degrees.",
        "alternative_pathway_ids": ["unikl_micet_diploma_chemical_engineering", "unikl_micet_diploma_chemical_food"]
    },
    "Foundation in Science and Arts": {
        "program_id": "unikl_msi_foundation_science_arts",
        "major_category": "Multidisciplinary Science & Management",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better) across all 4 pathways
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False, # Science required for Eng/Sci pathways, optional for Arts/IT/Business pathway
        "min_requirements_text": "Engineering Programme (Bachelor) Pathway: Pass SPM / SPMV / O-Level with at least credits in FIVE (5) subjects including Mathematics and 1 Physical Science subject. | Engineering Technology Programme (Bachelor) Pathway: Pass SPM / SPMV / O-Level with at least credits in FIVE (5) subjects including Mathematics and 1 Science / Technical / Vocational subject. | Science Programme (Bachelor) Pathway: Pass SPM / SPMV / O-Level with at least credits in FIVE (5) subjects including Mathematics and 2 Science subjects. | Arts / IT / Business Programme (Bachelor) Pathway: Pass SPM / SPMV / O-Level with at least credits in FIVE (5) subjects including Mathematics.",
        "knowledge_context": "Combines foundational management, information and communication technology (ICT), economics, and applied sciences to offer flexible progression into technology management or engineering technology degrees.",
        "alternative_pathway_ids": ["unikl_msi_diploma_industrial_automation", "unikl_mitec_diploma_industrial_logistics"]
    },
    "Foundation in Arts": {
        "program_id": "unikl_bmi_foundation_arts",
        "major_category": "Business, Humanities & Social Sciences",
        "pathway_category": "Business Management & Logistics",
        "min_spm_credits": 5,
        "min_math_grade": "NONE", # Minimum 5 credits in any subjects
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass Sijil Pelajaran Malaysia (SPM) with minimum 5 credits;",
        "knowledge_context": "Covers introduction to management, essentials of business law, basic ICT, and communication skills for students pursuing degrees in business, management, logistics, or humanities.",
        "alternative_pathway_ids": ["unikl_mitec_diploma_industrial_logistics", "unikl_miit_diploma_multimedia"]
    },
    "Foundation in Science and Technology for Korean University - Engineering": {
        "program_id": "unikl_miit_foundation_korean_engineering",
        "major_category": "International Engineering & Computing",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Two (2) science subjects (Credit: C or better)
        "min_requirements_text": "Pass in SPM/SPMV with at least five (5) credits including Mathematics and two (2) science subjects, with a pass in Bahasa Melayu and English;",
        "knowledge_context": "Specialized engineering preparatory pathway featuring intensive Korean language proficiency, engineering calculus, object-oriented programming, and computer hardware maintenance for degree studies at partner South Korean universities.",
        "alternative_pathway_ids": ["unikl_miit_diploma_it", "unikl_bmi_diploma_electrical_electronics"]
    },
    "Diploma in Information Technology": {
        "program_id": "unikl_miit_diploma_it",
        "major_category": "Information Technology & Computing",
        "pathway_category": "Computing & Digital Technology",
        "min_spm_credits": 3,
        "min_math_grade": "NONE", # Minimum 3 credits in any subject
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass SPM or its equivalent with a minimum of three (3) credits in any subject",
        "knowledge_context": "Equips students with hands-on skills in fundamentals of programming, computer networking, object-oriented system analysis and design, and data structures for software development roles.",
        "alternative_pathway_ids": ["unikl_miit_diploma_networking", "unikl_miit_diploma_multimedia"]
    },
    "Diploma in Multimedia": {
        "program_id": "unikl_miit_diploma_multimedia",
        "major_category": "Creative Arts, Design & Multimedia",
        "pathway_category": "Creative, Arts, Design & Multimedia",
        "min_spm_credits": 3,
        "min_math_grade": "NONE", # Minimum 3 credits in any subject
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass SPM or its equivalent with a minimum of three (3) credits in any subject",
        "knowledge_context": "Trains students in basic graphic design, interactive multimedia development, storyboard concepts, digital audio-visual production, and 2D/3D digital animation.",
        "alternative_pathway_ids": ["unikl_miit_diploma_animation", "unikl_miit_diploma_it"]
    },
    "Diploma in Animation": {
        "program_id": "unikl_miit_diploma_animation",
        "major_category": "Creative Arts, Design & Multimedia",
        "pathway_category": "Creative, Arts, Design & Multimedia",
        "min_spm_credits": 3,
        "min_math_grade": "NONE", # Minimum 3 credits in any subject
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass SPM or its equivalent with a minimum of three (3) credits in any subject",
        "knowledge_context": "Focuses on introduction to multimedia, animation principles and timing, character visualization and design, digital sculpting, and visual storytelling for creative studios.",
        "alternative_pathway_ids": ["unikl_miit_diploma_multimedia"]
    },
    "Diploma in Networking Technology": {
        "program_id": "unikl_miit_diploma_networking",
        "major_category": "Information Technology & Computing",
        "pathway_category": "Computing & Digital Technology",
        "min_spm_credits": 3,
        "min_math_grade": "NONE", # Minimum 3 credits in any subject
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass SPM or its equivalent with a minimum of three (3) credits in any subject",
        "knowledge_context": "Covers fundamentals of programming, computer network architectures, electrical circuit analysis, and Cisco routing and switching essentials for network infrastructure and cybersecurity careers.",
        "alternative_pathway_ids": ["unikl_miit_diploma_it", "unikl_bmi_diploma_electrical_electronics"]
    },
    "Diploma of Electrical and Electronics Engineering Technology": {
        "program_id": "unikl_bmi_diploma_electrical_electronics",
        "major_category": "Electrical & Electronics Engineering",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in Natural Sciences or Technical Based Subjects (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with at least credits (minimum Grade C and higher) in Mathematics and Natural Sciences or Technical Based Subjects;",
        "knowledge_context": "Provides practical training in engineering physics, electrical and electronics workshop practices, analog and digital electronics, and electrical circuit analysis.",
        "alternative_pathway_ids": ["unikl_msi_diploma_industrial_automation", "unikl_mimet_diploma_marine_electrical"]
    },
    "Diploma of Engineering Technology in Welding": {
        "program_id": "unikl_mfi_diploma_welding",
        "major_category": "Mechanical & Manufacturing Engineering",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in Natural Sciences or Technical Based Subjects (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with at least credits (minimum Grade C and higher) in Mathematics and Natural Sciences or Technical Based Subjects;",
        "knowledge_context": "Covers industrial welding processes, metallurgy, welding joint design, symbols and blueprint reading, quality inspection, and fabrication safety standards.",
        "alternative_pathway_ids": ["unikl_msi_diploma_mechanical_design", "unikl_mimet_diploma_naval_architecture"]
    },
    "Diploma of Engineering Technology in Automotive Maintenance": {
        "program_id": "unikl_mfi_diploma_automotive_maintenance",
        "major_category": "Automotive, Aviation & Transportation",
        "pathway_category": "Aviation, Automotive & Transportation",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in Natural Sciences or Technical Based Subjects (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with at least credits (minimum Grade C and higher) in Mathematics and Natural Sciences or Technical Based Subjects;",
        "knowledge_context": "Delivers hands-on competency in internal combustion engine fundamentals, modern engine technology, autotronics, vehicle diagnostics, and automotive air-conditioning systems.",
        "alternative_pathway_ids": ["unikl_midi_diploma_railway_system", "unikl_msi_diploma_mechanical_design"]
    },
    "Diploma of Engineering Technology in Avionics Maintenance": {
        "program_id": "unikl_miat_diploma_avionics_maintenance",
        "major_category": "Automotive, Aviation & Transportation",
        "pathway_category": "Aviation, Automotive & Transportation",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in Natural Sciences or Technical Based Subjects (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with at least credits (minimum Grade C and higher) in Mathematics and Natural Sciences or Technical Based Subjects;",
        "knowledge_context": "Specializes in aviation physics, aircraft structures, flight instruments, aircraft electrical systems, and radar/navigation avionics maintenance compliant with aviation standards.",
        "alternative_pathway_ids": ["unikl_miat_diploma_aeroplane_maintenance", "unikl_bmi_diploma_electrical_electronics"]
    },
    "Diploma of Engineering Technology in Aeroplane Maintenance": {
        "program_id": "unikl_miat_diploma_aeroplane_maintenance",
        "major_category": "Automotive, Aviation & Transportation",
        "pathway_category": "Aviation, Automotive & Transportation",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in Natural Sciences or Technical Based Subjects (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with at least credits (minimum Grade C and higher) in Mathematics and Natural Sciences or Technical Based Subjects;",
        "knowledge_context": "Provides comprehensive training in aerodynamics physics, airframe components and aircraft structures, turbine engine systems, and aircraft instrument maintenance.",
        "alternative_pathway_ids": ["unikl_miat_diploma_avionics_maintenance", "unikl_mfi_diploma_automotive_maintenance"]
    },
    "Diploma of Engineering Technology in Marine Engineering": {
        "program_id": "unikl_mimet_diploma_marine_engineering",
        "major_category": "Marine & Maritime Technology",
        "pathway_category": "Marine & Maritime",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in sciences or technical based subjects (C or better)
        "min_requirements_text": "Sijil Pelajaran Malaysia (SPM) or equivalent with at least credit in three (3) subjects including Mathematics and sciences or technical based subjects.",
        "knowledge_context": "Covers marine engineering propulsion systems, fundamentals of thermodynamics, shipboard electrical and electronics technology, and marine materials structure.",
        "alternative_pathway_ids": ["unikl_mimet_diploma_naval_architecture", "unikl_mimet_diploma_marine_electrical"]
    },
    "Diploma of Engineering Technology in Electrical & Electronics (Marine)": {
        "program_id": "unikl_mimet_diploma_marine_electrical",
        "major_category": "Marine & Maritime Technology",
        "pathway_category": "Marine & Maritime",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in sciences or technical based subjects (C or better)
        "min_requirements_text": "Sijil Pelajaran Malaysia (SPM) or equivalent with at least credit in three (3) subjects including Mathematics and sciences or technical based subjects.",
        "knowledge_context": "Focuses on marine electrical power generation, shipboard electronics, occupational safety and health in shipyard operations, and technical mathematics.",
        "alternative_pathway_ids": ["unikl_mimet_diploma_marine_engineering", "unikl_bmi_diploma_electrical_electronics"]
    },
    "Diploma of Engineering Technology (Naval Architecture and Shipbuilding)": {
        "program_id": "unikl_mimet_diploma_naval_architecture",
        "major_category": "Marine & Maritime Technology",
        "pathway_category": "Marine & Maritime",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in sciences or technical based subjects (C or better)
        "min_requirements_text": "Sijil Pelajaran Malaysia (SPM) or equivalent with at least credit in three (3) subjects including Mathematics and sciences or technical based subjects.",
        "knowledge_context": "Teaches technical mathematics, hull geometry, shipbuilding and vessel maintenance technology, hydrostatics, and marine welding technology.",
        "alternative_pathway_ids": ["unikl_mimet_diploma_marine_engineering", "unikl_mfi_diploma_welding"]
    },
    "Diploma of Engineering Technology in Mechanical Design & Development": {
        "program_id": "unikl_msi_diploma_mechanical_design",
        "major_category": "Mechanical & Manufacturing Engineering",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in sciences or technical based subjects (C or better)
        "min_requirements_text": "Sijil Pelajaran Malaysia (SPM) or equivalent with at least credit in three (3) subjects including Mathematics and sciences or technical based subjects.",
        "knowledge_context": "Develops skills in technical mathematics, CAD engineering drawing, material science, mechanics of machines, and conventional machining processes.",
        "alternative_pathway_ids": ["unikl_msi_diploma_industrial_automation", "unikl_mfi_diploma_welding"]
    },
    "Diploma of Electronic Engineering Technology (Industrial Automation and Control)": {
        "program_id": "unikl_msi_diploma_industrial_automation",
        "major_category": "Electrical, Electronic & Automation Engineering",
        "pathway_category": "Engineering & Technology",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in sciences or technical based subjects (C or better)
        "min_requirements_text": "Sijil Pelajaran Malaysia (SPM) or equivalent with at least credit in three (3) subjects including Mathematics and sciences or technical based subjects.",
        "knowledge_context": "Integrates technical mathematics, engineering science, electrical technology, PLC programming, robotics, and industrial C computing for smart manufacturing.",
        "alternative_pathway_ids": ["unikl_bmi_diploma_electrical_electronics", "unikl_msi_diploma_mechanical_design"]
    },
    "Diploma of Engineering Technology (Railway System)": {
        "program_id": "unikl_midi_diploma_railway_system",
        "major_category": "Automotive, Aviation & Transportation",
        "pathway_category": "Aviation, Automotive & Transportation",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in sciences or technical based subjects (C or better)
        "min_requirements_text": "Sijil Pelajaran Malaysia (SPM) or equivalent with at least credit in three (3) subjects including Mathematics and sciences or technical based subjects.",
        "knowledge_context": "Covers technical mathematics, basic electrical railway traction, rolling stock maintenance, signaling systems, and railway track safety operations.",
        "alternative_pathway_ids": ["unikl_mfi_diploma_automotive_maintenance", "unikl_bmi_diploma_electrical_electronics"]
    },
    "Diploma in Chemical Engineering Technology (Food)": {
        "program_id": "unikl_micet_diploma_chemical_food",
        "major_category": "Chemical & Food Technology",
        "pathway_category": "Chemical & Food Technology",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in natural sciences or technical based subjects (C or better)
        "min_requirements_text": "SPM or equivalent with at least credit in mathematics and, natural sciences or technical based subjects.",
        "knowledge_context": "Combines technical mathematics, organic and analytical chemistry, principles of chemical processes, food safety, and engineering drawing for food manufacturing.",
        "alternative_pathway_ids": ["unikl_micet_diploma_chemical_engineering"]
    },
    "Diploma in Chemical Engineering Technology": {
        "program_id": "unikl_micet_diploma_chemical_engineering",
        "major_category": "Chemical & Food Technology",
        "pathway_category": "Chemical & Food Technology",
        "min_spm_credits": 3,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": True, # Credit in natural sciences or technical based subjects (C or better)
        "min_requirements_text": "SPM or equivalent with at least credit in mathematics and, natural sciences or technical based subjects.",
        "knowledge_context": "Focuses on general chemistry, technical mathematics, organic and analytical chemistry, electrical technology, and chemical plant unit operations.",
        "alternative_pathway_ids": ["unikl_micet_diploma_chemical_food"]
    },
    "Diploma in Maritime Management": {
        "program_id": "unikl_mimet_diploma_maritime_management",
        "major_category": "Marine & Maritime Operations",
        "pathway_category": "Marine & Maritime",
        "min_spm_credits": 3,
        "min_math_grade": "NONE", # Minimum 3 credits in any subject
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass SPM or its equivalent with a minimum of three (3) credits in any subject",
        "knowledge_context": "Covers introduction to maritime operations, maritime economics, principles of shipping, port and terminal management, and international freight logistics.",
        "alternative_pathway_ids": ["unikl_mitec_diploma_industrial_logistics"]
    },
    "Diploma in Industrial Logistics": {
        "program_id": "unikl_mitec_diploma_industrial_logistics",
        "major_category": "Business, Management & Logistics",
        "pathway_category": "Business Management & Logistics",
        "min_spm_credits": 3,
        "min_math_grade": "NONE", # Minimum 3 credits in any subject
        "min_bm_grade": "E",      # Pass SPM (E or better)
        "min_bi_grade": "E",      # Pass grade (E or better)
        "requires_science": False,
        "min_requirements_text": "Pass SPM or its equivalent with a minimum of three (3) credits in any subject",
        "knowledge_context": "Trains students in basic statistics, fundamentals of logistics and supply chain management, warehouse inventory control, procurement, and principles of economics.",
        "alternative_pathway_ids": ["unikl_mimet_diploma_maritime_management"]
    },
    "Diploma in Pharmacy": {
        "program_id": "unikl_rcmp_diploma_pharmacy",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Credit in 1 Science subject (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with pass in Bahasa Melayu and English and five (5) credits in the following subjects: Mathematics, one (1) Science subject (Biology, Chemistry, Physics, General Science/Applied Science) and any other three (3) subjects including Bahasa Melayu and/or English;",
        "knowledge_context": "Covers introduction to pharmaceutics, pharmacology, human physiology, hospital and community dispensing practices, and pharmaceutical chemistry.",
        "alternative_pathway_ids": ["unikl_mestech_diploma_medical_lab_tech", "unikl_mestech_diploma_medical_health_sciences"]
    },
    "Diploma in Physiotherapy": {
        "program_id": "unikl_rcmp_diploma_physiotherapy",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Credit in 1 Science subject (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with pass in Bahasa Melayu and English and five (5) credits in the following subjects: Mathematics, one (1) Science subject (Biology, Chemistry, Physics, General Science/Applied Science) and any other three (3) subjects including Bahasa Melayu and/or English;",
        "knowledge_context": "Focuses on basic human anatomy and physiology, kinesiology and biomechanics, musculoskeletal rehabilitation, electrotherapy, and clinical patient care.",
        "alternative_pathway_ids": ["unikl_rcmp_diploma_nursing", "unikl_mestech_diploma_medical_health_sciences"]
    },
    "Diploma in Nursing": {
        "program_id": "unikl_rcmp_diploma_nursing",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Credit in 1 Science subject (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with pass in Bahasa Melayu and English and five (5) credits in the following subjects: Mathematics, one (1) Science subject (Biology, Chemistry, Physics, General Science/Applied Science) and any other three (3) subjects including Bahasa Melayu and/or English;",
        "knowledge_context": "Provides clinical training in human anatomy and physiology, principles of nursing care, basic pharmacology, medical-surgical nursing, and patient safety.",
        "alternative_pathway_ids": ["unikl_rcmp_diploma_physiotherapy", "unikl_mestech_diploma_medical_health_sciences"]
    },
    "Diploma in Medical Imaging": {
        "program_id": "unikl_rcmp_diploma_medical_imaging",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Credit in 1 Science subject (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with pass in Bahasa Melayu and English and five (5) credits in the following subjects: Mathematics, one (1) Science subject (Biology, Chemistry, Physics, General Science/Applied Science) and any other three (3) subjects including Bahasa Melayu and/or English;",
        "knowledge_context": "Covers fundamental radiation physics for radiographers, pathology, occupational safety and health, human anatomy and physiology, and diagnostic X-ray/CT imaging techniques.",
        "alternative_pathway_ids": ["unikl_mestech_diploma_medical_lab_tech", "unikl_rcmp_diploma_physiotherapy"]
    },
    "Diploma of Medical Laboratory Technology": {
        "program_id": "unikl_mestech_diploma_medical_lab_tech",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Credit in 1 Science subject (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with pass in Bahasa Melayu and English and five (5) credits in the following subjects: Mathematics, one (1) Science subject (Biology, Chemistry, Physics, General Science/Applied Science) and any other three (3) subjects including Bahasa Melayu and/or English;",
        "knowledge_context": "Trains students in basic microbiology, clinical biochemistry, human anatomy and physiology, hematology, and diagnostic pathology laboratory analysis.",
        "alternative_pathway_ids": ["unikl_rcmp_diploma_pharmacy", "unikl_mestech_diploma_medical_health_sciences"]
    },
    "Diploma in Medical and Health Sciences": {
        "program_id": "unikl_mestech_diploma_medical_health_sciences",
        "major_category": "Health & Medical Sciences",
        "pathway_category": "Health & Medical Sciences",
        "min_spm_credits": 5,
        "min_math_grade": "C",    # Credit in Mathematics (C or better)
        "min_bm_grade": "E",      # Pass in Bahasa Melayu (E or better)
        "min_bi_grade": "E",      # Pass in English (E or better)
        "requires_science": True, # Credit in 1 Science subject (C or better)
        "min_requirements_text": "Pass in SPM or its equivalent with pass in Bahasa Melayu and English and five (5) credits in the following subjects: Mathematics, one (1) Science subject (Biology, Chemistry, Physics, General Science/Applied Science) and any other three (3) subjects including Bahasa Melayu and/or English;",
        "knowledge_context": "Prepares assistant medical officers in operation theatre procedures, human anatomy and physiology, emergency medicine, trauma care, and community clinical health.",
        "alternative_pathway_ids": ["unikl_rcmp_diploma_nursing", "unikl_rcmp_diploma_physiotherapy"]
    }
}


def parse_docx_requirements(docx_path: Path, known_titles: set) -> dict:
    """
    Directly parses scripts/entry_requirements.docx so any text updates
    in the Word document are automatically reflected.
    """
    if not docx_path.exists():
        return {}

    with zipfile.ZipFile(docx_path) as z:
        xml_content = z.read("word/document.xml")
    tree = ET.fromstring(xml_content)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    lines = []
    for p in tree.findall(".//w:p", ns):
        texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
        line = "".join(texts).strip()
        if line and line.lower() != "min requirements:":
            lines.append(line)

    reqs_by_title = {}
    current_title = None
    for line in lines:
        norm = TITLE_ALIASES.get(line, line)
        if norm in known_titles:
            current_title = norm
            reqs_by_title[current_title] = []
        elif current_title:
            reqs_by_title[current_title].append(line)

    return {k: " | ".join(v) for k, v in reqs_by_title.items() if v}


def build_master_json():
    # 1. Load all 118 course links grouped by normalized programme title
    courses_by_title = {}
    total_links = 0

    with open(LINKS_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_title = row.get("Title", "").strip()
            if not raw_title:
                continue
            norm_title = TITLE_ALIASES.get(raw_title, raw_title)
            platform = row.get("Platform", "").strip()
            subject = row.get("Subject Names", "").strip()
            link = row.get("Online Link (URL)", "").strip()

            courses_by_title.setdefault(norm_title, []).append({
                "title": f"{subject} ({platform})",
                "platform": platform,
                "subject": subject,
                "link": link
            })
            total_links += 1

    # 2. Parse official requirement texts directly from entry_requirements.docx
    docx_reqs = parse_docx_requirements(REQ_DOCX, set(PROGRAM_CONFIG.keys()))

    # 3. Read all 35 programmes from unikl_programmes.csv and merge
    master_list = []
    matched_titles = set()

    with open(PROGS_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "").strip()
            if not title:
                continue

            cfg = PROGRAM_CONFIG.get(title)
            if not cfg:
                raise ValueError(f"Missing config for programme: {title}")

            guidelines = courses_by_title.get(title, [])
            if not guidelines:
                print(f"⚠️ Warning: No online courses found for '{title}'")
            else:
                matched_titles.add(title)

            min_req_text = docx_reqs.get(title, cfg["min_requirements_text"])

            prog_obj = {
                "program_id": cfg["program_id"],
                "title": title,
                "level": row.get("level", "").strip(),
                "campuses": row.get("campuses", "").strip(),
                "major_category": cfg["major_category"],
                "pathway_category": cfg["pathway_category"],
                "specialisation": row.get("specialisation", "").strip(),
                "min_spm_credits": cfg["min_spm_credits"],
                "min_math_grade": cfg["min_math_grade"],
                "min_bm_grade": cfg["min_bm_grade"],
                "min_bi_grade": cfg["min_bi_grade"],
                "requires_science": cfg["requires_science"],
                "min_requirements_text": min_req_text,
                "short_description": row.get("short_description", "").strip(),
                "knowledge_context": cfg["knowledge_context"],
                "link": row.get("link", "").strip(),
                "alternative_pathway_ids": cfg["alternative_pathway_ids"],
                "preparatory_guideline": guidelines
            }
            master_list.append(prog_obj)

    # Check if any course titles in LINKS_CSV were not matched
    unmatched = set(courses_by_title.keys()) - matched_titles
    if unmatched:
        print(f"⚠️ Unmatched course titles: {unmatched}")

    # Write to frontend/src/assets/unikl_foundation_testplan.json
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(master_list, f, indent=2, ensure_ascii=False)

    print(f"✅ Successfully built {OUTPUT_JSON}")
    print(f"📄 Parsed {len(docx_reqs)} / 35 entry requirements directly from {REQ_DOCX.name}")
    print(f"📊 Total Programmes: {len(master_list)} (Foundation: {sum(1 for p in master_list if p['level']=='Foundation')}, Diploma: {sum(1 for p in master_list if p['level']=='Diploma')})")
    print(f"🔗 Total Online Course Links Merged: {sum(len(p['preparatory_guideline']) for p in master_list)} / {total_links}")


if __name__ == "__main__":
    build_master_json()
