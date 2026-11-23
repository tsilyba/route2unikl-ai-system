# Route2UniKL — Project Status Baseline

| | |
|---|---|
| Baseline date | 22 November 2026 (MYT) |
| Branch | `feature/admin-module` |
| Baseline commit | `2287868` (M1.5B), in sync with `origin/feature/admin-module` when this baseline was written |
| Last updated | 24 November 2026 (MYT): M3B-1B-P0 experimental Firestore account-access guard, an emulator proof of concept in test-only files, **not deployed**, production rules unchanged ([section 8 F](#f-m3b-1b-p0--experimental-firestore-account-access-guard)). 23 November 2026 (MYT): Admin sign-out hardening (`69bcc07`); Admin fail-closed security & testing register added ([section 8](#8-admin-module--fail-closed-security--testing-register)); M3A Manage Users (read-only) committed (`4905ac0`), M3B deferred; M2 Admin Dashboard & Sidebar implemented; browser-side Gemini OCR disabled for security; M1.5C **deferred**; frontend provider-secret review; shared grade validation for both grade-entry pages (see [section 5](#ocr-status-m15c-deferred)) |
| Production Firebase project | `route2unikl` |
| Related documents | [CLAUDE.md](../CLAUDE.md) · [FIRESTORE_BASELINE.md](FIRESTORE_BASELINE.md) |

## Evidence labels

Every status claim in this document uses one of these labels.

| Label | Meaning |
|---|---|
| **Repo-verified** | Implementation confirmed by reading the source code in this repository. |
| **Unit tests** | Covered by the mocked FastAPI tests in `backend/tests/` (`test_auth.py`, `test_admin_users.py`). |
| **Frontend unit tests** | Covered by the Node test-runner tests in `frontend/src/**/*.test.js` (run with `node --test "src/**/*.test.js"` in `frontend/`; synthetic data, no browser, Firebase or network). |
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
| Admin route guard for `/admin/dashboard` (browser claim check with forced token refresh; an invalid session is signed out before the redirect to login, and a failed sign-out shows a blocked screen with a retry) | `frontend/src/components/ProtectedAdminRoute.jsx`, `frontend/src/utils/adminClaims.js`, `frontend/src/utils/signOutFlow.js` | Repo-verified; Browser smoke test (Admin login, dashboard access, refresh); Frontend unit tests (sign-out flow) |
| Login / landing redirect by claim | `frontend/src/pages/auth/Login.jsx`, `frontend/src/pages/LandingPage.jsx` | Repo-verified; Browser smoke test |
| Server confirmation of Admin access before any admin content is shown (`GET /api/admin/verify`: 401 → sign out, then go to login only after sign-out succeeds; a failed sign-out keeps the admin area blocked ("Couldn't sign you out") with a retry; 403 or no explicit `is_admin: true` → denied; auth outage or unreachable server → blocked with Retry; stale results ignored) | `frontend/src/components/admin/AdminLayout.jsx`, `frontend/src/components/admin/AdminStatusPanel.jsx`, `frontend/src/utils/adminVerification.js`, `frontend/src/utils/signOutFlow.js` | Repo-verified; Frontend unit tests (classification, sign-out flow); Unit tests (endpoint) |
| Admin layout and dashboard (M2): separate admin layout without the student Header/Footer, fixed desktop sidebar, mobile slide-in navigation (overlay, Escape, focus handling), logout; dashboard with welcome, module overview (M3–M7 disabled, "Coming soon") and access status; no statistics; unknown `/admin/*` paths show an admin "Page not found" | `frontend/src/components/admin/`, `frontend/src/pages/admin/AdminDashboard.jsx`, `frontend/src/App.jsx` | Repo-verified; Frontend unit tests (navigation configuration) |
| Manage Users, read-only (M3A): `GET /api/admin/users` (search by name or email; student-type, account-status and profile filters; pagination, newest first) and `GET /api/admin/users/{uid}` (account, profile, learning journey, metadata-only record summaries); admin status from custom claims; Auth accounts without a profile flagged; allow-listed fields only; no account actions | `backend/routes/admin_users.py`, `backend/services/user_admin_service.py`, `frontend/src/pages/admin/AdminUsers.jsx`, `frontend/src/pages/admin/AdminUserDetail.jsx` | Repo-verified; Unit tests (endpoints, mocked Firebase); Frontend unit tests (filters, labels, errors) |
| FastAPI token verification, `require_admin`, `ensure_same_user`, coded HTTP 503 | `backend/core/auth.py` | Repo-verified; Unit tests |
| `GET /api/auth/me`, `GET /api/admin/verify` | `backend/routes/auth_check.py` | Unit tests; `/api/admin/verify` is called by `AdminLayout` (M2); `/api/auth/me` is not used by the frontend |
| Frontend `authFetch` and auth error panel | `frontend/src/utils/apiClient.js`, `frontend/src/components/ApiAuthErrorPanel.jsx` | Repo-verified |
| Firestore Security Rules | [`firestore.rules`](../firestore.rules) | Emulator tests; deployed to production (owner-reported) |
| Browser "Seed Programs" button removed | `frontend/src/App.jsx` | Repo-verified |

Apart from the shared grade-validation helper and the Admin navigation, verification, Manage Users and
sign-out helpers, no automated tests exist for the frontend UI, recommendation scoring, RAG retrieval quality,
AI output quality or OCR accuracy.

## 2. Milestone history

| Milestone | Commit | Date (MYT) | Files | Summary |
|---|---|---|---|---|
| Foundation (before the Admin module) | `dca8e2d`, `32902ab` and earlier | before 22 Nov 2026 | — | Student journey, OCR, ChromaDB RAG assessment, 35-programme dataset, recommendation engine, preparation plan |
| M1 — Admin Authentication & RBAC | `677728f` | 22 Nov 2026 | 6 | Admin custom-claim checks at login and landing, `ProtectedAdminRoute`, placeholder Admin dashboard |
| M1.5A — FastAPI Authentication & Authorization | `fff01be` | 22 Nov 2026 | 10 | Firebase ID-token verification on all assessment routes, `require_admin`, ownership checks, generic errors, `authFetch`, 26 unit tests |
| M1.5B — Firestore Rules & Seed Button Removal | `2287868` | 22 Nov 2026 | 8 | `firestore.rules`, `firebase.json`, 44 emulator tests, browser seeding removed |
| Documentation baseline | `3c48bec` | 22 Nov 2026 | 3 | `CLAUDE.md`, `docs/PROJECT_STATUS.md`, `docs/FIRESTORE_BASELINE.md` |
| M1.5C — Secure Gemini Integration | **Deferred**; security patch only (`35e75d6`) | 23 Nov 2026 | 6 | Browser-side Gemini OCR removed from `UploadResults.jsx` (no SDK, no key reference, no upload/Analyze controls); manual entry kept; shared grade validation for the SPM leaver and Form 4/5 pages (`gradeEntry.js`, 18 frontend unit tests); B2–B4 fixed on both pages; `CLAUDE.md` updated (no provider secrets in `VITE_*` variables). The server-side Gemini integration was **not** implemented. |
| M2 — Admin Dashboard & Sidebar | `9e75a38` | 23 Nov 2026 | 14 | Separate admin layout, fixed sidebar, mobile navigation, logout; server confirmation via the existing `GET /api/admin/verify`; dashboard with module overview (M3–M7 disabled) and access status; 22 frontend unit tests. No backend, rules or dependency changes. |
| M3A — Manage Users (read-only) | `4905ac0` | 23 Nov 2026 | 15 | `GET /api/admin/users` and `GET /api/admin/users/{uid}` (`require_admin`, Admin SDK, allow-listed responses); Manage Users list and User Details pages (on an expired session or unconfirmed access, the login page opens only after sign-out succeeds; a failed sign-out shows an error and a retry); 37 new backend tests and 24 new frontend unit tests (navigation tests updated). No account actions, rules or dependency changes. M3B (account actions) deferred. |
| Admin sign-out hardening | `69bcc07` | 23 Nov 2026 | 7 | Automatic sign-out after an ended session (`AdminLayout` on HTTP 401 from `/api/admin/verify`; `ProtectedAdminRoute` on invalid-session error codes) no longer ignores a failed Firebase sign-out: the login page opens only after sign-out succeeds; a failure keeps the admin area blocked and shows "Couldn't sign you out" with "Try signing out again". Shared helper `frontend/src/utils/signOutFlow.js` (also used by M3A): overlapping sign-outs share one attempt; callbacks of superseded attempts, stale verifications and unmounted components are ignored. 18 new frontend unit tests. Manual logout, student redirects, backend, rules and dependencies unchanged. |

Recorded test results (not re-run for this documentation baseline):

- **M1.5A:** `python -m unittest discover -s tests -t . -v` — 26 tests, `OK`.
- **M1.5B:** `npm test` in `firestore-tests/` — 12 suites, 44 tests, 44 passed, 0 failed.
  Negative control: the W2 regression suite failed against the pre-fix rules (43 passed, 1 failed),
  confirming that the test detects the defect.
- **M1.5C security patch:** `node --test src/utils/gradeEntry.test.js` in `frontend/` — 18 tests passed;
  backend tests — 26 tests, `OK`; Firestore rules — 44/44 passed (rules unchanged).
- **M2:** `node --test "src/**/*.test.js"` in `frontend/` — 40 tests passed (22 new Admin tests and the
  18 grade-validation tests); backend tests — 26 tests, `OK`; Firestore rules — 44/44 passed (rules unchanged).
- **M3A:** backend tests — 63 tests, `OK` (37 new Manage Users tests with mocked Firebase Authentication
  and Firestore, plus the existing 26); frontend unit tests — 66 passed; Firestore rules — 44/44 passed
  (rules unchanged); manual browser verification — 10/10 (owner-reported).
- **Admin sign-out hardening:** frontend unit tests — 84 passed (18 new sign-out flow tests); backend
  tests — 63 tests, `OK`; Firestore rules — 44/44 passed (rules unchanged); frontend production build and
  lint of the changed files — passed; manual browser regression checks — 5/5 (owner-reported).
- **M3B-1B-P0 (experimental, not deployed):** `npm test` in `firestore-tests/` (production
  `firestore.rules`) — 44/44 passed; experimental suite (explicit command, see section 8 F) — 100/100
  passed; mutation testing — see section 8 F. Backend and frontend tests were not re-run (no backend or
  frontend changes).

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
| S4 | Incomplete account deletion. Profile deletes `users/{uid}`, then the Auth user; `results/{uid}` and `ai_assessments/{uid}` remain (owners cannot delete them under the rules). | `Profile.jsx`, `firestore.rules` | Medium | M3B (protected FastAPI deletion endpoint) |
| S5 | Accepted limitation W1: a student can delete and re-create their own `users` document, changing the student type and resetting `createdAt`. It can never grant Admin. | `firestore.rules` comment, emulator suite 12 | Low | M3B |
| S6 | **Resolved in M2:** the Admin area previously checked the claim in the browser only. `AdminLayout` now calls `GET /api/admin/verify` and shows no admin content unless the server confirms access. Frontend checks still only control what is displayed; Admin data must come from `require_admin` endpoints (M3+). | `ProtectedAdminRoute.jsx`, `frontend/src/components/admin/AdminLayout.jsx` | Resolved | — |
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

### Admin user listing (M3A)

- **Read-only.** No endpoint or page changes accounts, profiles, claims or sessions. Account actions
  (disable, enable, delete) are M3B, deferred pending a separate security and deletion-design approval.
- **Account limit:** Firebase Authentication accounts are read in pages of 1,000, up to 2,000 per request.
  If more exist, the response reports `complete: false` and the page warns that results may be
  incomplete; results are never silently truncated. Search, filters and sorting run in memory on the
  server over the scanned accounts, newest registration first (ties by uid).
- **Cost:** each list request reads one Firestore `users` document per scanned Auth account (field
  mask: name, student type, journey step); a details request reads three documents.
- **Missing vs orphaned profiles:** enumeration is Auth-driven. Auth accounts without a `users/{uid}`
  profile are detected and labelled "Profile missing". Firestore profiles without an Auth account are
  **not** detected; reconciling such orphaned profiles is future work.
- **Details** are available only for accounts that exist in Firebase Authentication, and only for uids
  made of letters, digits, `_` and `-` (as created by Email/Password sign-up).
- **Data minimisation:** responses use explicit allow-lists. Password hashes and salts, tokens, raw
  custom claims, provider identifiers, grades, assessment answers and scores are never returned. Admin
  status comes only from the Firebase custom claim.

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
| 1 | M2 — Admin Dashboard and Sidebar | **Implemented.** Admin layout, sidebar, mobile navigation and logout; Admin access confirmed with `/api/admin/verify`. | Module cards are labelled "Coming soon"; no statistics. |
| 2 | M3A — Manage Users (read-only) | **Implemented.** `require_admin` list and details endpoints using the Admin SDK; Manage Users and User Details pages. | Listing limits and missing-profile detection: see section 5. |
| — | **M3B — Account actions (DEFERRED)** | Disable, enable and delete accounts. | Requires a separate security and deletion-design approval. Deletion must also remove `results` and `ai_assessments` (resolves S4, W1). |
| 3 | M4 — Manage Programmes | Admin CRUD for programmes. | Decide the programme single source of truth and sync strategy first; guard the seeders. |
| 4 | M5 — Manage Programme Criteria | Eligibility fields (`min_spm_credits`, `min_math_grade`, `min_bm_grade`, `min_bi_grade`, `requires_science`). | Consumed by `recommendation_service.py`. |
| 5 | M6 — Manage Preparatory Resources | The 118 `preparatory_guideline` entries inside programme records. | Same data-consistency strategy as M4. |
| 6 | M7 — System Information | System information and announcements. | — |

All Admin management goes through FastAPI endpoints protected by `require_admin`. Admins get no
additional browser access to Firestore.

## 7. Recommended next milestone

**M3B — Account actions (disable, enable, delete).** M3A (read-only Manage Users) is implemented.
M3B starts only after a separate security and deletion-design approval: protected `require_admin`
endpoints, no actions on the caller's own account or on admin accounts, and an account-deletion process
that also removes `results` and `ai_assessments` (resolves S4 and W1), with partial-failure handling.
M1.5C remains deferred: OCR is not operational and manual results entry remains supported. Before OCR
returns or any public deployment: rotate or revoke the previously exposed key(s), remove the unused
`VITE_OLLAMA_URL` from `frontend/.env`, resolve the Ollama base-URL discrepancy, complete the
provider-terms and privacy review (S1, S10, S11), and implement M1.5C.
Start M3B only at step 1 (inspect and plan) of the milestone workflow in [CLAUDE.md](../CLAUDE.md).

## 8. Admin Module — Fail-Closed Security & Testing Register

A living technical record of the security behaviour of the completed Admin milestones (M1, M1.5A,
M1.5B, M2, M3A and the Admin sign-out hardening), and of the experimental, **undeployed** M3B-1B-P0
account-access guard (section F), based on the repository code and the recorded test results. It is
**not** the final Development and Testing Report. Last recorded: 24 November 2026 (MYT).

"Fail-closed" means that any failure to confirm identity or Admin status leaves the Admin area and
Admin data unavailable. Frontend checks only decide what is displayed. Data is protected by
`require_admin` on the FastAPI endpoints and by `firestore.rules`.

**Evidence labels used in this section** (consistent with the evidence labels at the top of this document):

- **Backend unit**: mocked FastAPI tests in `backend/tests/`.
- **Frontend unit**: Node test-runner tests in `frontend/src/**/*.test.js`.
- **Emulator**: Firestore rules tests in `firestore-tests/` (local emulator).
- **Emulator mutation**: the experimental suite re-run in the emulator against deliberately weakened
  copies of the experimental rules; a weakening counts as detected when tests fail (M3B-1B-P0 only; the
  scripts are not stored in the repository).
- **Manual**: owner-reported browser verification. Results are recorded per milestone; individual steps,
  screenshots and logs are not stored in the repository.
- **Code inspection**: confirmed by reading the source only.
- **Not yet tested**: no recorded test.

### A. Authentication and authorization

| # | Behaviour | Responsible component / endpoint | When verification fails | Evidence |
|---|---|---|---|---|
| A1 | Admin status comes only from the Firebase custom claim `admin: true` (strict boolean) | Frontend: `hasAdminClaim` in `frontend/src/utils/adminClaims.js` (forced token refresh), used by `ProtectedAdminRoute.jsx` and `Login.jsx`. Backend: `get_current_user` in `backend/core/auth.py` (`is_admin = decoded.get("admin") is True`) | A non-admin account is redirected to `/dashboard`. If the claim cannot be read (for example, after a network failure), `ProtectedAdminRoute` shows "Unable to verify access" with Try Again and no admin content. The backend treats any other value (`false`, the string `"true"`, missing) as non-admin. The email address and the Firestore `role` field are never used. | Backend unit (non-boolean or false claims are not admin; string and false claims receive 403 on Manage Users); Emulator (a string claim grants nothing, suite 5); Code inspection (frontend claim helper, which has no unit test); Browser smoke test (M1: Admin login, dashboard access, refresh) |
| A2 | Backend Admin authorization | `require_admin` in `backend/core/auth.py` | HTTP 403 "Administrator privileges required." The endpoint handler does not run. | Backend unit |
| A3 | Server confirmation before any Admin content renders | `GET /api/admin/verify` (`backend/routes/auth_check.py`, `require_admin`); `frontend/src/components/admin/AdminLayout.jsx`; `frontend/src/utils/adminVerification.js` | The Admin layout renders only after HTTP 200 with `is_admin === true` for the same uid. Any other outcome shows a full-screen status panel instead of the Admin area. Late or stale results are ignored after unmount, retry or an account change. | Frontend unit (`adminVerification.test.js`, 13 tests: strict `is_admin`, different-account response, 401/403/503/network classification); Backend unit (endpoint: student denied, admin recognised); Code inspection (render gate) |
| A4 | HTTP 401 and 403 | Backend: `get_current_user`, `require_admin`, `ensure_same_user`. Frontend: `AdminLayout.jsx`, `AdminStatusPanel.jsx`, Manage Users `RequestErrorPanel` (`AdminUsers.jsx`) | Backend 401: missing or non-Bearer token; invalid, expired, revoked or malformed token; deleted account. Backend 403: disabled account, non-admin on Admin endpoints, and a request for another user's student records (this also applies to admins). Frontend 401: automatic sign-out (section B). Frontend 403: "Admin access not confirmed" with Sign out, shown instead of the Admin area (Admin layout) or instead of the user data (Manage Users pages, where the already verified navigation stays visible). | Backend unit; Frontend unit (classification, Manage Users error descriptions); Code inspection (panels) |
| A5 | Backend unavailability and verification failures | Backend: `get_current_user` (HTTP 503 `AUTH_SERVICE_UNAVAILABLE`), Manage Users routes (HTTP 503 `USER_SERVICE_UNAVAILABLE`). Frontend: `AdminLayout.jsx`, `ProtectedAdminRoute.jsx`, `RequestErrorPanel` | If Firebase initialisation or token verification cannot complete, the backend returns 503 and never authenticates; it logs only the exception type. The frontend shows a blocked panel for a sign-in outage, an unreachable server or an unexpected response, with Try again (and Sign out in the Admin layout). These are availability measures; the security property is that no failure grants access. | Backend unit (503 cases, no secrets in responses or logs); Frontend unit (classification); Code inspection |
| A6 | Students attempting to access Admin routes | Frontend: `ProtectedAdminRoute.jsx` (navigation only). Backend: `require_admin` on every Admin endpoint. Firestore: `firestore.rules` | Redirect to `/dashboard`, which is a convenience, not protection. Admin endpoints return 403. Students can access only their own Firestore documents. | Backend unit (student receives 403 from `/api/admin/verify` and both Manage Users endpoints); Emulator (no access to other students' records, suite 3; Admin cannot be self-granted through profile fields, suites 4 and 12); Code inspection (redirect) |
| A7 | Protection of Admin API endpoints | `GET /api/admin/verify`, `GET /api/admin/users`, `GET /api/admin/users/{uid}`, all with `Depends(require_admin)` | Authorization runs before the handler, so denied requests never reach account listing or Firestore reads. The Manage Users routes accept only GET; other methods return 405. Invalid uids return 422 before any lookup. | Backend unit (wiring tests on the real `main.app`: routes registered, authentication required, GET only) |
| A8 | Firestore Security Rules | `firestore.rules` | The Admin claim grants no browser read, list or write access to `users`, `results` or `ai_assessments`, and a string claim grants nothing. Programme data cannot be written from any browser client, Admin included. Students cannot grant themselves Admin through document fields. Unknown collections and unauthenticated access to private data are denied. The Admin SDK bypasses these rules, so the backend authorizes every Admin route itself (A2). | Emulator (44/44: suites 1, 3, 4, 5, 6, 9, 12); deployed to `route2unikl` on 22 Nov 2026 (owner-reported) |

### B. Sign-out and session security

Shared helper: `frontend/src/utils/signOutFlow.js` (`endSession`, `signOutThenRedirect`,
`createAttemptTracker`), used by `AdminLayout.jsx`, `ProtectedAdminRoute.jsx` and the Manage Users pages
(through `adminUsers.js` and `adminUsersApi.js`).

| # | Behaviour | Where | What happens | Evidence |
|---|---|---|---|---|
| B1 | Automatic sign-out after an invalid Admin session | `AdminLayout.jsx` (HTTP 401 from `/api/admin/verify`); `ProtectedAdminRoute.jsx` (claim check fails with a session-ended Firebase error code); Manage Users pages (HTTP 401 from their endpoints) | Firebase sign-out starts automatically. For `auth/user-token-expired` and `auth/user-disabled`, the Firebase SDK signs out by itself, and the guard follows the resulting signed-out state. | Code inspection; Frontend unit (helper) |
| B2 | No redirect to `/login` until Firebase sign-out succeeds | `endSession` and `signOutThenRedirect` | The redirect, or the "signed out" state, is applied only after the sign-out promise resolves. A failure, whether rejected or thrown immediately, never redirects. | Frontend unit (`signOutFlow.test.js`, 18 tests; sign-out tests in `adminUsers.test.js`) |
| B3 | Admin content blocked while sign-out is pending | `AdminStatusPanel.jsx`, `ProtectedAdminRoute.jsx`, `RequestErrorPanel` | The Admin layout shows the "Session expired" panel ("Your session is no longer valid. Signing you out…") with no buttons. The route guard shows "Verifying admin access..." or "Signing out...". On Manage Users pages, the error panel replaces the page content ("Signing you out and returning to the login page…"); the already verified Admin navigation remains visible, but no user data is shown. | Code inspection |
| B4 | Admin content blocked after a failed sign-out | Same components | The Admin layout and the route guard show "Couldn't sign you out"; the Manage Users panel shows "We couldn't sign you out. Check your internet connection, then try again." There is no redirect, no admin data and no "Back to login" link while the session may still be active. | Code inspection; Frontend unit (helper and Manage Users sign-out controls); Not yet tested in a browser (see E3) |
| B5 | "Try signing out again" recovery | Same components | Starts a new sign-out attempt. The button is hidden or disabled while signing out. On success the user goes to `/login`; on failure the failure screen returns. | Frontend unit (retry after failure); Code inspection |
| B6 | Stale verification and sign-out callbacks | `createAttemptTracker`; the current-run check in `AdminLayout.jsx` and `ProtectedAdminRoute.jsx`; cancellation on unmount | Callbacks of a superseded attempt, a restarted verification or an unmounted component are ignored, so they cannot redirect or change the screen. | Frontend unit (stale, superseded and unmounted cases); Code inspection (wiring) |
| B7 | Overlapping sign-out attempts | `signOutFlow.js` | Overlapping requests share one Firebase sign-out; each still-active caller receives the same outcome. The next request after it settles starts a new attempt. | Frontend unit |
| B8 | Manual Admin logout (M2, unchanged) | `performSignOut` in `AdminLayout.jsx` (header and sidebar Log out, with a confirmation dialog) | "Signing out" panel, then `/login` after sign-out. On failure, only the error code is logged, an alert says "We couldn't log you out", and access is re-verified; there is no redirect. | Code inspection |

### C. Manage Users security (M3A)

| # | Protection | Implementation | Evidence |
|---|---|---|---|
| C1 | Server-side Admin authorization on the list and detail endpoints | `Depends(require_admin)` on `GET /api/admin/users` and `GET /api/admin/users/{uid}` (`backend/routes/admin_users.py`). Query parameters and the uid are validated (HTTP 422). | Backend unit (`test_admin_users.py`: no token, or an invalid, expired, revoked or deleted-account token → 401; student, string or false claim → 403; sign-in outage → 503; none of these access Firebase Authentication accounts or Firestore) |
| C2 | Response-field allow-list | The service builds responses from explicit allow-lists, and FastAPI response models drop any other field. List items contain uid, email, name, student type, is_admin, disabled, email_verified, created and last sign-in times, profile status and journey step. Details add sign-in providers, a profile summary and metadata-only record summaries. | Backend unit (exact field sets for list items and details) |
| C3 | Sensitive account and academic data excluded | Never returned: password hashes and salts, token data, raw custom claims, phone numbers, provider identifiers, grades, assessment answers, scores and the academic snapshot. Firestore reads use field masks; the `results` and `answers` arrays are read on the server only to count entries. Errors are generic, and logs record only the exception type. | Backend unit (sentinel values never appear in responses or logs; field masks asserted) |
| C4 | Administrator status from the custom claim only | A profile `role` of `"admin"` and a string claim `"true"` are not treated as admin. | Backend unit |
| C5 | Student access restrictions | Backend 403 for students on both endpoints; the frontend route guard redirects students to `/dashboard` (navigation only). | Backend unit; Code inspection (redirect) |
| C6 | No account modifications in M3A | Only GET routes exist (other methods return 405). The service makes no write calls. In tests, the mutating Firebase Admin Auth functions (create, update and delete users, set custom claims, revoke refresh tokens) are patched and asserted unused, and the fake Firestore has no write methods. | Backend unit; Code inspection |
| C7 | Missing profiles and incomplete listings (data completeness, **not** a security boundary) | Auth accounts without a `users/{uid}` profile are labelled "Profile missing". Listings scan at most 2,000 Auth accounts and report `complete: false` with a warning instead of silently truncating. Firestore profiles without an Auth account are not detected. | Backend unit |

### D. Evidence and verification

| Evidence | Scope | Latest recorded result |
|---|---|---|
| Backend unit tests | `test_auth.py` (26), `test_admin_users.py` (37) | 63 tests, `OK` |
| Frontend unit tests | `gradeEntry` (18), `adminNavigation` (11), `adminVerification` (13), `adminUsers` (24), `signOutFlow` (18) | 84/84 passed |
| Firestore emulator tests (production rules) | `firestore-tests/rules.test.mjs` against `firestore.rules`, run by `npm test` (12 suites, defined in `shared-rules-suite.mjs`) | 44/44 passed |
| Firestore emulator tests (experimental, M3B-1B-P0) | `firestore-tests/account-access.experimental.suite.mjs` against the test-only `account-access.experimental.rules`: the same 44 tests plus 56 guard tests (section F) | 100/100 passed |
| Mutation testing (experimental, M3B-1B-P0) | The experimental suite re-run against deliberately weakened copies of the experimental rules (section F) | 19 of 20 weakenings detected; the undetected one removes a redundant check |
| Frontend build and lint | Production build; lint of the changed files with zero warnings allowed | Passed (pre-existing project-wide lint issues: see E6) |
| Manual (owner-reported) | M3A Manage Users browser verification | 10/10 |
| Manual (owner-reported) | Admin sign-out hardening browser regression checks | 5/5 |
| Manual (owner-reported) | Earlier browser smoke tests recorded in section 1 (for example, M1 Admin login, dashboard access and refresh) | See section 1 |

Manual results are recorded per milestone; this register does not attribute individual behaviours to
specific manual steps. Not yet tested: a failed automatic sign-out in a real browser (B4, B5; the
helper logic is covered by frontend unit tests), and rendered-component behaviour beyond code
inspection (A3, B3–B6).

### E. Known limitations and open issues

| # | Limitation | Type | Effect / status |
|---|---|---|---|
| E1 | If Firebase's own sign-out fails during a token refresh (for an expired token or a disabled account), the stale-result check in `ProtectedAdminRoute` discards the error and the guard stays on "Verifying admin access..." until the page is reloaded. | Usability problem | Access remains blocked (fail-closed). Open. |
| E2 | A persistent browser-storage failure can prevent sign-out from completing. The user stays on the blocked "Couldn't sign you out" screen, and the stored session can remain in that browser until site data is cleared. | Security limitation (residual local session) and usability problem | Admin content stays blocked in the app. Recovery is user-side, such as clearing the site's data. Open. |
| E3 | The automatic sign-out failure UI has helper-level automated tests, but no browser-level failure-injection test. | Test-coverage gap | Open. |
| E4 | The component wiring (`AdminLayout`, `ProtectedAdminRoute`, `AdminStatusPanel`, the Manage Users pages) has no rendered-component unit tests; that would need a test-renderer dependency. | Test-coverage gap | Open. |
| E5 | Student-facing sign-out handling is outside the hardening patch: `ApiAuthErrorPanel.jsx` ignores a failed sign-out and then redirects; `Login.jsx` ignores a failed sign-out after a failed claim check; the student `Header.jsx` Logout has no error handling. | Security limitation (low) and future development task | Open; needs a separate approval. |
| E6 | Project-wide lint: 21 errors and 2 warnings in 15 files not touched by M3A or the sign-out hardening (mostly unused variables; `react-hooks` findings in `DummyAI.jsx` and `Recommendation.jsx`). | Future development task (code quality) | Open. |
| E7 | M3B account actions (disable, enable, delete) are not implemented; S4 and S5 remain open. | Future development task | Deferred pending a security and deletion-design approval. |
| E8 | A retry from the Admin layout's "Couldn't sign you out" panel is not tied to a verification run; in a rare overlap, a late failure could block a screen that had just been verified again. | Usability problem | Fails closed. Open. |
| E9 | A failed manual Admin logout uses an alert and re-verification instead of the shared failure panel. | Usability problem and future development task | Open. |
| E10 | Manage Users does not detect Firestore profiles without an Auth account, and scans at most 2,000 accounts per request (reported, not hidden). | Future development task | Open (section 5). |

Other project-wide security items (S1–S11) are tracked in [section 5](#5-known-limitations-and-technical-debt).
This register does not claim that every edge case is resolved.

### F. M3B-1B-P0 — Experimental Firestore Account-Access Guard

> **Status: experimental proof of concept, NOT deployed.** The production rules file `firestore.rules`
> is unchanged (byte-identical to `69bcc07`), and production Firestore has no account-access guard. The
> results below come from the local emulator (`demo-route2unikl`) with mock tokens. None of them is a
> production security guarantee.

**Purpose.** Disabling or deleting a Firebase Authentication account, or revoking its refresh tokens,
does not end ID tokens that were already issued: they remain valid until they expire (up to one hour),
and Firestore Security Rules do not check revocation. P0 tests whether the rules can deny such an
account's browser access to its own private documents immediately, using a record that only the backend
can write.

**Security boundary.** The guard covers browser access through the Firebase SDK to `users/{uid}`,
`results/{uid}` and `ai_assessments/{uid}` only. It does not cover the FastAPI backend (the Admin SDK
bypasses rules; the backend relies on its own token checks, section A), the public `programs` catalogue,
or Firebase Authentication itself.

**Files** (all in `firestore-tests/`):

| File | Role |
|---|---|
| `account-access.experimental.rules` | The experimental rules: the production rules plus the guard. Test-only: `firebase.json` does not reference it, so `firebase deploy` never uses it. |
| `account-access.experimental.suite.mjs` | Experimental suite: the original 44 tests, with an active record for every test identity, plus 56 guard tests. Refuses to run if the loaded rules do not contain the guard. Runs only by explicit command; its name does not match the `node --test` default patterns. |
| `shared-rules-suite.mjs` | Shared harness and the original 44 tests, moved unchanged from `rules.test.mjs`. |
| `rules.test.mjs` | Production baseline: the 44 tests against `../firestore.rules`. Run by `npm test`. |

Commands, run from `firestore-tests/`:

- Production baseline: `npm test`
- Experimental: `firebase emulators:exec --only firestore --project demo-route2unikl --config ../firebase.json "node --test --test-reporter=spec account-access.experimental.suite.mjs"`

**Record schema.** `account_access/{uid}`, written only by the backend (Admin SDK):

| Field | Type | Meaning |
|---|---|---|
| `state` | `'active'`, `'disabled'`, `'deleting'` or `'deleted'` | Only `'active'` grants access. |
| `version` | integer ≥ 0 | Incremented by the backend; not used in access decisions. |
| `sessionsValidAfter` | timestamp, optional | Set when an account is re-enabled; a session must have started after it. |

Any other field makes the record malformed, and access is denied. Operation locks, audit history and
bookkeeping timestamps (such as `updatedAt`) should therefore be stored in separate backend-only
collections. This is a recommendation; it is not implemented.

| # | Protection | Implementation (experimental rules) | Evidence |
|---|---|---|---|
| F1 | One guard on every operation the rules allow on the three collections | `isActiveOwner(uid)`: the existing `isOwner(uid)` check, then `hasActiveAccount()`. It starts all 8 `allow` statements (`get`, `create` and `update`, plus `delete` on `users`). No `list` is allowed. The owner check runs first, so the record is read only for the owner's own requests. | Emulator (suite 0 requires the exact list of all 12 `allow` statements in the file); Emulator mutation (removing the guard from any one of the 8 statements: 23–37 tests fail); Code inspection |
| F2 | Only an active, well-formed record grants access | Denied: `disabled`, `deleting` and `deleted` records, a missing record, and malformed records (16 cases: missing fields, wrong types, unknown or wrongly cased states, a negative or non-integer `version`, a wrongly typed threshold, misspelt or extra fields). Applies to get, create, update and delete; stored data is unchanged afterwards. | Emulator (suite 13); Emulator mutation (state check removed: 9 tests fail; extra-field check removed: 2; `version` checks removed: 3; missing record allowed, as in the documented Realtime Database pattern: 22) |
| F3 | Deleted academic documents cannot be recreated | With the record at `deleting` or `deleted` and the documents removed by the backend, a session that is still valid cannot create or read `users`, `results` or `ai_assessments`. | Emulator (suite 13) |
| F4 | Re-enabled accounts: a session that began before the threshold is denied | `timestamp.value((auth_time − 1) × 1000) >= sessionsValidAfter`, that is, `auth_time` ≥ ceil(threshold) + 1 second. A missing or non-integer `auth_time` is denied when a threshold exists; without a threshold, `auth_time` is not consulted. A threshold never overrides a non-active state. | Emulator (suite 14: 14 boundary cases, including sign-ins in the same second and thresholds 1 µs past a whole second; missing, null, string, float and boolean `auth_time`); Emulator mutation (comparison that rounds the threshold down: 6 tests fail; no one-second margin: 4; `seconds()`-based comparison: 10; missing `auth_time` tolerated: 1) |
| F5 | `account_access` is backend-only | `allow read, write: if false` (the catch-all also denies it). Students, the Admin claim, a string claim and signed-out visitors cannot get, list, query, create, update or delete records, or write sub-collections. A student cannot activate, create or alter their own record or threshold. | Emulator (suite 15); Emulator mutation (owner read allowed: 6 tests fail) |
| F6 | Existing ownership, payload and query restrictions still apply | The original 44 tests pass against the experimental rules. Every test identity has an active record, so denials come from the original checks, not from the guard. An Admin with an active record still has no access to students' documents; list, filtered and collection-group queries remain denied. | Emulator (suites 1–12 and 16); Emulator mutation (payload validation removed: 16 tests fail; an extra wildcard match granting owner reads: 40) |
| F7 | Production rules unchanged; ordinary deployment and default test runs do not pick up the experimental rules | `firebase.json` references only `firestore.rules`, which is byte-identical to `69bcc07`. `npm test` and a bare `node --test` run only the production baseline. | Code inspection (`firebase.json`; Git object hash of `firestore.rules`); Emulator (a bare `node --test` ran only the 44 baseline tests); Emulator mutation (the experimental suite refused to run with the production rules; with the experimental rules copied into a scratch `firestore.rules`, the baseline failed 15 tests) |

**Mutation testing.** The experimental suite was re-run against 20 deliberately weakened copies of the
experimental rules (F1–F6). 19 were detected, each making between 1 and 40 tests fail. The undetected
one removes the threshold's type check, which is redundant: the timestamp comparison itself denies a
wrongly typed threshold. The scripts ran from a temporary directory and are not stored in the repository.

**Emulator observation (not documented by Firebase).** In the emulator, the rules function
`Timestamp.seconds()` returned the second within the minute (0–59), not seconds since the epoch. A first
draft that used it accepted every old session; the boundary tests rejected it. The final comparison uses
timestamps only (`timestamp.value`), which the emulator compared to 1 µs. The Firebase rules reference
states neither the range of `seconds()` nor the precision of timestamp comparison.

**Limitations and pending work**

| # | Limitation | Type | Status |
|---|---|---|---|
| FL1 | Not deployed. Production Firestore has no account-access guard: a disabled or deleted account keeps browser access to its own documents until its ID token expires (up to one hour). | Security limitation | Open. Deployment needs FL2, FL5 and separate owner approval. |
| FL2 | Production `auth_time`: the Firestore rules reference for `request.auth.token` does not list `auth_time`, and the emulator tests used hand-built mock tokens. If production tokens do not provide it as an integer, re-enabled accounts would be denied (fails closed). | Not yet tested | Needs an owner-approved production check on a test account before deployment. |
| FL3 | Session-check precision: `auth_time` is in whole seconds, so a genuine sign-in less than 2 seconds after the threshold is denied (fails closed). The check assumes `auth_time` is within one second of the real sign-in time, on a clock consistent with Firestore server time; Firebase does not document this. The backend must set the threshold with a server timestamp, confirm the account is disabled first, and wait about 3 seconds before re-enabling it. | Security limitation (residual) and design constraint | Open; backend design (M3B-2). |
| FL4 | Cost and latency: about one extra billed document read per owner request on the three collections, including denied requests (Firebase bills document reads made by rules), using 1 of the 10 document reads allowed per rules evaluation. | Cost and performance | Code inspection; not measured. |
| FL5 | Records are not provisioned: registration and login do not create `account_access` records, and no backfill exists. Deploying the experimental rules now would deny every account, Admin accounts included. | Future development task | Pending (next M3B-1B step). |
| FL6 | Student self-delete (`Profile.jsx`) still deletes from the browser and does not use the guard; S4 remains open. | Future development task | Pending (M3B). |
| FL7 | Firebase does not document the ordering between a rules check and a simultaneous change to the record; a write made just before an account is disabled may still be saved. The emulator tests include no concurrency testing. | Security limitation (residual) | Not yet tested. |
| FL8 | The guard does not apply to the FastAPI backend, which uses the Admin SDK (rules do not apply) and relies on its own token checks (section A). | Boundary (by design) | — |
| FL9 | The emulator is not production: rules-engine details, token contents, billing and latency may differ. | Test-coverage gap | Open. |

### Future Admin Module report

A comprehensive Admin Module Development and Testing Report will be prepared after all Admin Module
milestones are completed. The report will consolidate implementation decisions, architecture, security
controls, test cases, results, defect history, limitations and supporting evidence from the milestone records.
