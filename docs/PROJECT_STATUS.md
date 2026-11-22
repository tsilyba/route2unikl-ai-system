# Route2UniKL — Project Status Baseline

| | |
|---|---|
| Baseline date | 22 November 2026 (MYT) |
| Branch | `feature/admin-module` |
| Baseline commit | `2287868` (M1.5B), in sync with `origin/feature/admin-module` when this baseline was written |
| Production Firebase project | `route2unikl` |
| Related documents | [CLAUDE.md](../CLAUDE.md) · [FIRESTORE_BASELINE.md](FIRESTORE_BASELINE.md) |

## Evidence labels

Every status claim in this document uses one of these labels.

| Label | Meaning |
|---|---|
| **Repo-verified** | Implementation confirmed by reading the source code in this repository. |
| **Unit tests** | Covered by the mocked FastAPI tests in `backend/tests/test_auth.py`. |
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
| Manual grade entry → `results/{uid}` | `frontend/src/pages/user/ManualGradeEntry.jsx` | Repo-verified; Emulator tests (payload) |
| OCR result upload (Gemini, in the browser) → `results/{uid}` | `frontend/src/pages/user/UploadResults.jsx` | Repo-verified; Emulator tests (payload); live OCR Untested in this baseline |
| Academic results saved in production | — | Browser smoke test + Console (document confirmed). Save method (manual or OCR) not recorded. Browser read-back not independently tested |
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

No automated tests exist for the frontend UI, recommendation scoring, RAG retrieval quality,
AI output quality or OCR accuracy.

## 2. Milestone history

| Milestone | Commit | Date (MYT) | Files | Summary |
|---|---|---|---|---|
| Foundation (before the Admin module) | `dca8e2d`, `32902ab` and earlier | before 22 Nov 2026 | — | Student journey, OCR, ChromaDB RAG assessment, 35-programme dataset, recommendation engine, preparation plan |
| M1 — Admin Authentication & RBAC | `677728f` | 22 Nov 2026 | 6 | Admin custom-claim checks at login and landing, `ProtectedAdminRoute`, placeholder Admin dashboard |
| M1.5A — FastAPI Authentication & Authorization | `fff01be` | 22 Nov 2026 | 10 | Firebase ID-token verification on all assessment routes, `require_admin`, ownership checks, generic errors, `authFetch`, 26 unit tests |
| M1.5B — Firestore Rules & Seed Button Removal | `2287868` | 22 Nov 2026 | 8 | `firestore.rules`, `firebase.json`, 44 emulator tests, browser seeding removed |

Recorded test results (not re-run for this documentation baseline):

- **M1.5A:** `python -m unittest discover -s tests -t . -v` — 26 tests, `OK`.
- **M1.5B:** `npm test` in `firestore-tests/` — 12 suites, 44 tests, 44 passed, 0 failed.
  Negative control: the W2 regression suite failed against the pre-fix rules (43 passed, 1 failed),
  confirming that the test detects the defect.

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
| S1 | Gemini API key used in the browser. `UploadResults.jsx` creates `GoogleGenerativeAI(import.meta.env.VITE_GEMINI_API_KEY)`. Vite inlines `VITE_*` variables into the client bundle, so anyone who loads a built app can extract the key. | `frontend/src/pages/user/UploadResults.jsx` | High — blocks any public deployment | M1.5C |
| S2 | Self-asserted academic results. Extracted grades remain editable (`handleEditChange`) and the browser writes `status: "verified"` / `verificationMethod: "AI_OCR_GEMINI"`. Rules check the shape, not the truth. | `UploadResults.jsx`, `isValidResults` in `firestore.rules` | Medium | M1.5C (server-side OCR), later verification design |
| S3 | Self-asserted assessment. `ai_assessments` is written by the browser, and `/api/assessment/recommend` derives the score from stored `answers[].isCorrect`. | `DummyAI.jsx`, `recommend_endpoint` in `backend/routes/assessment.py` | Medium | Future |
| S4 | Incomplete account deletion. Profile deletes `users/{uid}`, then the Auth user; `results/{uid}` and `ai_assessments/{uid}` remain (owners cannot delete them under the rules). | `Profile.jsx`, `firestore.rules` | Medium | M3 (protected FastAPI deletion endpoint) |
| S5 | Accepted limitation W1: a student can delete and re-create their own `users` document, changing the student type and resetting `createdAt`. It can never grant Admin. | `firestore.rules` comment, emulator suite 12 | Low | M3 |
| S6 | The Admin route checks the claim in the browser only and does not call `/api/admin/verify`. Acceptable while the dashboard is a placeholder; any Admin data must come from `require_admin` endpoints. | `ProtectedAdminRoute.jsx` | Low today | M2 |
| S7 | FastAPI interactive docs (`/docs`, `/openapi.json`) are public by default. | `backend/main.py` | Low | Before backend deployment |
| S8 | No Firebase App Check. | `frontend/src/firebase.js` | Low–Medium | Later |
| S9 | `scripts/uploadPrograms.js` hard-codes an absolute local path to an Admin SDK key file outside the repository and a placeholder `databaseURL`. The key itself is not committed; the path and filename are in Git history. | `scripts/uploadPrograms.js` | Low | Clean up in M4 |

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
  script; `@google/generative-ai` and `tesseract.js` are declared only in the root `package.json`.
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
| 1 | **M1.5C — Secure Gemini Integration** | Move OCR extraction from the browser to an authenticated FastAPI endpoint; remove `VITE_GEMINI_API_KEY` and `@google/generative-ai` usage from the frontend. | Required before any public application deployment. Rotate the key if any build containing it has been shared or hosted. |
| 2 | M2 — Admin Dashboard and Sidebar | Admin layout, sidebar and logout; confirm Admin access with `/api/admin/verify`. | Clearly labelled placeholders; no invented statistics. |
| 3 | M3 — Manage Users | `require_admin` FastAPI endpoints using the Admin SDK. | Include protected account deletion that also removes `results` and `ai_assessments` (resolves S4, W1). |
| 4 | M4 — Manage Programmes | Admin CRUD for programmes. | Decide the programme single source of truth and sync strategy first; guard the seeders. |
| 5 | M5 — Manage Programme Criteria | Eligibility fields (`min_spm_credits`, `min_math_grade`, `min_bm_grade`, `min_bi_grade`, `requires_science`). | Consumed by `recommendation_service.py`. |
| 6 | M6 — Manage Preparatory Resources | The 118 `preparatory_guideline` entries inside programme records. | Same data-consistency strategy as M4. |
| 7 | M7 — System Information | System information and announcements. | — |

All Admin management goes through FastAPI endpoints protected by `require_admin`. Admins get no
additional browser access to Firestore.

## 7. Recommended next milestone

**M1.5C — Secure Gemini Integration.** The browser-side `VITE_GEMINI_API_KEY` integration is the
highest-severity open issue (S1) and must be secured before any public application deployment.
It also lays the groundwork for more trustworthy academic results (S2). Start it only at step 1
(inspect and plan) of the milestone workflow in [CLAUDE.md](../CLAUDE.md).
