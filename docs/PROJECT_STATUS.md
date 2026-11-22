# Route2UniKL — Project Status Baseline

| | |
|---|---|
| Baseline date | 22 November 2026 (MYT) |
| Branch | `feature/admin-module` |
| Baseline commit | `2287868` (M1.5B), in sync with `origin/feature/admin-module` when this baseline was written |
| Last updated | 23 November 2026 (MYT): browser-side Gemini OCR disabled for security; M1.5C **deferred**; frontend provider-secret review; shared grade validation for both grade-entry pages (see [section 5](#ocr-status-m15c-deferred)) |
| Production Firebase project | `route2unikl` |
| Related documents | [CLAUDE.md](../CLAUDE.md) · [FIRESTORE_BASELINE.md](FIRESTORE_BASELINE.md) |

## Evidence labels

Every status claim in this document uses one of these labels.

| Label | Meaning |
|---|---|
| **Repo-verified** | Implementation confirmed by reading the source code in this repository. |
| **Unit tests** | Covered by the mocked FastAPI tests in `backend/tests/test_auth.py`. |
| **Frontend unit tests** | Covered by the Node test-runner tests in `frontend/src/utils/gradeEntry.test.js` (synthetic data; no browser or Firebase). |
| **Emulator tests** | Covered by the Firestore rules suite in `firestore-tests/` (local emulator, `demo-route2unikl`). |
| **Browser smoke test** | Exercised manually in the real app: local React dev server connected to production Firebase. Owner-reported. |
| **Console** | Checked in the Firebase Console. Owner-reported. |
| **Rules Playground** | Simulated in the Firebase Console Rules Playground. A rules simulation, not an application test. Owner-reported. |
| **Untested** | No recorded test. |

## 1. Implemented features

### Student journey

| Feature | Main location | Evidence |
|---|---|---|
| Registration (Email/Password, creates `users/{uid}`) | `frontend/src/pages/auth/Register.jsx` | Repo-verified; Emulator tests (payload); Browser smoke test |
| Login | `frontend/src/pages/auth/Login.jsx` | Repo-verified; Browser smoke test |
| Forgot password | `frontend/src/pages/auth/ForgotPassword.jsx` | Repo-verified; Untested |
| Profile read and name edit | `frontend/src/pages/user/Profile.jsx` | Repo-verified; Emulator tests; Browser smoke test |
| Profile "delete account" | `frontend/src/pages/user/Profile.jsx` | Repo-verified; Emulator tests (rules only); Untested in production |
| Interest selection (profile ingestion) | `frontend/src/pages/user/ProfileIngestion.jsx` | Repo-verified; Emulator tests (payload) |
| Manual grade entry for Form 4/5 → `results/{uid}` | `frontend/src/pages/user/ManualGradeEntry.jsx` | Uses the shared grade validation (below). Repo-verified; Frontend unit tests (validation); Emulator tests (payload) |
| SPM results page for SPM leavers → `results/{uid}` | `frontend/src/pages/user/UploadResults.jsx` | Automatic OCR **disabled** (M1.5C deferred); manual subject and grade entry only, using the shared grade validation (below), saved with the manual-entry values. Repo-verified; Frontend unit tests (validation); Emulator tests (manual-entry payload) |
| Shared grade validation for both grade-entry pages | `frontend/src/utils/gradeEntry.js` | Grades must be A+, A, A-, B+, B, C+, C, D, E or G; partly filled elective rows are rejected and fully empty ones ignored; at most 20 subjects; whitespace trimmed; fresh rows per page visit. Browser-side data quality only: `firestore.rules` does not check individual grades. Repo-verified; Frontend unit tests |
| Academic results saved in production (before OCR was disabled) | — | Browser smoke test + Console (document confirmed). Save method (manual or OCR) not recorded. Browser read-back not independently tested |
| AI assessment (FastAPI RAG) → `ai_assessments/{uid}` | `frontend/src/pages/user/DummyAI.jsx`, `backend/routes/assessment.py`, `backend/services/rag_orchestrator.py` | Repo-verified; Unit tests (auth, static fallback); Emulator tests (payload); Untested in production |
| Recommendations | `frontend/src/pages/user/Recommendation.jsx`, `backend/services/recommendation_service.py` | Repo-verified; Unit tests (auth only); scoring logic Untested |
| Preparation plan (bundled JSON) | `frontend/src/pages/user/PreparationPlan.jsx` | Repo-verified; Untested |
| Programme catalogue (Firestore `programs`, public) | `frontend/src/pages/user/AllPrograms.jsx`, `frontend/src/pages/user/Dashboard.jsx` | Repo-verified; Emulator tests; Browser smoke test |

### Admin and security

| Feature | Main location | Evidence |
|---|---|---|
| Admin route guard for `/admin/dashboard` (browser claim check with forced token refresh) | `frontend/src/components/ProtectedAdminRoute.jsx`, `frontend/src/utils/adminClaims.js` | Repo-verified; Browser smoke test (Admin login, dashboard access, refresh) |
| Login / landing redirect by claim | `frontend/src/pages/auth/Login.jsx`, `frontend/src/pages/LandingPage.jsx` | Repo-verified; Browser smoke test |
| Admin dashboard | `frontend/src/pages/admin/AdminDashboard.jsx` | Placeholder page only |
| FastAPI token verification, `require_admin`, `ensure_same_user`, coded HTTP 503 | `backend/core/auth.py` | Repo-verified; Unit tests |
| `GET /api/auth/me`, `GET /api/admin/verify` | `backend/routes/auth_check.py` | Unit tests; not yet called by the frontend |
| Frontend `authFetch` and auth error panel | `frontend/src/utils/apiClient.js`, `frontend/src/components/ApiAuthErrorPanel.jsx` | Repo-verified |
| Firestore Security Rules | [`firestore.rules`](../firestore.rules) | Emulator tests; deployed to production (owner-reported) |
| Browser "Seed Programs" button removed | `frontend/src/App.jsx` | Repo-verified |

Apart from the shared grade-validation helper, no automated tests exist for the frontend UI,
recommendation scoring, RAG retrieval quality, AI output quality or OCR accuracy.

## 2. Milestone history

| Milestone | Commit | Date (MYT) | Files | Summary |
|---|---|---|---|---|
| Foundation (before the Admin module) | `dca8e2d`, `32902ab` and earlier | before 22 Nov 2026 | — | Student journey, OCR, ChromaDB RAG assessment, 35-programme dataset, recommendation engine, preparation plan |
| M1 — Admin Authentication & RBAC | `677728f` | 22 Nov 2026 | 6 | Admin custom-claim checks at login and landing, `ProtectedAdminRoute`, placeholder Admin dashboard |
| M1.5A — FastAPI Authentication & Authorization | `fff01be` | 22 Nov 2026 | 10 | Firebase ID-token verification on all assessment routes, `require_admin`, ownership checks, generic errors, `authFetch`, 26 unit tests |
| M1.5B — Firestore Rules & Seed Button Removal | `2287868` | 22 Nov 2026 | 8 | `firestore.rules`, `firebase.json`, 44 emulator tests, browser seeding removed |
| Documentation baseline | `3c48bec` | 22 Nov 2026 | 3 | `CLAUDE.md`, `docs/PROJECT_STATUS.md`, `docs/FIRESTORE_BASELINE.md` |
| M1.5C — Secure Gemini Integration | **Deferred**; security patch only (commit after `3c48bec`) | 23 Nov 2026 | 6 | Browser-side Gemini OCR removed from `UploadResults.jsx` (no SDK, no key reference, no upload/Analyze controls); manual entry kept; shared grade validation for the SPM leaver and Form 4/5 pages (`gradeEntry.js`, 18 frontend unit tests); B2–B4 fixed on both pages; `CLAUDE.md` updated (no provider secrets in `VITE_*` variables). The server-side Gemini integration was **not** implemented. |

Recorded test results (not re-run for this documentation baseline):

- **M1.5A:** `python -m unittest discover -s tests -t . -v` — 26 tests, `OK`.
- **M1.5B:** `npm test` in `firestore-tests/` — 12 suites, 44 tests, 44 passed, 0 failed.
  Negative control: the W2 regression suite failed against the pre-fix rules (43 passed, 1 failed),
  confirming that the test detects the defect.
- **M1.5C security patch:** `node --test src/utils/gradeEntry.test.js` in `frontend/` — 18 tests passed;
  backend tests — 26 tests, `OK`; Firestore rules — 44/44 passed (rules unchanged).

## 3. Repository status at baseline

This is a snapshot taken on 22 Nov 2026 (MYT) **before** the documentation files (`CLAUDE.md`,
`docs/`) were created and staged. It is not the current working-tree status; run `git status` for that.

- At the time of the snapshot: branch `feature/admin-module`, HEAD `2287868`, nothing staged.
- **Unrelated local modifications** (not part of any milestone; never stage or revert them):
  `.gitignore` (one added line) and three files under `backend/chroma_db/`.
- **Tracked although listed in `.gitignore`:** `backend/chroma_db/`, `backend/.cache/` (ONNX model)
  and `scripts/node_modules/` (5,928 files). Git still reports changes to them.
- **Local-only, ignored:** `backend/.env`, `frontend/.env`, `backend/serviceAccountKey.json`, `backend/.venv/`.
- **No `.firebaserc`:** Firebase CLI commands must pass `--project route2unikl` explicitly.
- **No Python dependency manifest** (`requirements.txt` or similar). The local venv uses Python 3.12
  with FastAPI 0.165, ChromaDB 1.5.9, uvicorn 0.54, pydantic 2.14, httpx 0.28 and python-dotenv 1.2.

## 4. Deployment status

| Component | Status |
|---|---|
| Firestore Security Rules | **Deployed** to `route2unikl` on 22 Nov 2026 (MYT), owner-reported. See [FIRESTORE_BASELINE.md](FIRESTORE_BASELINE.md). |
| Frontend (React) | **Not deployed.** Runs on the local Vite dev server. No hosting configuration exists in the repository. |
| Backend (FastAPI) | **Not deployed.** API base URL is hard-coded to `http://localhost:8000` in `frontend/src/utils/apiClient.js`; CORS allows only `localhost:5173` and `127.0.0.1:5173`. |
| ChromaDB | Local persistent store in `backend/chroma_db/`. |
| Firestore indexes | Not managed in the repository (no `firestore.indexes.json`). |

Production smoke tests were run from the local React dev server connected to production Firebase.

## 5. Known limitations and technical debt

### Security

| ID | Issue | Evidence | Severity | Planned |
|---|---|---|---|---|
| S1 | Browser-exposed Gemini API key. **Active browser use removed** in the M1.5C security patch: `UploadResults.jsx` no longer imports the Gemini SDK, references the key or calls the Gemini API, and the production build contains no Gemini SDK, endpoint or key variable. An earlier check found the Vite dev server still serving the Gemini variable from `frontend/.env`; in a later name-only inspection of the local dev server (22 Nov 2026), neither `VITE_GEMINI_API_KEY` nor `VITE_OLLAMA_API_KEY` was among the variables served to the browser. **Historical exposure remains:** the Gemini key, and any provider key ever placed in a `VITE_*` variable while the dev server ran, must be treated as compromised and rotated or revoked (owner action). | `frontend/src/pages/user/UploadResults.jsx`, `frontend/.env` (local) | High until rotated or revoked | Owner action; M1.5C (deferred) |
| S2 | Self-asserted academic results. Before the security patch, `UploadResults.jsx` wrote `status: "verified"` / `recordType: "OFFICIAL_SPM_CERT"` / `verificationMethod: "AI_OCR_GEMINI"` even when no OCR ran, and grades were editable. It now writes the manual-entry values. Existing documents may still carry the old values; they never meant independent verification, and no code reads these fields. The manual-entry combination labels an SPM leaver's actual results as `PREDICTED_GRADES` because the rules offer no other label. | `UploadResults.jsx`, `isValidResults` in `firestore.rules` | Low–Medium | Results schema v2 design (separate approval) |
| S3 | Self-asserted assessment. `ai_assessments` is written by the browser, and `/api/assessment/recommend` derives the score from stored `answers[].isCorrect`. | `DummyAI.jsx`, `recommend_endpoint` in `backend/routes/assessment.py` | Medium | Future |
| S4 | Incomplete account deletion. Profile deletes `users/{uid}`, then the Auth user; `results/{uid}` and `ai_assessments/{uid}` remain (owners cannot delete them under the rules). | `Profile.jsx`, `firestore.rules` | Medium | M3 (protected FastAPI deletion endpoint) |
| S5 | Accepted limitation W1: a student can delete and re-create their own `users` document, changing the student type and resetting `createdAt`. It can never grant Admin. | `firestore.rules` comment, emulator suite 12 | Low | M3 |
| S6 | The Admin route checks the claim in the browser only and does not call `/api/admin/verify`. Acceptable while the dashboard is a placeholder; any Admin data must come from `require_admin` endpoints. | `ProtectedAdminRoute.jsx` | Low today | M2 |
| S7 | FastAPI interactive docs (`/docs`, `/openapi.json`) are public by default. | `backend/main.py` | Low | Before backend deployment |
| S8 | No Firebase App Check. | `frontend/src/firebase.js` | Low–Medium | Later |
| S9 | `scripts/uploadPrograms.js` hard-codes an absolute local path to an Admin SDK key file outside the repository and a placeholder `databaseURL`. The key itself is not committed; the path and filename are in Git history. | `scripts/uploadPrograms.js` | Low | Clean up in M4 |
| S10 | The existing AI assessment also calls the Gemini API from the backend (Gemma models and a `gemini-2.5-flash` fallback via `GEMINI_API_KEY`). The Gemini API terms cited by the owner restrict use in applications likely to be accessed by under-18s, so this feature needs the same provider-terms review; the OpenAI and Ollama terms also need review. | `backend/services/rag_orchestrator.py` | High (compliance) | Separate review before any public deployment |
| S11 | `frontend/.env` contains an unused `VITE_OLLAMA_URL`. No frontend code reads it, now or in Git history, but the Vite dev server serves its value to the browser (name-only inspection; the value was not inspected). | `frontend/.env` (local) | Low | Local configuration cleanup (owner action) |

### OCR status (M1.5C deferred)

- **OCR is temporarily unavailable.** The browser-based Gemini OCR was disabled for security. Removing
  the browser calls does not make OCR operational or secure; it only stops the key from being used by
  the frontend code. SPM leavers enter subjects and grades manually on the same page, and manual
  academic results entry remains supported (`UploadResults.jsx` and `ManualGradeEntry.jsx`).
- **Gemini / Google AI Studio remains the preferred OCR provider.** Tesseract was evaluated earlier and
  rejected for accuracy (owner-reported).
- **Planned architecture:** React → authenticated FastAPI endpoint → Gemini API. The key stays on the
  server, with authentication, eligibility checks, upload validation, limits and strict output validation.
- **Activation prerequisites:** a provider-terms and privacy review, particularly for users under 18 and
  for personal data (names, identification numbers) on SPM result slips; rotation or revocation of the
  previously browser-exposed key; and explicit owner approval.
- **Known issue for the future integration (B1):** the removed merge logic matched subjects by
  substring, so `MATEMATIK TAMBAHAN` overwrote `MATEMATIK`. Mathematics and Additional Mathematics must
  be kept separate by exact matching of normalized subject names.
- The previous browser implementation remains available in Git history (`UploadResults.jsx` at `3c48bec`).

### AI providers (backend)

- The AI assessment's provider chain in `backend/services/rag_orchestrator.py` is OpenAI → Gemma via the
  Gemini API → Ollama Cloud → static fallback questions. Provider keys are read only from `backend/.env`;
  the browser never calls a provider directly.
- **Ollama Cloud is integrated server-side** (`call_ollama_cloud`): requests go to
  `{OLLAMA_BASE_URL}/api/chat` with `OLLAMA_API_KEY` sent as a Bearer token. Ollama is tried only when
  `OLLAMA_API_KEY` is set and the earlier providers did not succeed.
- **The actual Ollama Cloud connection has not been verified.** No Ollama request has been made in testing,
  and whether `backend/.env` defines `OLLAMA_API_KEY` or `OLLAMA_BASE_URL` has not been checked (values are
  never read). Ollama Cloud requests must not be described as working until they are tested with approval.
- **Base URL discrepancy:** Ollama's documented cloud host is `https://ollama.com`, with the chat endpoint
  `/api/chat` (owner-confirmed). The backend default for `OLLAMA_BASE_URL` is `https://api.ollama.com`,
  which differs. If `OLLAMA_BASE_URL` is not set in `backend/.env`, Ollama requests may fail and the
  assessment falls back to another provider or the static questions. Setting `OLLAMA_BASE_URL`
  (configuration) or correcting the default (code) is a separate approved change.
- Provider-terms review for all providers: see S10.

### Programme data consistency

Programme data exists in three places, read by different parts of the system:

| Source | Read by |
|---|---|
| Firestore `programs` | `AllPrograms.jsx`, `Dashboard.jsx` |
| `frontend/src/assets/unikl_foundation_testplan.json` (35 programmes, 118 `preparatory_guideline` resources) | `Recommendation.jsx`, `PreparationPlan.jsx`, `recommendation_service.py`, `rag_orchestrator.py`, `seed_chroma.py`, `scripts/seedPrograms.js` |
| ChromaDB collection `unikl_programs` (`backend/chroma_db/`) | `rag_orchestrator.py` (retrieval for AI assessment) |

- Editing Firestore alone does not change recommendations, preparation plans or RAG retrieval.
- `scripts/seedPrograms.js` (exposed as `npm run seed` in `frontend/package.json`) deletes every
  `programs` document that is not in the JSON, then merge-writes the 35 programmes.
- `scripts/uploadPrograms.js` adds programmes from `scripts/unikl_programmes.csv` with auto-generated
  IDs, which would create duplicates.
- `backend/seed_chroma.py` removes ChromaDB records not in the JSON; `scripts/build_master_json.py` regenerates the JSON.
- A single source of truth and a synchronisation/re-indexing strategy must be chosen before M4–M6.

### Engineering

- No CI; all tests run manually.
- `frontend/package.json` lists server-only packages (`firebase-admin`, `csv-parser`) and the `seed`
  script; `@google/generative-ai` and `tesseract.js` are declared only in the root `package.json` and
  are no longer imported by the frontend.
- `frontend/src/pages/Register.jsx` is an unused duplicate; routes use `frontend/src/pages/auth/Register.jsx`.
- `.vscode/settings.json` points to `backend/venv/bin/python` (macOS layout); the local Windows venv is `backend/.venv`.
- `frontend/README.md` is the default Vite template.

### Previously reported — needs re-verification

- The static AI fallback path calls `print()` with an emoji, which raised `UnicodeEncodeError` on a
  cp1252 console during M1.5A testing.
- On the Profile page, saving an empty name is rejected by the rules without clear user feedback (observed during M1.5B review).

## 6. Roadmap (recommended order)

| Order | Milestone | Scope | Prerequisites and notes |
|---|---|---|---|
| — | **M1.5C — Secure Gemini Integration (DEFERRED)** | Security patch done: browser-side Gemini OCR disabled. Remaining: React → authenticated FastAPI → Gemini API. | Not completed. Activation requires a provider-terms and privacy review (users under 18, personal data on SPM slips), rotation or revocation of the old key, and owner approval. Required before OCR returns and before any public deployment. |
| 1 | M2 — Admin Dashboard and Sidebar | Admin layout, sidebar and logout; confirm Admin access with `/api/admin/verify`. | Clearly labelled placeholders; no invented statistics. |
| 2 | M3 — Manage Users | `require_admin` FastAPI endpoints using the Admin SDK. | Include protected account deletion that also removes `results` and `ai_assessments` (resolves S4, W1). |
| 3 | M4 — Manage Programmes | Admin CRUD for programmes. | Decide the programme single source of truth and sync strategy first; guard the seeders. |
| 4 | M5 — Manage Programme Criteria | Eligibility fields (`min_spm_credits`, `min_math_grade`, `min_bm_grade`, `min_bi_grade`, `requires_science`). | Consumed by `recommendation_service.py`. |
| 5 | M6 — Manage Preparatory Resources | The 118 `preparatory_guideline` entries inside programme records. | Same data-consistency strategy as M4. |
| 6 | M7 — System Information | System information and announcements. | — |

All Admin management goes through FastAPI endpoints protected by `require_admin`. Admins get no
additional browser access to Firestore.

## 7. Recommended next milestone

**M2 — Admin Dashboard and Sidebar.** The owner deferred M1.5C after the browser-side Gemini OCR
was disabled in a security patch. OCR is not operational; manual results entry remains supported.
Before OCR returns or any public deployment: rotate or revoke the previously exposed key(s), remove
the unused `VITE_OLLAMA_URL` from `frontend/.env`, resolve the Ollama base-URL discrepancy, complete the
provider-terms and privacy review (S1, S10, S11), and implement M1.5C.
Start M2 only at step 1 (inspect and plan) of the milestone workflow in [CLAUDE.md](../CLAUDE.md).
