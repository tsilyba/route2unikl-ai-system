# Route2UniKL — Project Status Baseline

| | |
|---|---|
| Baseline date | 22 November 2026 (MYT) |
| Branch | `feature/admin-module` |
| Baseline commit | `2287868` (M1.5B), in sync with `origin/feature/admin-module` when this baseline was written |
| Last updated | 26 November 2026 (MYT): M3B-3 Admin Delete Student Account, **local emulators only, not committed, not deployed; owner browser walkthrough on 26 Nov 2026 partially verified the D1–D14 plan (5 verified, 8 partially verified, 1 not verified; D4, D5 and D13 incomplete)**: permanent deletion of `active` or `disabled` student accounts (Firebase Authentication account, `users`, `results` and `ai_assessments` documents), with a typed-email confirmation in the browser and a uid confirmation checked by the server; access closed first, data deleted in one atomic Firestore batch, Auth deleted only after the data removal is confirmed, minimal tombstone and audit record kept; every failure recorded and resumable, including an Auth account already gone ("Incomplete deletions"); administrators protected at three points; deletion locks renewed with a takeover grace period; the backend's student-data endpoints refuse accounts in deletion (JL1, emulator mode only); the L1 403-message defect fixed; saving S3's results in the app during the walkthrough opened the AI-assessment page, so the AI generation workflow was triggered (external AI provider request not verified; browser test plan corrected); post-implementation security audit (26 Nov 2026): PASS WITH LIMITATIONS, acceptable only as a local-emulator development milestone, **not production-ready** ([section 8 L](#l-m3b-3--admin-delete-student-account-emulator-only)). M3B-2 (`e5e41a6`) Admin Disable & Enable accounts, **local emulators only, not deployed**: protected endpoints mounted only in emulator mode, coordinated with the account-access record, operation locks, audit records, resumable incomplete operations, and Manage Users controls; owner browser walkthrough on 26 Nov 2026: 13/13 conversational checkpoints passed (owner-reported); these do not map one-to-one to the 13 planned tests, of which 3 were verified, 7 partially verified, 1 not verified and 2 covered by automated tests only; Firestore rules rejection, audit-record contents and old refresh-token behaviour after Enable were not manually verified; post-implementation security audit (26 Nov 2026): PASS WITH LIMITATIONS, acceptable as a local-emulator development milestone, **not production-ready** (Medium findings M1–M3 open) ([section 8 K](#k-m3b-2--admin-disable--enable-accounts-emulator-only)). M3B-1B-P1-B2B/C (`7936909`) local account integration, **local emulators only, not deployed**: the backend mounts the registration route only when it starts in Firebase emulator mode, and the React dev server uses the emulators and backend registration only with `VITE_USE_FIREBASE_EMULATORS=true`; production behaviour unchanged; owner browser walkthrough in emulator mode completed on 26 Nov 2026 (11 of 11 steps passed, with recorded limitations), after a password-length defect found in step M5 was fixed in the frontend; registration passwords containing hidden control characters (Unicode `Cc`) are now refused on both registration paths and the backend (JL9 change; owner browser retest pending) ([section 8 J](#j-m3b-1b-p1-b2bc--local-account-integration-emulator-only)). M3B-1B-P1-B2A (`29fcdd3`) trusted backend registration, **local emulator testing only**, **not deployed** ([section 8 I](#i-m3b-1b-p1-b2a--trusted-backend-registration-emulator-only)). M3B-1B-P1-B1 (`6e3675f`) backend account-access service for `account_access/{uid}` records, backend-only, **not deployed** ([section 8 H](#h-m3b-1b-p1-b1--backend-account-access-service)). M3B-1B-P1-A (`7ec0ecb`) Firebase Authentication emulator foundation for local development and tests; the backend records its Firebase configuration at initialization, refuses emulator settings in production mode, and re-checks the configuration before and after every token verification (503 on any mismatch) ([section 8 G](#g-m3b-1b-p1-a--firebase-authentication-emulator-foundation)). M3B-1B-P0 experimental Firestore account-access guard (`d646700`), an emulator proof of concept in test-only files, **not deployed**, production rules unchanged ([section 8 F](#f-m3b-1b-p0--experimental-firestore-account-access-guard)). 23 November 2026 (MYT): Admin sign-out hardening (`69bcc07`); Admin fail-closed security & testing register added ([section 8](#8-admin-module--fail-closed-security--testing-register)); M3A Manage Users (read-only) committed (`4905ac0`), M3B deferred; M2 Admin Dashboard & Sidebar implemented; browser-side Gemini OCR disabled for security; M1.5C **deferred**; frontend provider-secret review; shared grade validation for both grade-entry pages (see [section 5](#ocr-status-m15c-deferred)) |
| Production Firebase project | `route2unikl` |
| Related documents | [CLAUDE.md](../CLAUDE.md) · [FIRESTORE_BASELINE.md](FIRESTORE_BASELINE.md) |

## Evidence labels

Every status claim in this document uses one of these labels.

| Label | Meaning |
|---|---|
| **Repo-verified** | Implementation confirmed by reading the source code in this repository. |
| **Unit tests** | Covered by the mocked FastAPI tests in `backend/tests/` (`test_auth.py`, `test_admin_users.py`, `test_firebase_config.py`, `test_account_access_service.py`, `test_registration.py`). |
| **Frontend unit tests** | Covered by the Node test-runner tests in `frontend/src/**/*.test.js` (run with `node --test "src/**/*.test.js"` in `frontend/`; synthetic data, no browser, Firebase or network). |
| **Emulator tests** | Covered by the Firestore rules suite in `firestore-tests/` (local emulator, `demo-route2unikl`). |
| **Emulator integration tests** | Covered by `backend/integration_tests/`: the backend against the local Firebase Authentication and Firestore emulators (`demo-route2unikl`), run with a separate command (section 8 G). Emulator results are not production evidence. |
| **Browser smoke test** | Exercised manually in the real app: local React dev server connected to production Firebase. Owner-reported. |
| **Console** | Checked in the Firebase Console. Owner-reported. |
| **Rules Playground** | Simulated in the Firebase Console Rules Playground. A rules simulation, not an application test. Owner-reported. |
| **Untested** | No recorded test. |

## 1. Implemented features

### Student journey

| Feature | Main location | Evidence |
|---|---|---|
| Registration (Email/Password, creates `users/{uid}`). Production: in the browser. Local emulator mode only: through the trusted backend registration (section 8 J). On both paths the password must have 6–128 characters and no hidden control characters, checked before any request (JL9 change, section 8 J) | `frontend/src/pages/auth/Register.jsx`, `frontend/src/utils/registrationApi.js` | Repo-verified; Emulator tests (payload); Browser smoke test (production flow); Frontend unit tests (backend client); Emulator integration tests (backend flow); Manual (emulator mode, owner-reported, 26 Nov 2026: steps M2–M5, M10) |
| Login (local emulator mode only: a student whose Firestore access is refused is signed out with a message; section 8 J) | `frontend/src/pages/auth/Login.jsx`, `frontend/src/utils/accountAccess.js` | Repo-verified; Browser smoke test (production); Frontend unit tests (access check); Manual (emulator mode, owner-reported, 26 Nov 2026: steps M6–M9) |
| Forgot password | `frontend/src/pages/auth/ForgotPassword.jsx` | Repo-verified; Untested |
| Profile read and name edit | `frontend/src/pages/user/Profile.jsx` | Repo-verified; Emulator tests; Browser smoke test |
| Profile "delete account" (browser deletion; leaves `results`, `ai_assessments` and the access record: S4, FL6; not changed by the M3B-3 Admin deletion) | `frontend/src/pages/user/Profile.jsx` | Repo-verified; Emulator tests (rules only); Untested in production |
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
| Frontend `authFetch` and auth error panel (since M3B-3, 401/403 errors keep the backend's machine-readable code and fixed message: L1 fix, section 8 L) | `frontend/src/utils/apiClient.js`, `frontend/src/utils/apiErrors.js`, `frontend/src/components/ApiAuthErrorPanel.jsx` | Repo-verified; Frontend unit tests (`apiErrors`) |
| Firestore Security Rules | [`firestore.rules`](../firestore.rules) | Emulator tests; deployed to production (owner-reported) |
| Firebase emulator mode for local development and tests (Authentication and Firestore emulators, `demo-` project, loopback only; production mode refuses emulator settings); configuration recorded at initialization and re-checked before and after every token verification. Frontend (P1-B2B/C): the React dev server uses the emulators only with `VITE_USE_FIREBASE_EMULATORS=true`, never in a production build, and then with no production configuration value | `backend/core/firebase.py`, `backend/core/auth.py`, `firebase.json`, `frontend/src/firebase.js`, `frontend/src/utils/firebaseEmulator.js` | Repo-verified; Unit tests; Frontend unit tests; Emulator integration tests (sections 8 G and J) |
| Account-access service (backend-only; its only caller is the emulator-only registration below): validates, reads and inspects `account_access/{uid}` records and creates one only if none exists, with the state taken from Firebase Authentication | `backend/services/account_access_service.py` | Repo-verified; Unit tests; Emulator integration tests (section 8 H) |
| Trusted backend registration (**local emulator testing only**; `main.py` mounts the router only when the backend starts in emulator mode, and the route answers 404 outside emulator mode; the React registration page uses it only in emulator mode, and production registration still runs in the browser): creates the Auth account with the Admin SDK, then the `users/{uid}` profile, then the active access record | `backend/services/registration_service.py`, `backend/routes/registration.py`, `backend/main.py` | Repo-verified; Unit tests; Emulator integration tests (sections 8 I and J) |
| Admin Disable & Enable student accounts (M3B-2; **local emulator testing only**: routes mounted only in emulator mode, 404 otherwise): `GET /api/admin/users/{uid}/access`, `POST .../disable`, `POST .../enable` (`require_admin`; never the caller's own account or an administrator); the access record is restricted before Auth on Disable and activated last on Enable; sessions revoked and `sessionsValidAfter` set on Enable; operation locks and audit records in backend-only collections; incomplete operations recorded and resumable; Account access panel with confirmation dialogs on User Details | `backend/services/account_action_service.py`, `backend/routes/admin_account_actions.py`, `backend/services/account_access_service.py`, `frontend/src/pages/admin/AdminUserDetail.jsx`, `frontend/src/components/admin/ConfirmDialog.jsx`, `frontend/src/utils/adminAccountActions.js` | Repo-verified; Unit tests; Frontend unit tests; Emulator integration tests (section 8 K); Manual (emulator mode, owner-reported, 26 Nov 2026: 13/13 conversational checkpoints; the planned tests only partly covered, see section 8 K); post-implementation security audit PASS WITH LIMITATIONS (local-emulator milestone; not production-ready) |
| Admin Delete Student Account (M3B-3; **local emulator testing only**: routes mounted only in emulator mode, 404 otherwise): `POST /api/admin/users/{uid}/delete` (body `{"confirm_uid"}` equal to the path uid) and `GET /api/admin/account-operations/incomplete-deletions` (`require_admin`; never the caller, an administrator, or an account without a valid access record); permanent deletion of the Auth account and `users`, `results`, `ai_assessments`, in a recoverable order with a tombstone and audit record; typed-email confirmation dialog, return to Manage Users with a notice, and an "Incomplete deletions" recovery panel; the student-data endpoints `/api/assessment/*` refuse accounts in deletion (emulator mode only) | `backend/services/account_action_service.py`, `backend/services/account_access_service.py`, `backend/routes/admin_account_actions.py`, `backend/core/student_access.py`, `backend/routes/assessment.py`, `frontend/src/pages/admin/AdminUserDetail.jsx`, `frontend/src/pages/admin/AdminUsers.jsx`, `frontend/src/components/admin/ConfirmDialog.jsx`, `frontend/src/utils/adminAccountActions.js` | Repo-verified; Unit tests; Frontend unit tests; Emulator integration tests (section 8 L); Manual: **partially verified** (owner walkthrough, 26 Nov 2026; section 8 L) |
| Browser "Seed Programs" button removed | `frontend/src/App.jsx` | Repo-verified |

Apart from the shared grade-validation helper, the Admin navigation, verification, Manage Users and
sign-out helpers, and the emulator-configuration, registration-client and access-check helpers (P1-B2B/C),
no automated tests exist for the frontend UI, recommendation scoring, RAG retrieval quality,
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
| M3B-1B-P0 — Experimental Firestore account-access guard | `d646700` | 24 Nov 2026 | 5 | Guard in the test-only `firestore-tests/account-access.experimental.rules`; shared rules-test harness; experimental suite of 100 tests (the original 44 plus 56 guard tests). Production `firestore.rules` unchanged and not deployed (section 8 F). |
| M3B-1B-P1-A — Firebase Authentication emulator foundation | `7ec0ecb` | 24 Nov 2026 | 7 | Authentication emulator on `127.0.0.1:9099`; explicit backend emulator mode (`demo-` project, loopback hosts, anonymous credential); production mode refuses emulator settings; immutable record of the initialised configuration, re-checked before and after every token verification (503 on mismatch); 31 new backend unit tests and 14 emulator integration tests (section 8 G). |
| M3B-1B-P1-B1 — Backend account-access record service | `6e3675f` | 24 Nov 2026 | 4 | Backend-only service that validates, reads and inspects `account_access/{uid}` records and creates one only if none exists (atomic create, state from Firebase Authentication, never overwrites); no route; 23 new backend unit tests and 9 emulator integration tests (section 8 H). |
| M3B-1B-P1-B2A — Trusted backend registration (emulator only) | `29fcdd3` | 24 Nov 2026 | 5 | Backend service and route that create the Auth account (Admin SDK), then the `users/{uid}` profile, then the active access record; strict input validation that never repeats the input; a partial failure disables the new account and returns 503 `REGISTRATION_INCOMPLETE`; router not mounted, 404 outside emulator mode; 24 new backend unit tests and 13 emulator integration tests (section 8 I). |
| M3B-1B-P1-B2B/C — Local account integration (emulator only), with the JL9 password fix | `7936909` | 26 Nov 2026 | 15 | Registration route mounted only in emulator mode; React dev server on the emulators only with `VITE_USE_FIREBASE_EMULATORS=true`; emulator-mode registration through the backend and a login-time access check; password rule on both registration paths (6–128 characters, no control characters); 9 emulator integration tests; owner browser walkthrough 11/11 (section 8 J). |
| M3B-2 — Admin Disable & Enable accounts (emulator only) | `e5e41a6` | 26 Nov 2026 | 14 | Disable and Enable routes mounted only in emulator mode; coordinated with the access record; operation locks, audit records, resumable incomplete operations; Account access panel; 42 backend unit and 10 emulator integration tests, 22 frontend unit tests (section 8 K). |
| M3B-3 — Admin Delete Student Account (emulator only) | **Not committed** | 26 Nov 2026 | — | Permanent, recoverable deletion of student accounts and their `users`, `results` and `ai_assessments` documents; tombstone and audit; recovery list; student-data endpoints refuse accounts in deletion (emulator mode); L1 fixed; 38 backend unit, 14 emulator integration and 19 frontend unit tests; owner browser walkthrough partially verified the plan (D4, D5 and D13 incomplete); post-implementation audit PASS WITH LIMITATIONS; local-emulator development milestone only, not production-ready (section 8 L). |

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
- **M3B-1B-P1-A (local emulator foundation, with the runtime configuration check):** backend tests — 94
  tests, `OK` (the existing 63 and 31 new Firebase configuration tests); emulator integration tests
  (separate command, section 8 G) — 14 tests, `OK`; frontend unit tests — 84 passed; Firestore rules —
  44/44 (production) and 100/100 (experimental); configuration mutation check — 17 of 17 weakened copies
  detected.
- **M3B-1B-P1-B1 (backend account-access service, not connected):** backend tests — 117 tests, `OK` (the
  existing 94 and 23 new service tests); emulator integration tests — 23 tests, `OK` (the existing 14 and 9
  new); frontend unit tests — 84 passed; Firestore rules — 44/44 (production) and 100/100 (experimental);
  the emulator concurrency test repeated 10 times (scratch run) — one record created per run, no
  unconfirmed outcome.
- **M3B-1B-P1-B2A (trusted backend registration, emulator only):** backend tests — 141 tests, `OK` (the
  existing 117 and 24 new registration tests); emulator integration tests — 36 tests, `OK` (the existing
  23 and 13 new); frontend unit tests — 84 passed; Firestore rules — 44/44 (production) and 100/100
  (experimental); the registration module repeated 3 times and run in reverse module order (scratch run,
  before the final audit added one test) — all passed.
- **M3B-1B-P1-B2B/C (local account integration, emulator only; not committed when recorded):** backend
  tests — 142 tests, `OK` (one registration test split into two); emulator integration tests — 45 tests,
  `OK` (the existing 36 and 9 new), in two full runs; an earlier full run stopped in module set-up when the
  emulator reset request timed out after 10 seconds, and the immediate re-run passed (not reproduced since;
  see JL8); frontend unit tests — 109 passed (the existing 84 and 25 new); Firestore rules — 44/44
  (production) and 100/100 (experimental); frontend production build — passed; lint of the changed
  frontend files — passed, except the unused `React` import in `Register.jsx`, which predates this milestone
  (E6) and was left unchanged; bundle scan — section 8 J. Browser verification — **in progress** (owner;
  step M5 found a defect, section 8 J). After the M5 password-length fix (26 Nov 2026, section 8 J): backend tests — 146 tests, `OK` (4 new);
  frontend unit tests — 115 passed (6 new); emulator integration and Firestore rules not re-run (backend
  source unchanged).
  **Final pre-commit audit (26 Nov 2026), all suites re-run after the owner's browser walkthrough:** backend
  tests — 146 tests, `OK`; emulator integration tests — 45 tests, `OK`; frontend unit tests — 115/115;
  Firestore rules — 44/44 (production) and 100/100 (experimental); frontend production build — passed (bundle
  scan unchanged; `DEV` inlined as false and the emulator flag unset); lint of the changed frontend files —
  passed (the pre-existing `Register.jsx` error unchanged). Manual browser walkthrough in emulator mode
  (owner-reported) — 11/11 steps passed, with the limitations recorded in section 8 J.
  **JL9 password policy change (26 Nov 2026; control characters refused):** backend tests — 151 tests, `OK`
  (5 new); emulator integration tests — 45 tests, `OK`; frontend unit tests — 120/120 (5 new); Firestore
  rules — 44/44 (production) and 100/100 (experimental); frontend production build — passed; lint of the
  changed frontend files — passed (pre-existing `Register.jsx` error unchanged); owner browser retest pending.
- **M3B-2 (Admin Disable & Enable, emulator only; not committed when recorded):** backend tests — 193 tests,
  `OK` (42 new); emulator integration tests — 55 tests, `OK` (the existing 45 and 10 new; the new module
  passed 3 consecutive runs); frontend unit tests — 142/142 (22 new); Firestore rules — 44/44 (production)
  and 100/100 (experimental), unchanged rules; frontend production build — passed (bundle scan unchanged);
  lint of the changed frontend files — passed; mutation check — 17 of 17 weakened copies detected; end-to-end
  HTTP check against scratch emulators — passed. The emulator suites ran on alternative ports through a
  scratch configuration outside the repository, because the owner's own emulators were running (section 8 K).
  Browser verification — not yet performed when these results were recorded; **owner browser walkthrough
  on 26 Nov 2026: 13/13 conversational checkpoints passed** (owner-reported). They do not map one-to-one to the
  13 planned tests: 3 verified, 7 partially verified, 1 not verified, 2 automated tests only (section 8 K).
  **Post-implementation security audit (26 Nov 2026, read-only): PASS WITH LIMITATIONS.** Re-run during the
  audit: backend tests — 193 tests, `OK`; frontend unit tests — 142/142; lint of the changed frontend files —
  passed; emulator integration tests — 55 tests, `OK`; Firestore rules — 44/44 and 100/100 (scratch ports);
  mutation check — 17 of 17 detected; frontend production build — passed; a scratch probe of refresh tokens
  after Enable (finding M3). Findings M1–M3 (Medium) and L1–L7 (Low) are open (section 8 K).
- **M3B-3 (Admin Delete Student Account, emulator only; not committed when recorded):** backend tests — 231
  tests, `OK` (the existing 193 and 38 new); emulator integration tests — 69 tests, `OK` (the existing 55 and
  14 new), in repeated full runs; frontend unit tests — 161/161 (19 new); Firestore rules — 44/44 (production)
  and 100/100 (experimental), unchanged rules; mutation check — backend 32 of 32 and frontend 13 of 13 weakened
  copies detected; frontend production build — passed (bundle scan: no provider secret); lint of the changed
  frontend files — passed. Emulator suites on alternative ports (scratch configuration), as for M3B-2.
  Browser verification — not yet performed when these results were recorded. **Owner browser walkthrough on
  26 Nov 2026 (owner-reported): of the 14 planned tests, 5 verified, 8 partially verified, 1 not verified (D13);
  D4 and D5 incomplete; the original plan was not fully completed** (section 8 L). Saving S3's results in the
  app opened the AI-assessment page, so the AI generation workflow was triggered. The three ChromaDB files were
  rewritten at that time (confirmed); an external AI provider request is not verified. The test plan has been
  corrected (section 8 L, DA1).
  **Post-implementation security audit (26 Nov 2026, read-only): PASS WITH LIMITATIONS.** Re-run during the
  audit: backend tests — 231 tests, `OK`; emulator integration tests — 69 tests, `OK` (two consecutive runs);
  frontend unit tests — 161/161; Firestore rules — 44/44 and 100/100 (scratch ports); mutation check — 32 of 32
  and 13 of 13 detected; lint and production build — unchanged. A scratch nested-data probe against a real
  scratch emulator passed 2/2. Findings: DA1 (Medium; test plan, corrected) and DA2–DA7 (Low) (section 8 L).
  Acceptable only as a local-emulator development milestone; not production-ready.

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
| S4 | Incomplete account deletion. Profile deletes `users/{uid}`, then the Auth user; `results/{uid}` and `ai_assessments/{uid}` remain (owners cannot delete them under the rules). The Admin deletion (M3B-3, local emulators only, section 8 L) removes all three documents and the Auth account; the student self-delete is unchanged. | `Profile.jsx`, `firestore.rules` | Medium | Student self-delete through a protected backend endpoint (section 8 J fixes) before production |
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

- **Read-only.** No M3A endpoint changes accounts, profiles, claims or sessions. The account actions
  (disable, enable, delete) are separate M3B routes that exist only in local emulator mode (sections 8 K and L).
  A deleted account no longer appears in this Auth-based list; an unfinished deletion whose Auth account is
  already gone is listed under "Incomplete deletions" (section 8 L).
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
| — | **M3B — Account actions** | Disable, enable and delete accounts. | **M3B-2 Disable & Enable** (section 8 K) and **M3B-3 Delete** (section 8 L, not yet committed; browser walkthrough partially verified; audit PASS WITH LIMITATIONS): implemented for the local emulators only; not usable in production until the production blockers in sections 8 J, K and L are met. The student self-delete fix (S4, FL6) and S5/W1 remain. |
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
The preconditions for the Disable, Enable and Delete actions, the required student self-delete fixes and
the minimum reconciliation are listed in [section 8 J](#j-m3b-1b-p1-b2bc--local-account-integration-emulator-only).
M3B-2 (Disable and Enable) is implemented for the local emulators ([section 8 K](#k-m3b-2--admin-disable--enable-accounts-emulator-only)),
and so is M3B-3 (Admin Delete Student Account, [section 8 L](#l-m3b-3--admin-delete-student-account-emulator-only)). M3B-3 was
partially verified by the owner in the browser (D4, D5 and D13 incomplete) and audited (PASS WITH LIMITATIONS). It is
acceptable only as a local-emulator development milestone and is pending commit. The remaining M3B work is the student self-delete fix (S4, FL6) and the
production blockers listed in sections 8 J, K and L.
M1.5C remains deferred: OCR is not operational and manual results entry remains supported. Before OCR
returns or any public deployment: rotate or revoke the previously exposed key(s), remove the unused
`VITE_OLLAMA_URL` from `frontend/.env`, resolve the Ollama base-URL discrepancy, complete the
provider-terms and privacy review (S1, S10, S11), and implement M1.5C.
Start M3B only at step 1 (inspect and plan) of the milestone workflow in [CLAUDE.md](../CLAUDE.md).

## 8. Admin Module — Fail-Closed Security & Testing Register

A living technical record of the security behaviour of the completed Admin milestones (M1, M1.5A,
M1.5B, M2, M3A and the Admin sign-out hardening), of the experimental, **undeployed** M3B-1B-P0
account-access guard (section F), of the M3B-1B-P1-A local emulator foundation (section G) and of the
backend-only M3B-1B-P1-B1 account-access service (section H), of the emulator-only M3B-1B-P1-B2A
trusted registration (section I), of the emulator-only M3B-1B-P1-B2B/C local account integration
(section J), of the emulator-only M3B-2 Disable & Enable account actions (section K) and of the
emulator-only M3B-3 Delete Student Account action (section L), based on the repository code and the
recorded test results. It is **not** the final Development and Testing Report.
Last recorded: 26 November 2026 (MYT).

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
- **Emulator integration**: backend tests in `backend/integration_tests/` against the local Firebase
  Authentication and Firestore emulators (M3B-1B-P1-A).
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
| Backend unit tests | `test_auth.py` (26), `test_admin_users.py` (37), `test_firebase_config.py` (31), `test_account_access_service.py` (23), `test_registration.py` (34), `test_account_actions.py` (42), `test_account_deletion.py` (38) | 231 tests, `OK` |
| Backend emulator integration tests (M3B-1B-P1-A, P1-B1, P1-B2A, P1-B2B/C, M3B-2, M3B-3) | `backend/integration_tests/`: `test_auth_emulator.py` (14), `test_account_access_service.py` (9), `test_registration_emulator.py` (13), `test_local_account_flow.py` (9), `test_account_actions_emulator.py` (10) and `test_account_deletion_emulator.py` (14) against the Authentication and Firestore emulators (`demo-route2unikl`), separate command (section G) | 69 tests, `OK` |
| Frontend unit tests | `gradeEntry` (18), `adminNavigation` (11), `adminVerification` (13), `adminUsers` (24), `signOutFlow` (18), `firebaseEmulator` (8), `registrationApi` (22), `accountAccess` (6), `adminAccountActions` (36), `apiErrors` (5) | 161/161 passed |
| Firestore emulator tests (production rules) | `firestore-tests/rules.test.mjs` against `firestore.rules`, run by `npm test` (12 suites, defined in `shared-rules-suite.mjs`) | 44/44 passed |
| Firestore emulator tests (experimental, M3B-1B-P0) | `firestore-tests/account-access.experimental.suite.mjs` against the test-only `account-access.experimental.rules`: the same 44 tests plus 56 guard tests (section F) | 100/100 passed |
| Mutation testing (experimental, M3B-1B-P0) | The experimental suite re-run against deliberately weakened copies of the experimental rules (section F) | 19 of 20 weakenings detected; the undetected one removes a redundant check |
| Mutation testing (configuration, M3B-1B-P1-A) | `test_firebase_config.py` re-run against deliberately weakened copies of `backend/core/firebase.py` and `backend/core/auth.py` (section G) | 17 of 17 weakenings detected |
| Mutation testing (account deletion, M3B-3) | The account-action and deletion unit tests against weakened in-memory copies of the services, routes and student-data check; the helper tests against weakened scratch copies of the frontend helpers (section L) | Backend 32 of 32, frontend 13 of 13 detected |
| Frontend build and lint | Production build; lint of the changed files with zero warnings allowed | Passed (pre-existing project-wide lint issues: see E6) |
| Manual (owner-reported) | M3A Manage Users browser verification | 10/10 |
| Manual (owner-reported) | Admin sign-out hardening browser regression checks | 5/5 |
| Manual (owner-reported) | M3B-1B-P1-B2B/C local walkthrough in emulator mode, steps M1–M11 (section J) | 11/11 passed, with limitations (M7, M10, M11; section J); one defect found in M5 and fixed |
| Manual (owner-reported) | M3B-2 local walkthrough in emulator mode: 13 conversational checkpoints, mapped to the 13 planned tests (section K) | 13/13 conversational checkpoints passed. Planned tests: 3 verified, 7 partially verified, 1 not verified, 2 automated tests only. Firestore rules rejection, audit-record contents and old refresh-token behaviour after Enable not manually verified (section K) |
| Manual (owner-reported) | M3B-3 Delete Student Account in emulator mode (plan D1–D14, section L) | **Partially verified** (26 Nov 2026): 5 verified, 8 partially verified, 1 not verified (D13); D4 and D5 incomplete; the original plan was not fully completed |
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
| E7 | M3B account actions: Disable and Enable (M3B-2, section K) and Delete (M3B-3, section L) are implemented for the local emulators only; the student self-delete is unchanged, so S4 (self-delete) and S5 remain open. | Future development task | Production use pending the blockers in sections J, K and L; M3B-3 browser verification partial (D4, D5 and D13 incomplete; section L). |
| E8 | A retry from the Admin layout's "Couldn't sign you out" panel is not tied to a verification run; in a rare overlap, a late failure could block a screen that had just been verified again. | Usability problem | Fails closed. Open. |
| E9 | A failed manual Admin logout uses an alert and re-verification instead of the shared failure panel. | Usability problem and future development task | Open. |
| E10 | Manage Users does not detect Firestore profiles without an Auth account, and scans at most 2,000 accounts per request (reported, not hidden). | Future development task | Open (section 5). |

Other project-wide security items (S1–S11) are tracked in [section 5](#5-known-limitations-and-technical-debt).
This register does not claim that every edge case is resolved.

### F. M3B-1B-P0 — Experimental Firestore Account-Access Guard

> **Status: experimental proof of concept (committed in `d646700`), NOT deployed.** The production rules
> file `firestore.rules` is unchanged (byte-identical to `69bcc07`), and production Firestore has no account-access guard. The
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
| FL6 | Student self-delete (`Profile.jsx`) still deletes from the browser and does not use the guard; S4 remains open. | Future development task | Pending. The Admin deletion (M3B-3, section L) does not change the self-delete (DL5). |
| FL7 | Firebase does not document the ordering between a rules check and a simultaneous change to the record; a write made just before an account is disabled may still be saved. The emulator tests include no concurrency testing. | Security limitation (residual) | Not yet tested. |
| FL8 | The guard does not apply to the FastAPI backend, which uses the Admin SDK (rules do not apply) and relies on its own token checks (section A). | Boundary (by design) | — |
| FL9 | The emulator is not production: rules-engine details, token contents, billing and latency may differ. | Test-coverage gap | Open. |

### G. M3B-1B-P1-A — Firebase Authentication Emulator Foundation

> **Status: committed in `7ec0ecb`. Local development and test infrastructure, plus configuration
> hardening of the backend's Firebase initialisation and token verification (G1, G2, G7, G8).** Token verification itself, `check_revoked=True`,
> the error mapping and `require_admin` are unchanged. No deployment, production data, real account or
> custom claim was involved. Emulator results are not production evidence.

**Purpose.** Account-management work (M3B) must be developed and tested without touching real accounts.
P1-A adds the Firebase Authentication emulator next to the existing Firestore emulator, adds an explicit
backend emulator mode, and tests the existing backend authentication against emulator-created accounts.

**Configuration.** `backend/core/firebase.py` selects the mode with `ROUTE2UNIKL_FIREBASE_MODE`:

| Setting | Production mode (default) | Emulator mode |
|---|---|---|
| `ROUTE2UNIKL_FIREBASE_MODE` | Unset or `production` | `emulator`. Any other value is refused. |
| `ROUTE2UNIKL_EMULATOR_PROJECT_ID` | Must not be set | Required: a `demo-` project ID, for example `demo-route2unikl` |
| `FIREBASE_AUTH_EMULATOR_HOST`, `FIRESTORE_EMULATOR_HOST` | Must not be set | Both required: a loopback `host:port` (`127.0.0.1`, `localhost` or `[::1]`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Not checked (unchanged) | Must not be set |
| `GOOGLE_CLOUD_PROJECT`, `GCLOUD_PROJECT` | Not checked (unchanged) | If set, must equal the emulator project ID |
| Credential | `backend/serviceAccountKey.json` (unchanged) | An anonymous emulator credential: no key file, no application-default credentials |

`firebase.json` adds the Authentication emulator on `127.0.0.1:9099`; the Firestore emulator stays on
`127.0.0.1:8080`. The emulator integration tests are run from `backend/` with:

```
firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\Scripts\python.exe -m unittest discover -s integration_tests -t . -v"
```

They are kept outside `backend/tests/`, so the default backend command never needs or starts an emulator.

**Running the backend against the emulators** (local only): set the emulator-mode variables above and
start the server bound to the loopback interface, for example `uvicorn main:app --host 127.0.0.1 --port 8000`
(127.0.0.1 is uvicorn's default; never `--host 0.0.0.0`). An emulator-mode backend accepts forged tokens
(GL2), so it must not be reachable from other machines.

**Token verification: emulator versus production.** In production mode the Admin SDK checks the token's
RS256 signature against Google's keys, its key ID, expiry, audience, issuer and subject, and then, with
`check_revoked=True`, the account's disabled state and revocation time. In emulator mode the SDK skips the
signature and expiry checks; audience, issuer, subject, disabled state and revocation are still checked,
against the emulator. The real production verifier is exercised offline by a unit test that rejects
unsigned, wrong-algorithm and wrong-project tokens before any network request.

| # | Protection | Implementation | Evidence |
|---|---|---|---|
| G1 | Production initialisation | With the mode unset or `production`, the first initialisation loads the same key file and initialises the app exactly as before. Later calls validate and reuse the app this module created without reloading the key; an app created elsewhere in the process is refused (G7). | Backend unit; Code inspection |
| G2 | Production mode refuses emulator settings | The Admin SDK reads `FIREBASE_AUTH_EMULATOR_HOST` and `FIRESTORE_EMULATOR_HOST` itself, and while the Auth variable is set it skips ID-token signature and expiry checks. Production mode therefore raises `FirebaseConfigError` if either host or the emulator project variable is present, before loading the key. Token verification then answers 503 `AUTH_SERVICE_UNAVAILABLE` without verifying any token. | Backend unit (every emulator setting, with and without an explicit `production` mode; 503 through the real `get_current_user`); Emulator integration (test 10; the limitation test shows a forged token being accepted when the variable is set) |
| G3 | Emulator mode accepts only a complete, isolated configuration | Requires a `demo-` project and loopback hosts for both emulators; refuses application-default credentials, a conflicting Google project, an unknown mode and an existing non-emulator app. Any failure raises; there is no fallback to production. Error messages and logs name variables, never their values. | Backend unit; Emulator integration (test 10: five invalid configurations → 503, no app created, no request made); configuration mutation check (17 of 17 weakenings detected, covering G2, G3, G7 and G8; scratch scripts, not stored in the repository) |
| G4 | No real credentials or production project in emulator mode | Anonymous credential; the test run replaces the key loader with one that fails if called; the app's project is the `demo-` project; the Firestore client uses the emulator host; every recorded HTTP request went to a loopback address. | Emulator integration (test 9, plus a check of all request hosts when the run ends) |
| G5 | Emulators bound to loopback only | `firebase.json` hosts are `127.0.0.1`. One check during a scratch run showed every emulator socket listening on `127.0.0.1` (the emulator hub also on `[::1]`). | Code inspection (`firebase.json`); one observation during a scratch run, not stored in the repository |
| G6 | Existing backend authentication behaves as expected against the Auth emulator | New account signed in through the emulator → `/api/auth/me` 200. Missing, malformed, wrong-project or unknown-account tokens → 401. Student or string `"true"` claim → 403 on `/api/admin/verify` and both Manage Users endpoints. `admin: true` (new token) → 200, and Manage Users lists emulator accounts with their Firestore-emulator profiles; a token issued before the claim was set → 403. Disabled → 403 "This account has been disabled.", and sign-in and token refresh fail. Deleted → 401 "Account not found", and sign-in fails. Revoked → tokens issued before the revocation → 401 "Session revoked"; a new sign-in → 200. | Emulator integration (tests 1–8) |
| G7 | Immutable record of the initialised configuration | The first successful `initialize_firebase()` records a frozen `FirebaseConfig` (mode, project ID, Auth and Firestore emulator hosts in emulator mode, credential type) and the app it created. Nothing is recorded until the app, its project and the Firestore client are all confirmed; a failure after the app was created removes that app, so a retry starts clean. The record is never overwritten: re-creating a removed app (for example in tests) requires the same configuration, including the same production project. Later `initialize_firebase()` calls accept only the recorded app under a matching environment; an app created elsewhere, a replaced app or a credential of the wrong type is refused. | Backend unit (lifecycle: failed initialisation and retry, repeated initialisation, re-creation after removal, immutability, external and replaced apps, credential mismatch); Emulator integration (test 9 checks the record; test 10 re-creates the app after removal) |
| G8 | Configuration re-checked before and after every token verification | `get_current_user` calls `check_runtime_configuration()` before verifying the token and again before accepting the verified identity. It fails if the mode, project, either emulator host or the credential type differs from the record, if production mode sees any emulator setting, if emulator settings are missing or invalid, or if the app is missing or not the recorded one. Before verification, a failure means the token is never verified; after verification, the verified identity is discarded. Both answer 503 `AUTH_SERVICE_UNAVAILABLE`; logs contain only the exception type. `/api/auth/me`, `/api/admin/verify` and both Manage Users endpoints are covered, because `require_admin` depends on `get_current_user`. Valid configurations still authenticate, and Admin claims are still enforced. | Backend unit (mismatch on all four endpoints without verification; a change during verification rejected; valid configurations and Admin claims); Emulator integration (test 11: seven changes after initialisation → 503 on student and Admin endpoints, verification never called, 200 again once restored; test 12: a change during real emulator verification → 503) |

**Emulator behaviour that differs from production or is unverified there** (asserted by two limitation
tests and the re-enable test, so that a change is noticed):

- Emulator ID tokens are unsigned (`alg: none`). With `FIREBASE_AUTH_EMULATOR_HOST` set, the Admin SDK
  accepts a forged token for an existing emulator account, including one claiming `admin: true`.
- Disabling and re-enabling an account does not change its revocation time in the emulator: after
  re-enabling, the old ID token is accepted again until refresh tokens are revoked. Account actions must
  revoke tokens when re-enabling (as in the M3B-1A design).
- After revocation, the emulator still exchanges the old refresh token for new ID tokens; Firebase
  documents that revocation ends refresh tokens in production.

**Limitations and pending work**

| # | Limitation | Type | Status |
|---|---|---|---|
| GL1 | Emulator results do not prove production behaviour (token signing, expiry, refresh-token revocation and re-enable semantics differ or are unverified). The production initialisation path was tested only with a fake credential: start-up with the real service-account key, and verification of real signed tokens, were not exercised (no production access was authorised). | Test-coverage gap | Open |
| GL2 | Emulator mode accepts forged tokens by design of the emulator. It must never be used with real data; the loopback hosts, the `demo-` project and the production refusal (G2) keep it local. | Security limitation (by design) | Accepted for local development |
| GL3 | Process-environment race: the Admin SDK reads `FIREBASE_AUTH_EMULATOR_HOST` inside each verification, and Python cannot lock the process environment. A change made after the first check and undone before the second can still affect that one verification without being detected. The two checks (G8) close every other ordering. Nothing in the code changes these variables at run time (`backend/.env` is loaded at import, before initialisation). | Security limitation (residual) | Open; accepted (see GL7) |
| GL4 | A misconfigured server still starts (`main.py` prints the error) and answers 503 on authenticated routes instead of refusing to start. | Operations | Deferred by owner decision (24 Nov 2026); `main.py` unchanged |
| GL5 | The React app was not connected to the emulators: it used production Firebase, and an emulator-mode backend rejects production tokens (wrong project). | Future development task | Addressed in P1-B2B/C: the dev server uses the emulators with `VITE_USE_FIREBASE_EMULATORS=true` (section J); owner browser walkthrough completed on 26 Nov 2026 |
| GL6 | The emulator integration tests (14 in P1-A, 23 since P1-B1, 36 since P1-B2A, 45 since P1-B2B/C) need the Firebase CLI and run with a separate command, manually (no CI). The `CLAUDE.md` commands table does not list the command, and each run leaves an untracked `backend/firestore-debug.log` (not covered by `.gitignore`), which must be deleted afterwards and never staged. | Test-process gap | Deferred by owner decision (24 Nov 2026): no `CLAUDE.md`, `.gitignore` or new ignore-file change |
| GL7 | These checks are configuration hardening against misconfiguration and accidental environment changes. They are not protection against a compromised backend process: code running inside the process can change the environment, the recorded configuration or the checks themselves. | Security limitation (by design) | Accepted |
| GL8 | A local emulator-mode backend must be bound to `127.0.0.1` (see "Running the backend against the emulators"). The code cannot enforce how the server is started. | Operations | Documented |

### H. M3B-1B-P1-B1 — Backend Account-Access Service

> **Status: committed in `6e3675f`. Backend-only service, not connected to login, migration or any
> mounted route, and not deployed.** Its only caller is the emulator-only registration of section I
> (P1-B2A), whose router is not mounted. It ran only against in-memory fakes and the local
> emulators (`demo-route2unikl`); no real account, custom claim or Firestore document was read or written.

**Purpose.** The experimental guard (section F) needs an `account_access/{uid}` record for every account.
`backend/services/account_access_service.py` is the only code that reads or creates these records. It uses
the Admin SDK through `core.firebase`, so the P1-A configuration checks (G7) apply to every call, and
Firestore Security Rules do not apply to it. The record schema is exactly the guard's: `state` (`active`,
`disabled`, `deleting` or `deleted`), `version` (integer ≥ 0) and an optional `sessionsValidAfter`
timestamp. Locks, audit history and other operational data are kept out of this collection.

**Interface** (internal Python functions; no HTTP endpoint):

| Function | What it does | Writes |
|---|---|---|
| `validate_access_record(data)` | Checks stored data against the guard's schema and returns valid, or malformed with problem codes (unknown field, missing or invalid `state` or `version`, invalid `sessionsValidAfter`). A boolean `version` or a timestamp without a time zone is invalid. | No |
| `read_access_record(uid)` | The stored record: valid, missing or malformed (never repaired). | No |
| `inspect_account(uid)` | The record together with the Firebase Authentication status, and any inconsistency between them. | No |
| `provision_access_record(uid)` | Trusted, server-only provisioning: creates the record only if none exists. | Create only |

| # | Protection | Implementation | Evidence |
|---|---|---|---|
| H1 | UID validated before any Firebase call | The Manage Users rule (`UID_PATTERN`: letters, digits, `_` and `-`, 1 to 128 characters), applied as a full match, so a trailing newline is refused. | Backend unit |
| H2 | Records only for existing Auth accounts, with the Auth status | The Auth account is read first. If it does not exist, nothing is written (`AUTH_ACCOUNT_NOT_FOUND`). An enabled account gets `{state: 'active', version: 1}`; a disabled account gets `{state: 'disabled', version: 1}`. `sessionsValidAfter` is never written. | Backend unit; Emulator integration (tests 1, 2, 6) |
| H3 | Atomic create-if-absent; existing records never modified | A single Firestore `create()`, which fails if the document exists, with automatic retries turned off. Active, disabled, deleting, deleted and malformed records, and any `sessionsValidAfter`, stay exactly as stored (in the emulator, the document's update time is unchanged). Malformed records are reported, never repaired. | Backend unit; Emulator integration (tests 3, 4, 5) |
| H4 | Concurrent and duplicate requests | Exactly one request creates the record; every other one reports the stored record with `created = false`. Firestore refuses a competing create either with "already exists" or with "aborted" (write contention), and both are handled by reading the stored record. If nothing is stored after such a refusal, the outcome is reported as unconfirmed. | Backend unit (16 threads; both refusal kinds); Emulator integration (test 7: 8 concurrent requests). A scratch run repeated test 7 ten times: 10 records created (one per run), 24 "already exists" and 46 "aborted" refusals, none unconfirmed. |
| H5 | Failures are never reported as success | `activated` is true only for a newly created `active` record whose Auth account was still enabled when checked again after the write. Errors use fixed codes: `FIREBASE_UNAVAILABLE` (initialisation or configuration), `AUTH_UNAVAILABLE`, and `STORE_UNAVAILABLE` (Firestore unavailable, a failed write, or a write whose outcome is unknown; retrying is safe because nothing is overwritten). An Auth change during provisioning (disabled, deleted or unverifiable) is reported as an inconsistency, not as an activation; the record that was written is not corrected (HL2). | Backend unit |
| H6 | Inconsistencies detected, never repaired | `inspect_account` reports: missing or malformed record; Auth account missing; Auth disabled but record active; Auth enabled but record disabled; deletion in progress; record deleted while the Auth account exists. Inspection never writes. | Backend unit (every combination); Emulator integration (test 8: account disabled, then deleted, in Auth after provisioning) |
| H7 | No public endpoint; private data not logged | Neither `main.py` nor any route references the service directly (checked by a test). Since P1-B2A, `registration_service.py` calls it, through a router that answers 404 outside emulator mode (section I) and that `main.py` mounts only in emulator mode since P1-B2B/C (section J). Logs contain the uid, codes and exception types only; an error's message is its code. Email addresses, tokens and academic data are never logged. | Backend unit |
| H8 | Emulator only | The section G harness: loopback hosts, `demo-` project, the key loader fails if called, every HTTP request on loopback. | Emulator integration (test 9) |

**Missing records.** A missing record is never treated as permission to activate an account.
`provision_access_record` takes the state from Firebase Authentication, so a disabled Auth account always
gets a `disabled` record and a missing Auth account gets none. Whether an *enabled* account without a record
should receive an `active` record is decided by the trusted caller (P1-B2). The function only guarantees that
it never overwrites a record and never contradicts the Auth status at the time of writing.

**Why there is no self-provisioning.** Registration (`Register.jsx`) creates the Auth account in the browser,
without the backend. The backend therefore has no trusted evidence that an account is newly registered: an
ID token proves only that the account exists and is enabled. A provisioning endpoint for signed-in users would
let any enabled account without a record (for example one whose record was lost) obtain an `active` record.

**Decisions for P1-B2 (unresolved)**

| Topic | Options | Recommendation |
|---|---|---|
| New registrations | (a) Backend-mediated registration: the browser sends the registration to a FastAPI endpoint that creates the Auth account with the Admin SDK and then provisions the record, so the evidence comes from the server. Needs rate limiting, input validation, a consistent "email already in use" response and a decision on handling the password on the server. (b) A Cloud Functions trigger on Auth account creation; new infrastructure, outside the current architecture. (c) A self-provisioning endpoint limited to very recently created accounts (Auth creation time and the token's `auth_time` within a short window, and no record ever stored): a heuristic, not proof. | (a), for server-side evidence within the current architecture; owner decision. Implemented for emulator testing only in P1-B2A (section I). |
| Existing accounts | A server-only backfill that calls `provision_access_record` for every Auth account, with a dry-run mode and separate approval before any production write (M3B-1A migration plan). | As planned. |
| Login | Report a missing record (for monitoring) without creating one. | Never create a record from login. Since P1-B2B/C, login (browser and backend) is tested not to create or change a record (section J, J5). Monitoring is not implemented. |
| Self-delete | `Profile.jsx` still deletes from the browser and does not touch the record (FL6). | Move to the backend with M3B; required fixes in section J. |
| Reconciliation (HL2, HL5) | Minimum safe approach: a downgrade-only correction in a Firestore transaction. Re-read Auth and the record; if Auth is disabled or missing and the record is still `active` with the version that was read, set `state: 'disabled'` and increment `version`, keeping `sessionsValidAfter`. Never upgrade a record, never touch `deleting` or `deleted`, and never write a record that changed in the meantime. Run it immediately when provisioning reports `AUTH_DISABLED_RECORD_ACTIVE`, `AUTH_ACCOUNT_MISSING` or `AUTH_STATE_UNVERIFIED`, and as a scheduled sweep over all accounts. Coordinated account actions (M3B) restrict the record before changing Auth, so they never open the window; changes made directly in the Firebase console are caught only by the sweep. | Required before the guard is deployed; to be designed with the M3B operation and lock model (not implemented). |

**Limitations**

| # | Limitation | Type | Status |
|---|---|---|---|
| HL1 | Not connected in production: no login, migration or production route calls the service (the registration router is mounted only in emulator mode, section J), and the guard is not deployed, so P1-B1 changes nothing in production. | Future development task | Open; connected locally in P1-B2B/C (emulator only). Production needs the requirements in section J. |
| HL2 | Auth lifecycle race during provisioning: if the account is disabled or deleted in Auth after the first Auth lookup but before the write, the new record stays `active` (confirmed on the emulators in a scratch run). The second Auth check reports it (`activated = false`, issue `AUTH_DISABLED_RECORD_ACTIVE` or `AUTH_ACCOUNT_MISSING`), but nothing corrects the record. Once the guard is deployed, such a record would let that account's existing browser session keep Firestore access to its own documents until its ID token expires (up to one hour); the backend still rejects the account, and it cannot sign in again. | Security limitation (lifecycle consistency) | Open; reconciliation required before the guard is deployed (see "Reconciliation" above) |
| HL3 | A write that times out is reported as `STORE_UNAVAILABLE` even if it was stored; the retry then reports the stored record with `created = false`, so the caller cannot always tell that its own earlier attempt created it. | Operations | Accepted (never reported as success) |
| HL4 | Emulator results are not production evidence (Firestore contention behaviour, latency, Auth propagation). | Test-coverage gap | Open |
| HL5 | Auth changes after provisioning: Firebase Authentication and Firestore cannot be updated atomically. An account disabled or deleted after the last Auth check (for example in the Firebase console) keeps its `active` record, and provisioning has correctly reported success because the record matched Auth when checked (confirmed on the emulators in a scratch run). `inspect_account` detects the mismatch afterwards. Same consequence as HL2. | Security limitation (lifecycle consistency) | Open; same reconciliation |

### I. M3B-1B-P1-B2A — Trusted Backend Registration (Emulator Only)

> **Status: committed in `29fcdd3`, for local emulator testing only; not deployed.** At that commit,
> `main.py` did not include `backend/routes/registration.py`. Since P1-B2B/C (section J), `main.py`
> mounts it only when the backend starts in Firebase emulator mode, and the React registration page uses
> it only in emulator mode; a production-mode backend has no registration endpoint. Even when mounted, the
> route answers 404 outside Firebase emulator mode without touching Firebase. All evidence comes from
> in-memory fakes and the local emulators (`demo-route2unikl`); no real account, custom claim or Firestore
> document was read or written.

**Purpose.** Option (a) of the P1-B2 decisions (section H): the server creates the Firebase Authentication
account itself, so it knows the account is new, and only then provisions the account's access record. An ID
token is never used as evidence that an account is new.

**Workflow** (`backend/services/registration_service.py`; `POST /register` in `backend/routes/registration.py`):

1. Validate the request: exactly `name`, `email`, `password` and `role`, all strings; any other field (a
   uid, claims, flags, an access state) is refused. `name`: 1–100 characters, no control characters.
   `email`: up to 254 characters in a conservative address format (Firebase checks it again). `password`:
   6–128 characters (Firebase's minimum; Firebase stores the password); since the JL9 change (section J), no
   Unicode control characters (category `Cc`), never trimmed. `role`: `spm_leaver` or `form_4_5`
   (the Manage Users `STUDENT_TYPES`). The body is limited to 4 KB.
2. Create the Firebase Authentication account with the Admin SDK (`create_user`: enabled, email not
   verified). Firebase chooses the uid. An email already in use is refused (409) before anything is written.
3. Create `users/{uid}` (approved by the owner on 24 Nov 2026) with exactly the fields the registration rule requires: `name`, `email` (as
   Firebase stored it), `role` and `createdAt` (server time). Created only if absent.
4. Provision the access record through `provision_access_record` (section H), last, so the Firestore guard
   opens only for a complete account.
5. Report success (201, body `{"status": "registered"}`) only if provisioning reports `activated`: a
   newly created `active` record whose account was still enabled when checked after the write.

| # | Protection | Implementation | Evidence |
|---|---|---|---|
| I1 | Evidence that the account is new comes from the server | Steps 3 and 4 use the uid that `create_user` returned in the same operation; a caller cannot supply a uid. An email already in use is refused before any write, so registration can never modify or activate an existing account, whatever its access record. | Backend unit; Emulator integration (tests 1, 3, 4) |
| I2 | Strict input; no privileged fields | Unknown fields → 422 (`unexpected_field`); wrong types refused; `admin` and every other role refused. Invalid input never reaches Firebase. | Backend unit; Emulator integration (test 2) |
| I3 | Passwords never disclosed | The route validates the body itself, because FastAPI's default 422 response repeats the submitted input. Responses carry a code and invalid field names only. The password is held as a secret value, passed only to `create_user`, and never stored, logged, returned or put into an exception. Firebase error messages (which can contain the email) are never logged; logs contain the uid, the step and codes only. | Backend unit (password, name and email sentinels never in logs, errors or responses); Emulator integration (test 11: logs, responses and stored documents) |
| I4 | Success only when confirmed | 201 only after an activated access record. | Backend unit; Emulator integration (tests 1, 7–9) |
| I5 | Partial failures never return success, and the new account is disabled when possible | If the profile or the access record cannot be created, a record unexpectedly exists, or Auth changes during provisioning, the service tries to disable the account just created (never deletes it) and returns 503 `REGISTRATION_INCOMPLETE`. The uid is logged for recovery, never returned. If disabling fails, the account stays **enabled**: the error log records `account_disabled=False`, and nothing retries it automatically. A retry of the request gets 409 and never completes or re-enables the account. | Backend unit (including a failed disable); Emulator integration (tests 7–9: account disabled, sign-in refused with `USER_DISABLED`; test 7: a retry gets 409 and the account stays disabled) |
| I9 | The server-written profile matches the student schema | `users/{uid}` has exactly `name`, `email` (equal to the ID token's email claim), `role` and `createdAt` (a timestamp), for both roles. Under the deployed production rules, the student can read it and make the app's next profile update with their own token; changing the role is refused, and another student cannot read it. | Emulator integration (test 13: Firestore emulator enforcing `firestore.rules`) |
| I6 | Duplicate and concurrent requests | Firebase Authentication enforces unique emails: one request creates the account, the others get 409; no second account, profile or record. | Backend unit (16 threads); Emulator integration (tests 5 and 6: 8 concurrent requests) |
| I7 | Not exposed | `main.py` mounts the router only when the backend starts in emulator mode (since P1-B2B/C; checked by a test with an unset, `production`, unknown and emulator mode, and on the real application in `test_local_account_flow.py` test 8, section J). Outside emulator mode the route answers 404 without touching Firebase or calling the registration service. If the emulator configuration is not ready, or Firebase was initialised in production mode even though the environment claims emulator mode, it answers 503 without calling the service. | Backend unit (service spy; real readiness check); Emulator integration (test 10: service spy, no account created) |
| I8 | Emulator only | The section G harness: loopback hosts, `demo-` project, the key loader fails if called, every HTTP request on loopback. | Emulator integration (test 12) |

**Partial registration outcomes**

| Failure | State left behind | Response | Recovery |
|---|---|---|---|
| Invalid input; email in use | Nothing created or changed | 422; 409 | — |
| Auth account creation fails, or its outcome is unknown | Possibly an enabled account without profile or record; its uid is not known | 503 `REGISTRATION_UNAVAILABLE` | A retry gets 409 if the account exists. An administrator finds it by email (`inspect_account` reports `RECORD_MISSING`) and completes or removes it. With the guard deployed, the missing record already denies Firestore access. |
| Profile cannot be created | Account disabled; no profile; no record | 503 `REGISTRATION_INCOMPLETE` | An administrator completes the registration (profile, record, enable) or removes the account. |
| Access record fails, or its outcome is unknown | Account disabled; profile; no record, or an `active` record if a timed-out write was stored (HL2, HL3) | 503 `REGISTRATION_INCOMPLETE` | As above; reconciliation (section H) would downgrade an `active` record. |
| A record unexpectedly exists; Auth changes during provisioning | Account disabled; profile; the record as found, or an `active` record written meanwhile (HL2) | 503 `REGISTRATION_INCOMPLETE` | As above. |
| The account cannot be disabled | Account **still enabled**; partial data; not restricted | 503 `REGISTRATION_INCOMPLETE`, the same response as above; the error log records `account_disabled=False` | Nothing retries the disable. An administrator must find the account from the error log and handle it manually; until then the account can sign in and use the backend (with the guard deployed, a missing record would still deny Firestore access). |
| Response lost after success | Complete, enabled account | No response reaches the client; a retry gets 409 | The student signs in successfully. |

A lost success response and an incomplete registration both make a retry return 409, but they differ: after a
lost response the account is complete and sign-in succeeds; after an incomplete registration the first
response was 503 and the account is disabled, so sign-in fails with `USER_DISABLED` (unless disabling itself
failed, above).

Recovery is manual and not guaranteed: completing or removing an incomplete registration needs the M3B
account actions or a separately approved server-side tool, and depends on an administrator acting on the
logs. Accounts are never deleted automatically.

**Abuse prevention and production prerequisites** (assessment only; nothing below is implemented, because
the route is not exposed):

- The Admin SDK's `create_user` is not subject to the per-IP sign-up limits Firebase applies to browser
  sign-ups, so the backend must add its own before exposure: rate limits per client and per email, kept in
  a shared store rather than process memory; bot protection (for example Firebase App Check or reCAPTCHA);
  and monitoring of incomplete registrations.
- HTTPS only, with CORS limited to the frontend's origin.
- A 409 reveals whether an email is registered, as Firebase's own sign-up error does unless its
  email-enumeration protection is enabled. A uniform response needs another way to inform the student,
  such as email verification (owner decision).
- Password policy: Firebase's minimum of 6 characters is kept for consistency with the current app; a
  stronger policy is an owner decision.

**Owner decisions for this milestone (24 Nov 2026) and deferred production requirements.** Before the route
may be mounted or exposed, each deferred item needs a separate, approved change:

| Item | Decision for P1-B2A | Required before exposure |
|---|---|---|
| Profile creation | Registration creates `users/{uid}` (approved). | — |
| Duplicate email | 409 `EMAIL_IN_USE`, for emulator testing only. | Decide whether to keep 409 or use a uniform response (IL4). |
| Password minimum | Firebase's 6 characters, for compatibility. | Decide the production password policy. |
| Rate limiting and bot protection | Deferred. | Implement per-client and per-email rate limits in a shared store, and bot protection (IL2). |
| HTTPS and CORS | Deferred. | HTTPS only; CORS limited to the frontend's origin. |
| Incomplete registrations | Manual recovery. | An approved recovery procedure or tool, and monitoring of the logs (IL3). |
| Auth/Firestore reconciliation | Not implemented here. | Reconciliation (section H) before the guard is deployed (IL5). |
| Mounting the route | Not mounted. Since P1-B2B/C (approved): mounted only in emulator mode. | A separately approved change to mount it in production mode. |

**Limitations**

| # | Limitation | Type | Status |
|---|---|---|---|
| IL1 | Not exposed or integrated: there is no live registration endpoint, and the frontend still registers in the browser. | Future development task | Integrated locally in P1-B2B/C (emulator mode only, section J); still not exposed in production |
| IL2 | No rate limiting or bot protection. | Security limitation (must be resolved before exposure) | Open |
| IL3 | Incomplete registrations need manual administrator recovery, which is not guaranteed. An account whose creation outcome is unknown cannot be restricted automatically (its uid is unknown), and an account whose disable failed stays enabled until someone acts on the error log. | Operations | Open; manual recovery accepted for this milestone |
| IL4 | A 409 reveals that an email is registered. | Privacy | Kept for emulator testing (owner decision); decide before exposure |
| IL5 | The HL2 race applies: an access record written while Auth changes stays `active`. The account is disabled, but the record is not downgraded until reconciliation exists. | Security limitation (lifecycle consistency) | Open (section H reconciliation) |
| IL6 | Emulator results are not production evidence (Auth quotas, latency, email normalisation, password policy). | Test-coverage gap | Open |

### J. M3B-1B-P1-B2B/C — Local Account Integration (Emulator Only)

> **Status: implemented for the local Firebase emulators only; not deployed; production behaviour
> unchanged. Owner browser walkthrough in emulator mode completed on 26 Nov 2026: 11 of 11 steps passed,
> with the limitations recorded under "Owner browser verification results"; step M5 first found a defect,
> fixed in the frontend (see "Defect found in browser verification").** A production-mode backend has no
> registration route, and a production build of the React app never uses the emulators or the backend
> registration. Evidence comes from unit tests, the emulator integration tests, the owner's browser
> walkthrough (emulator mode) and scratch checks
> against the local emulators (`demo-route2unikl`); no real account, custom claim, Firestore document or
> rules deployment was involved.

**Purpose.** Connect the pieces of P1-A, P1-B1 and P1-B2A into one local student flow (registration,
login and account-access checks) that can be exercised in the browser against the emulators, with the
experimental guard (section F) loaded into the Firestore emulator.

| Component | Production (default; unchanged) | Local emulator mode |
|---|---|---|
| Backend `main.py` | No registration route | Mounts `POST /api/account/register` when the backend starts in Firebase emulator mode (`registration_enabled()` in `backend/routes/registration.py`) |
| React Firebase clients (`frontend/src/firebase.js`, `frontend/src/utils/firebaseEmulator.js`) | Configuration from `frontend/.env` | Only in the Vite dev server (`DEV`) with `VITE_USE_FIREBASE_EMULATORS` exactly `true`: the demo project `demo-route2unikl` with placeholder values, the Authentication emulator on `127.0.0.1:9099` and the Firestore emulator on `127.0.0.1:8080`, connected before first use. The Firebase SDK shows its "Running in emulator mode" banner. |
| Registration page (`Register.jsx`, `frontend/src/utils/registrationApi.js`) | Browser sign-up, then `users/{uid}` written from the browser | The same form and both student types; one POST to the backend; the backend's code is turned into a message that never repeats the input; on success, the login page |
| Login page (`Login.jsx`, `frontend/src/utils/accountAccess.js`) | Sign-in and claim check | After the claim check, for students only: one read of the student's own `users/{uid}`. If Firestore refuses it (`permission-denied`), the student is signed out and sees "Your account can't access student data at the moment. Please contact the Route2UniKL administrator." Any other failure does not block the login (the rules, not this check, enforce access). Login never writes. |

**Local flow:** registration form → `POST /api/account/register` (no token) → the backend creates the
Auth account, the `users/{uid}` profile and the `active` access record (section I) → 201 → login page →
sign-in with the Authentication emulator → claim check → own-profile check → student dashboard. Firestore
reads and writes go to the emulator with the student's own token, where the experimental rules (if
loaded) check the access record; backend calls go to the emulator-mode backend, which verifies the token
against the Authentication emulator.

| # | Protection | Implementation | Evidence |
|---|---|---|---|
| J1 | The browser uses the emulators only in the dev server with the exact flag | `shouldUseEmulators`: `DEV === true` and the flag is the string `true`. A production build has `DEV` false, so the flag is ignored. | Frontend unit (`firebaseEmulator.test.js`: production builds, unset and near-miss flag values, missing environment) |
| J2 | No production configuration in emulator mode | The emulator configuration is built from constants (demo project, placeholder key and app ID); production values passed in are ignored. Hosts are loopback and match `firebase.json`. | Frontend unit |
| J3 | Environment variables are read individually | `firebase.js` passes each variable by name, so a build inlines only those. | Bundle scan of the production build (24 Nov 2026; counts only, `.env` not read): the only `VITE_` names are the six `VITE_FIREBASE_*` names and `VITE_USE_FIREBASE_EMULATORS`, each twice (object key and property read); no inlined environment object (no quoted `VITE_` keys, no `BASE_URL`). The emulator code path and the demo constants are present in the bundle but unreachable (`DEV` is false). `dist/` was deleted afterwards. |
| J4 | Backend registration from the browser in emulator mode only, without echoing input | `registerThroughBackend` first checks the password (6–128 characters counted in code points like the backend, and since JL9 no control characters; never trimmed) and sends no request if it fails; otherwise it sends exactly `name`, `email`, `password` and `role` as JSON, without cookies, and never rejects; 201 is the only success; 409 `EMAIL_IN_USE`, 422 (field names only), 503 `REGISTRATION_INCOMPLETE` or `REGISTRATION_UNAVAILABLE`, 404, 413, network failure and anything else have fixed messages. | Frontend unit (`registrationApi.test.js`: no message contains the name, email or password; a `__proto__` field name is not looked up; password boundaries, see "Defect found in browser verification") |
| J5 | Login never creates or changes an access record | The browser check only reads `users/{uid}`; the backend's `get_current_user` does not use the service. | Emulator integration (`test_local_account_flow.py` test 7: sign-in and a backend call leave a `disabled` record, including its update time, unchanged; test 6: no record is created for an account without one); Code inspection |
| J6 | Blocked accounts are refused, including with previously issued tokens | Disabled (record first, then Auth): Firestore 403 and backend 403 with the earlier token; sign-in `USER_DISABLED`. Deleted (record `deleting`, data removed, Auth deleted, record `deleted`): read 403, re-creating the profile 403, backend 401; sign-in `EMAIL_NOT_FOUND`. Missing record: profile create and read 403. Incomplete registration: account disabled, no record. | Emulator integration (tests 3–7, with the experimental rules loaded) |
| J7 | Students cannot read other students' documents or the access records | Own profile 200; another student's profile 403; own `account_access` record 403. | Emulator integration (test 1) |
| J8 | Production-mode backend has no registration route | `main.py` checks `registration_enabled()` at import. | Backend unit (unset, `production`, unknown and emulator modes); Emulator integration (test 8: production-mode application → 404, no account created); scratch run (24 Nov 2026): the documented emulator-mode start lists the route |
| J9 | Only the emulators are used | Section G harness. | Emulator integration (test 9) |
| J10 | Access-failure messages reveal nothing sensitive | Registration and access messages are fixed text; the access message names no state, record or code. | Frontend unit; scratch run: the emulator-mode server log contained neither the test password nor the email |

The nine integration areas required for this milestone map to `test_local_account_flow.py` as follows:
complete registration and successful login (test 1); duplicate email (2); incomplete registration (3);
disabled login (4); missing record (6); blocked Firestore access (4, 5, 7); production-mode registration
refusal (8); no accidental production connection (9, plus the frontend unit tests and bundle scan). The
module loads the experimental rules into the running Firestore emulator and restores `firestore.rules`
afterwards.

**Running the local flow** (PowerShell; local emulators only; the commands below were checked in scratch
runs on 24 Nov 2026, except the browser steps). Use four terminals:

1. Emulators, from the repository root: `firebase emulators:start --only auth,firestore --project demo-route2unikl`
   (`firebase.json` disables the Emulator UI). Restarting the emulators clears all data and reloads `firestore.rules`.
2. Optional, to test the guard: load the experimental rules into the running Firestore emulator, from the repository root:

   ```
   $rules = [System.IO.File]::ReadAllText("$PWD\firestore-tests\account-access.experimental.rules")
   $body = @{ rules = @{ files = @(@{ name = 'firestore.rules'; content = $rules }) } } | ConvertTo-Json -Depth 5
   Invoke-RestMethod -Method Put -Uri 'http://127.0.0.1:8080/emulator/v1/projects/demo-route2unikl:securityRules' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
   ```

   This affects only the running emulator. Restarting it, or saving `firestore.rules`, restores the production rules.
3. Backend, from `backend/` (never `--host 0.0.0.0`, see GL2 and GL8):

   ```
   $env:ROUTE2UNIKL_FIREBASE_MODE = 'emulator'
   $env:ROUTE2UNIKL_EMULATOR_PROJECT_ID = 'demo-route2unikl'
   $env:FIREBASE_AUTH_EMULATOR_HOST = '127.0.0.1:9099'
   $env:FIRESTORE_EMULATOR_HOST = '127.0.0.1:8080'
   .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

   If start-up prints a Firebase configuration error, check that `GOOGLE_APPLICATION_CREDENTIALS` is not set
   and that `GOOGLE_CLOUD_PROJECT` and `GCLOUD_PROJECT` are unset or `demo-route2unikl` (section G).
4. Frontend, from `frontend/`: `$env:VITE_USE_FIREBASE_EMULATORS = 'true'; npm run dev`, then open
   `http://localhost:5173`. `frontend/.env` does not need to change.

Helper commands for the browser plan (PowerShell, emulator only; `Bearer owner` is the emulators' administrative
access and works only on the emulators):

| Purpose | Command |
|---|---|
| Find an account's uid by email | `(Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/projects/demo-route2unikl/accounts:lookup' -Headers @{Authorization='Bearer owner'} -ContentType 'application/json' -Body '{"email":["<email>"]}').users[0]` (`disabled` is omitted while the account is enabled) |
| Read an access record | `(Invoke-RestMethod -Uri 'http://127.0.0.1:8080/v1/projects/demo-route2unikl/databases/(default)/documents/account_access/<uid>' -Headers @{Authorization='Bearer owner'}).fields` |
| Block a record (state and version only) | `Invoke-RestMethod -Method Patch -Uri 'http://127.0.0.1:8080/v1/projects/demo-route2unikl/databases/(default)/documents/account_access/<uid>?updateMask.fieldPaths=state&updateMask.fieldPaths=version' -Headers @{Authorization='Bearer owner'} -ContentType 'application/json' -Body '{"fields":{"state":{"stringValue":"disabled"},"version":{"integerValue":"2"}}}'` |
| Disable the Auth account | `Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/projects/demo-route2unikl/accounts:update' -Headers @{Authorization='Bearer owner'} -ContentType 'application/json' -Body '{"localId":"<uid>","disableUser":true}'` |
| Create an account without a record (the old browser way) | `Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-api-key' -ContentType 'application/json' -Body '{"email":"no-record@example.test","password":"<test password>","returnSecureToken":true}'` |

**Manual browser verification plan (performed by the owner on 26 Nov 2026; results below).** Use only example addresses (for example
`student1@example.test`) and test passwords. Do not open the AI assessment page: the backend calls live AI
providers in emulator mode too. The emulator has no programme data, so programme lists are empty.

| # | Step | Expected result |
|---|---|---|
| M1 | Open the app in emulator mode (steps 1–4, with the experimental rules) | The Firebase emulator banner is shown at the bottom of the page. |
| M2 | Register an SPM leaver | "Registration Successful! Please login." and the login page. The lookup shows the account; the record is `state: active`, `version: 1`. |
| M3 | Register a Form 4/5 student | As M2; after login, the profile page shows the student type "Upper Secondary Student". |
| M4 | Register again with the M2 email | "An account with this email already exists. Please log in, or reset your password." No second account. |
| M5 | Mismatched passwords; then a 5-character password, **typed** into both fields (not pasted: a pasted TAB or space counts as a character, see "Defect found in browser verification") | "Passwords do not match…" (no request sent); then "Please check your password (6 to 128 characters)." (no request sent; no account created). Since the JL9 change, a password containing a TAB or line break, even pasted, shows "Password cannot contain hidden control characters." (no request sent). |
| M6 | Log in with the M2 account | Student dashboard; the profile page shows the registered name and email. |
| M7 | While still signed in as M2: block the record, then disable the Auth account; then, without reloading, open the profile page through the app's navigation | The profile data does not load (Firestore refuses the earlier session; the page's own error handling applies, JL3). A full page reload may sign the user out instead, because the Firebase SDK re-checks the account. Logging in again shows "This account has been disabled…". The backend refusal of the earlier token is covered by integration test 4. |
| M8 | Block only the record of the M3 account (Auth still enabled); log in | "Your account can't access student data at the moment…", and the user is signed out. The record is unchanged afterwards (`disabled`, `version: 2`). |
| M9 | Create an account without a record (helper command); log in with it | The same access message, signed out; still no record afterwards. |
| M10 | Stop the backend; register | "We couldn't reach the Route2UniKL server…"; no account created. |
| M11 | Stop the dev server, start it without the flag (new terminal), open the app | No emulator banner: the app uses the production configuration. **Do not register or sign in** in this mode (that would use production Firebase). |

**Defect found in browser verification (M5, 26 Nov 2026).**

- *Observed (owner-reported):* registering `student3@example.test` with the password `Test1` succeeded:
  the success message, the login page, and `POST /api/account/register` → 201 in the FastAPI log. Expected:
  "Please check your password (6 to 128 characters)."
- *Root cause:* the request did not carry a 5-character password. A read-only lookup of that account in the
  local Authentication emulator (which keeps test passwords readable; only the length and character class
  were printed) found 6 characters: a leading TAB (U+0009) followed by `Test1`. A TAB cannot be typed into
  the field, so it most likely came with a pasted value, in both password fields. The masked fields do not
  show it. The backend counted it, as specified ("never trimmed"), so 6 characters passed the 6–128 rule,
  and Firebase Authentication accepted it too. The backend length check was not faulty. It already ran
  before any Firebase Authentication or Firestore operation, and the existing tests already refused 5 and
  129 characters. The frontend, however, had no length check of its own.
- *Fix:* the frontend now refuses passwords outside 6–128 characters before sending anything, with the
  documented message (`isPasswordLengthValid` in `frontend/src/utils/registrationApi.js`). It counts
  characters as code points, as the backend does, so the two agree on characters such as emoji. Passwords
  are never trimmed or changed. The backend rule is unchanged. New regression tests cover exactly 5, 6, 128
  and 129 characters: on the backend (service and route) and in the frontend.
- *Not changed (owner decision, JL9):* a password that contains control characters such as TAB, or leading
  or trailing spaces, is still accepted if its length is 6–128. Repeating M5 by pasting the same value would
  therefore still succeed. Type the password instead. *Update (26 Nov 2026): control characters are now
  refused; see "Password policy change (JL9)" below. Spaces remain allowed.*

| Evidence | Result |
|---|---|
| Backend unit: `PasswordLengthBoundaryTests` (service) and `test_password_length_boundaries` (route) in `test_registration.py`, 4 new tests | 5 and 129 characters (also 129 emoji) → `INVALID_REGISTRATION` naming only `password`; route 422 `{"code":"INVALID_REGISTRATION","fields":["password"]}`; Firebase Authentication never called; no Auth account, profile or access record. 6 and 128 characters (also an inner space and 128 emoji) → registered, with the password passed to Firebase exactly as received. A leading TAB plus 5 characters is accepted unchanged (current rule); 3 spaces plus 2 characters is refused. The password never appears in responses, errors or logs. |
| Frontend unit: 6 new tests in `registrationApi.test.js` | 5, 0 and 129 characters (also 129 emoji) → the documented message and **no request**; 6 and 128 characters (also an inner space and 128 emoji, which is 256 UTF-16 units) → sent unchanged; non-string values refused; the message never contains the password. |
| Mutation check (scratch, in memory; source not edited) | Limits shifted to minimum 5, minimum 7, maximum 127 and maximum 129: 4, 4, 3 and 4 of the 4 new backend tests failed; unchanged limits: 0 failed. |
| Full runs (26 Nov 2026) | Backend unit 146 tests, `OK`; frontend unit 115/115; lint of the changed frontend files passed. Emulator integration and Firestore rules suites were not re-run: the backend source is unchanged, and the integration harness wipes the emulators, which were in use for browser verification. |
| Browser | M5 repeated by the owner after the fix: a typed 5-character password (`Test1`) was refused — PASS (owner-reported). |

**Defect history (this milestone)**

| # | Found by | Defect | Root cause | Fix | Status |
|---|---|---|---|---|---|
| D1 | Frontend unit test (during implementation, 24 Nov 2026) | A field name such as `__proto__` in a 422 response would have been looked up on the object prototype, producing a garbled message | Plain object property lookup | Own-property check (`Object.hasOwn`) in `registrationApi.js` | Fixed before review |
| D2 | Owner browser walkthrough, step M5 (26 Nov 2026) | A password entered as `Test1` was accepted (201) | The submitted value was a leading TAB plus `Test1` (6 characters); the frontend had no length check of its own | Frontend length check before any request; boundary regression tests (above) | Fixed; M5 re-tested PASS |

**Owner browser verification results** (owner-reported, 26 Nov 2026; local emulators, `demo-route2unikl`,
experimental rules loaded; no production login or registration was performed)

| # | Result | Notes and limitations |
|---|---|---|
| M1 | PASS | Emulator banner shown. |
| M2 | PASS | SPM leaver registered. |
| M3 | PASS | Form 4/5 student registered. |
| M4 | PASS | Duplicate email refused. |
| M5 | PASS (after fix) | Mismatched passwords refused. The first minimum-length attempt exposed defect D2; after the fix, a typed `Test1` was refused. |
| M6 | PASS | Student login; name, email and student type correct. |
| M7 | PASS for the login refusal | After the record and the Auth account were disabled, the browser showed signed-out navigation, and logging in again gave the disabled-account message. **The Firestore refusal of the earlier token was not directly observed in the browser**; it is covered only by emulator integration tests 4 and 5 and the experimental rules suite. |
| M8 | PASS | Auth enabled, record disabled: the access-denied message. |
| M9 | PASS | Auth account without a record: the access-denied message. |
| M10 | PASS for the error message | With FastAPI stopped, registration showed the connection error. **That no account was created was not independently checked.** In emulator mode the registration page sends only the backend request, never a Firebase sign-up (code inspection of `Register.jsx`), so with the backend stopped nothing can create one; the network-failure message is covered by a frontend unit test. |
| M11 | PASS | Restarted without the flag: no emulator banner. No production login or registration was performed (by design), so the production registration and login flows were not exercised in this milestone. |

**Final pre-commit audit (26 Nov 2026).** The owner's emulators were stopped first (only processes confirmed as
`demo-route2unikl` emulators), then every suite was re-run: backend unit 146, `OK`; emulator integration 45,
`OK`; frontend unit 115/115; Firestore rules 44/44 (production) and 100/100 (experimental); production build
passed, and the bundle scan was unchanged (`DEV` inlined as false, emulator flag unset; `dist/` deleted); lint of
the changed frontend files passed (the pre-existing `Register.jsx` error is unchanged and also present at
`29fcdd3`). The diff against `29fcdd3` contains only this milestone's files. `.gitignore` and the three ChromaDB
files had the same hash, size and modification time before and after the runs. The changes contain no
credential patterns, and only `@example.test` addresses.

**Password policy change (JL9, 26 Nov 2026; owner request, before the milestone commit).** Passwords that
contain a Unicode control character are now refused at registration.

- *Exact rule (both registration paths and the backend):* a password is valid only if it has 6 to 128
  Unicode code points **and** no character of Unicode category `Cc`, which is exactly U+0000–U+001F and
  U+007F–U+009F (TAB, line feed, carriage return, DEL, NUL, ESC, the C1 controls such as NEL). The password
  is checked as entered and is never trimmed, normalised, stripped or otherwise changed. Ordinary spaces
  (internal, leading or trailing), no-break spaces and all other printable characters remain allowed.
- *Messages:* a control character → "Password cannot contain hidden control characters." (checked first,
  so it is shown even if the length is also wrong); a wrong length → "Please check your password (6 to 128
  characters)." (unchanged). Neither repeats the password or its characters.
- *Backend:* `validate_registration` in `backend/services/registration_service.py` refuses it with
  `INVALID_REGISTRATION` naming only `password` (route: 422 `{"code":"INVALID_REGISTRATION","fields":["password"]}`),
  before Firebase is initialised or called. The response shape is unchanged; nothing is logged.
- *Frontend:* `passwordValidationMessage` in `frontend/src/utils/registrationApi.js` (`/\p{Cc}/u` and the
  code-point length). `Register.jsx` calls it after the password-confirmation check and **before both
  paths**: the emulator-mode backend request and the production browser sign-up
  (`createUserWithEmailAndPassword`). `registerThroughBackend` also checks it before sending. Routing and the
  Firebase configuration are unchanged.
- *Production effect (browser registration path only):* new registrations are now refused before any
  Firebase call when the password has a control character, is shorter than 6 characters (previously refused
  by Firebase with its own error text) or is longer than 128 characters (previously accepted by Firebase).
  Login, the password-reset email, and existing accounts and their stored passwords are unchanged (the app
  has no password-change page). The unrouted duplicate `frontend/src/pages/Register.jsx` (section 5) was not
  changed.
- *Not covered (outside the requested `Cc` rule):* other invisible characters, such as zero-width spaces
  (category `Cf`), remain allowed. If the backend alone refuses a control character (only possible when the
  frontend check is bypassed), the browser shows the generic length message, because the 422 response names
  the field, not the reason.

| Evidence | Result |
|---|---|
| Backend unit: `PasswordControlCharacterTests` (4 tests) and `test_passwords_with_control_characters_are_refused` (route) in `test_registration.py`; `test_spaces_count_and_are_never_trimmed` replaces the earlier TAB-accepted test | `Test1` refused (length); `Test123` accepted and passed to Firebase unchanged; TAB + `Test1`, trailing TAB, LF, CR, CRLF, DEL, NUL, ESC, NEL and U+009F refused with only `password` named, Firebase never initialised or called, no Auth account, profile or access record, the password in no error, response or log; Python's category `Cc` is exactly the 65 documented code points, and each of them is refused; space, `~`, U+00A0 and U+00A1 accepted; leading, trailing and internal spaces passed on unchanged; 128 characters accepted and 129 refused (existing boundary tests). |
| Frontend unit: 5 new tests in `registrationApi.test.js`; the earlier TAB-accepted test replaced | The same cases; all 65 `Cc` code points refused with the control message and **no request**; the control message takes precedence over the length message; spaces sent exactly as typed; 128/129 characters. |
| Mutation check (scratch; backend patched in memory, frontend on a scratch copy; repository files not edited) | Backend: rule disabled, C0 only, ASCII controls only (no C1) and an over-broad rule refusing all non-ASCII were each detected; unchanged: 0 failures. Frontend: rule disabled, C0 only, and length checked before control characters were each detected; unchanged: 0 failures. |
| Full runs (26 Nov 2026, emulators stopped first) | Backend unit 151, `OK`; emulator integration 45, `OK`; frontend unit 120/120; Firestore rules 44/44 (production) and 100/100 (experimental); production build passed (the `\p{Cc}` expression and the new message are in the bundle; bundle scan unchanged); lint of the changed frontend files passed (pre-existing `Register.jsx` error unchanged). `.gitignore` and the three ChromaDB files unchanged (hash, size and modification time). |
| Browser | A focused retest by the owner is pending. A production-mode browser test is not recommended: if the check failed, it would create a real account. |

**Student self-delete: findings (code inspection and the P0 suites) and required fixes.** `Profile.jsx`
deletes `users/{uid}` from the browser and then calls `deleteUser`. With the guard deployed this would
leave: `results/{uid}` and `ai_assessments/{uid}` (S4); the access record `active` for a deleted account
(as HL5) until reconciliation; and, until the ID token expires (up to one hour), a session that can still
read and write those documents and re-create `users/{uid}`. `deleteUser` also fails for sessions that
are not recent ("requires recent login"), after the profile is already gone, leaving an enabled account
without a profile. Required before the guard is deployed (M3B; not implemented):

1. A backend deletion endpoint for the signed-in student, identity from the verified token only, that
   requires a recent sign-in (`auth_time` within a short window).
2. A resumable order: record `deleting` (transaction, version check) → revoke refresh tokens → delete
   `results`, `ai_assessments` and `users` → delete the Auth account → record `deleted`. A failure leaves
   the record `deleting`, which already denies Firestore access, and a retry continues.
3. Remove the browser deletion from `Profile.jsx`; call the endpoint, then sign out.
4. A rules change, under the change procedure in [FIRESTORE_BASELINE.md](FIRESTORE_BASELINE.md), removing
   the owner's delete on `users` (also resolves S5/W1).
5. Unit and emulator integration tests for each partial failure, the resume path and the earlier token.

**Minimum reconciliation (not implemented; design in section H).** Downgrade only, in a Firestore
transaction: re-read the Auth account and the record; only if Auth is disabled or missing and the record is
still `active` with the version that was read, set `state: 'disabled'` and increment `version`, keeping
`sessionsValidAfter`. Never upgrade, never touch `deleting` or `deleted`, never write a record that changed
meanwhile, and log only the uid and codes. It is needed in two places: immediately after provisioning
reports an Auth change (HL2, IL5), and as a scheduled sweep for changes made outside the coordinated actions
(HL5, console changes, and browser self-delete while it exists). Records are never changed silently: every
correction is logged and reported.

**Preconditions for Admin Disable, Enable and Delete (M3B-2).** Before these actions are implemented
(emulator first), agree the design; before they are used in production, also complete the production items
below.

- Endpoints under `require_admin` only; no action on the caller's own account or on Admin accounts; the
  target uid validated; identity and Admin status from the verified token.
- Coordinated order, record before Auth: Disable = record `disabled` (transaction, version check) → Auth
  disabled → revoke refresh tokens. Enable = confirm both are disabled → revoke refresh tokens → set
  `sessionsValidAfter` with a server timestamp → wait about 3 seconds (FL3) → record `active` → Auth enabled
  (the emulator does not end old tokens on re-enable; section G). Delete = the resumable deletion order above.
- An operation lock and audit model in separate backend-only collections (the record allows no extra
  fields), so that concurrent actions cannot interleave, and an audit trail without personal data in logs.
- The minimum reconciliation above, so a partly completed action or a console change cannot leave an
  `active` record.
- Defined handling and recovery for every partial failure, never reported as success.
- Emulator integration tests for each order, each partial failure and earlier tokens (Firestore and
  backend), plus unit tests.

**Pending production requirements** (none is implemented; each needs separate approval):

| Requirement | Reference |
|---|---|
| Backfill of access records for existing accounts (dry run first) | FL5, section H |
| Guard deployment through the rules change procedure, after a production `auth_time` canary | FL1, FL2 |
| Backend registration in production: rate limiting and bot protection, HTTPS and CORS, the 409 enumeration decision, the password policy, a recovery procedure and monitoring for incomplete registrations, and mounting the route in production mode | Section I, IL2–IL4 |
| The production registration page switched to the backend (otherwise, with the guard, browser registration cannot create the profile: test 6) | JL2 |
| Reconciliation (minimum, above) | HL2, HL5, IL5 |
| Student self-delete moved to the backend | Above; S4, FL6 |
| Enabling the login access check in production, once the guard is deployed | JL3 |
| Backend deployment, `/docs` exposure and App Check | Section 4, S7, S8 |

**Limitations**

| # | Limitation | Type | Status |
|---|---|---|---|
| JL1 | The backend does not consult the access record: an enabled account with a missing or blocked record still gets 200 from `/api/auth/me` (tests 6 and 7). Backend routes follow the Auth state (`check_revoked=True`), which the coordinated order changes right after the record. | Boundary (by design, FL8) | Partly addressed in M3B-3 (section L, DP9): in emulator mode, the student-data endpoints refuse `deleting` and `deleted` records; other states, `/api/auth/me` and production mode unchanged (DL3) |
| JL2 | With the guard, the production browser registration can no longer create `users/{uid}` (test 6), so the guard cannot be deployed before registration goes through the backend in production. | Dependency | Open |
| JL3 | The login access check runs in emulator mode only, and it is a usability check: Firestore rules enforce access. Other student pages do not show the access message when a session is blocked later; they use their own error handling (not reviewed). | Usability problem | Open |
| JL4 | Browser behaviour rests on the owner's walkthrough (11/11 passed) and code inspection: no rendered-component tests exist (E4). Not observed in the browser: the Firestore refusal of an earlier token (M7) and account non-creation with the backend stopped (M10). The production registration and login flows were not exercised (M11, by design). | Test-coverage gap | Partly closed (owner walkthrough, 26 Nov 2026); the rest open |
| JL5 | The production bundle contains the emulator code path and demo constants, unreachable because `DEV` is false. | Code size (no exposure) | Accepted |
| JL6 | Running the flow locally needs four terminals and manual commands; the emulator UI is disabled in `firebase.json`. | Developer experience | Accepted; no `firebase.json` change |
| JL7 | Emulator results are not production evidence (section G). | Test-coverage gap | Open |
| JL8 | One full integration run stopped in module set-up when the emulator reset request timed out (10 seconds); the re-run and a later run passed. The cause was not investigated. | Test flakiness | Open; watch for recurrence |
| JL9 | Passwords may contain control characters (such as TAB) and leading or trailing spaces; each counts towards the 6–128 characters and is never trimmed. Characters that cannot be typed or seen in the masked field can make a password differ from what the student believes they chose (the M5 defect). Refusing control characters (refusing, never trimming) would be a change to the password policy. | Usability problem and policy decision | **Resolved (26 Nov 2026)** for control characters: Unicode category `Cc` is refused on both registration paths and the backend, without trimming ("Password cannot contain hidden control characters."; see "Password policy change (JL9)"). Spaces remain allowed by design; other invisible characters (such as zero-width spaces, category `Cf`) are not covered. The wider production password policy (section I) is still an owner decision. |

### K. M3B-2 — Admin Disable & Enable Accounts (Emulator Only)

> **Status: implemented and tested against the local Firebase emulators only; committed in `e5e41a6`, not deployed.
> Owner browser walkthrough on 26 Nov 2026: 13/13 conversational checkpoints passed (owner-reported). They do not
> map one-to-one to the planned tests B1–B13: 3 verified, 7 partially verified, 1 not verified, 2 automated tests
> only (see "Actual Browser Walkthrough Results" and "Coverage of the planned tests"). Post-implementation security audit (26 Nov 2026):
> PASS WITH LIMITATIONS — acceptable as a local-emulator development milestone; NOT production-ready (Medium
> findings M1–M3 open; see "Post-implementation security audit").** The new routes exist only when the backend starts in
> Firebase emulator mode; a production-mode backend has no account-changing endpoint, and the read-only M3A
> routes are unchanged. No production account, claim, Firestore document or rules deployment was involved.
> Delete was not part of M3B-2; it is M3B-3 (section L), which changes the states below for `deleting` and
> `deleted` records and adds Delete to the allowed actions of active and disabled accounts.

**Purpose.** Let an administrator disable and enable student accounts from Manage Users, with the
account-access record (section F) and Firebase Authentication kept consistent, earlier sessions blocked,
and every operation either verified as complete or recorded as incomplete and resumable.

**Endpoints** (`backend/routes/admin_account_actions.py`, mounted under `/api/admin/users`):

| Method and path | Purpose | Notes |
|---|---|---|
| `GET /{uid}/access` | Access state for the UI: Auth status, the record (state, version, `sessionsValidAfter`), consistency issues, any unfinished operation, the account state and the allowed actions | Read-only. No email, name, claims or another administrator's uid (only `started_by_you`). |
| `POST /{uid}/disable` | Disable a student account | 200 only after verification; body `{"outcome":"completed", "operation", "operation_id", "resumed_operation_id", "audit_recorded", "lock_released", "account"}` |
| `POST /{uid}/enable` | Enable a disabled student account | As above; takes about 4–5 seconds (waits below) |

Order of checks on every route: (1) emulator mode, else 404 `{"detail":"Not Found"}` before any token check;
(2) Firebase initialised in emulator mode, else 503; (3) `require_admin` (401/403); (4) uid pattern (422); then the
service. Errors: `{"code", "message"}`, with `operation`, `operation_id`, `failed_step` and `reason` for
`OPERATION_INCOMPLETE`. Codes: 403 `SELF_ACTION_FORBIDDEN`, `ADMIN_TARGET_FORBIDDEN`; 404 `USER_NOT_FOUND`;
409 `ACCESS_RECORD_UNSUPPORTED`, `ALREADY_DISABLED`, `ALREADY_ACTIVE`, `OPERATION_IN_PROGRESS`,
`INCOMPLETE_OPERATION_PENDING`; 503 `ACCOUNT_ACTION_UNAVAILABLE` (nothing changed), `OPERATION_INCOMPLETE`
(stopped part-way, recorded).

**Account states and allowed actions** (computed by the server; the UI only shows them):

| State | Condition | Allowed |
|---|---|---|
| `protected` | The caller's own account, or an account with the `admin: true` claim | none |
| `unsupported` | Record missing, malformed, `deleting` or `deleted` (since M3B-3: missing or malformed only; `deleting`/`deleted` are the deletion states in section L) | none (never created, repaired or reactivated) |
| `in_progress` | A running operation lock with a valid lease | none |
| `incomplete` | An unfinished operation (failed step recorded, or lease expired) | unfinished Disable: Disable (resume); unfinished Enable: Enable (resume) or Disable (cancel) |
| `active` | Auth enabled, record `active` | Disable |
| `disabled` | Auth disabled, record `disabled` | Enable |
| `inconsistent` | Auth and the record disagree, no operation recorded | Disable or Enable |

**Workflow** (`backend/services/account_action_service.py`). Every step is idempotent; a resumed operation
continues from the current state.

| Disable | Enable |
|---|---|
| 1. `restrict_record`: record `active` → `disabled` (Firestore access closes first) | 1–2. Normalise to fully disabled: `restrict_record`, `disable_auth` (only when resuming or inconsistent) |
| 2. `disable_auth`: Auth account disabled | 3. `revoke_sessions`: wait 1.1 s, then revoke refresh tokens |
| 3. `verify`: Auth disabled and record `disabled` | 4. `set_session_threshold`: `sessionsValidAfter` = Firestore server time (record still `disabled`) |
| | 5. `settle`: wait 3 s (FL3: a sign-in within the guard's margin would be refused) |
| | 6. `enable_auth`: Auth account enabled |
| | 7. `activate_record`: record `disabled` → `active`, **last** |
| | 8. `verify`: Auth enabled, record `active` with `sessionsValidAfter` |

**Design decisions and findings**

- *Enable activates the record last* (a change from the order sketched in section J, which put the record
  before Auth). With this order a failure at any step leaves the record not `active`, so Firestore stays closed:
  a failure at `enable_auth` leaves both disabled; a failure at `activate_record` leaves Auth enabled with the
  record `disabled` (the student can sign in but cannot read their data; the backend accepts their new tokens,
  JL1). The earlier order would have left an `active` record whose Auth account is disabled after a failure.
- *Revocation margin (new finding, confirmed on the emulators).* The Admin SDK treats a token as revoked only if
  its issue time (`iat`, set by Firebase Authentication) is earlier than the account's revocation time, both in
  whole seconds (`firebase_admin/_auth_client.py:763`), so a token issued in the same second as the revocation
  remains valid for the backend. Without a margin, a session created just before a resumed Enable passed the
  backend check (integration test 7 failed in 1 of 2 runs with the margin set to 0). Enable therefore waits
  1.1 s after Auth is confirmed disabled before revoking. The Firestore guard was not affected (its own
  one-second margin, F4). This applies to production as well.
  *Correction (post-implementation audit, 26 Nov 2026):* the revocation time is **not** necessarily Firebase's
  time. `revoke_refresh_tokens` writes `valid_since = int(time.time())`, taken from the **backend host's clock**
  (`firebase_admin/_auth_client.py:164`), while `iat` comes from Firebase Authentication's clock. The 1.1 s
  margin covers same-second timing only when the two clocks agree, as on the emulators (one host clock). If the
  backend clock is behind Firebase's by more than about 1.1 s, tokens issued shortly before the Disable could
  survive the backend's revocation check; if it is ahead by more than about 4 s, fresh sign-ins after Enable
  would be refused (fails closed). See M2. The guard's threshold (`sessionsValidAfter`) is Firestore server time
  compared with `auth_time` (FL3) and does not use the backend clock.
- *Disable does not revoke tokens:* a disabled account fails the backend's check (`check_revoked=True` also
  checks the disabled state), cannot refresh tokens, and is refused by the guard; Enable always revokes first.
- *Version checks:* each record change expects the version that the operation last saw and writes with a
  precondition on the document's update time (`account_access_service.change_record_state`); a record changed by
  anything else is never overwritten (reason `RECORD_CHANGED`).
- *Locks:* `account_operations/{uid}`, created atomically (create-if-absent) with a 120-second lease. A running lock
  refuses every action; after a failure the lock is kept as `incomplete` with the failed step and a reason code
  (a lock whose lease expired counts as incomplete). The same action resumes it; Disable may take over an
  unfinished Enable; Enable may not take over an unfinished Disable. A lock is taken over only with a
  precondition, so two administrators cannot both take it; another operation's lock is never overwritten, even
  temporarily. After the lock is acquired, the state is read again before anything changes.
- *Audit:* `account_audit/{operationId}` is created before any account change (no audit record → no change), then
  updated with the outcome.
- *Reconciliation (downgrade only):* Disable on an account whose Auth is disabled but whose record is still
  `active` only downgrades the record. `account_access_service.reconcile_access_record()` also handles a missing
  Auth account (record `active` → `disabled`), never upgrades, and never touches `deleting`, `deleted`, missing or
  malformed records; it is used by tests only until the scheduled sweep (deferred to the production migration).
  The coordinated actions never create an `active` record with a disabled Auth account.

**Operation records** (backend-only collections; the access record keeps exactly `state`, `version` and
`sessionsValidAfter`; the experimental and production rules deny browser access to unknown collections):

| Collection | Fields |
|---|---|
| `account_operations/{uid}` (lock) | `operationId`, `operation` (`disable`/`enable`), `actorUid`, `status` (`running`/`incomplete`), `leaseExpiresAt`, `failedStep`, `reason`, `previousOperationId`, `startedAt`, `updatedAt` |
| `account_audit/{operationId}` | `operationId`, `operation`, `actorUid`, `targetUid`, `outcome` (`started`/`completed`/`incomplete`), `failedStep`, `reason`, `resumesOperationId`, `resumesOperation`, `before` and `after` (`{auth, record, version, sessionsValidAfterSet}`), `startedAt`, `finishedAt` |

No email address, name, password, token, custom claim or academic data is stored or logged; logs contain uids,
operation identifiers, steps and codes.

| # | Protection | Evidence |
|---|---|---|
| K1 | Routes absent outside emulator mode; the guard runs before token verification | Backend unit (unset, `production`, unknown mode: 404, token never verified, service never called; `main.py` mounts the routes only in emulator mode); Emulator integration (test 9: production-mode application, 404, nothing changed) |
| K2 | Administrators only; never the caller's own account or an administrator account | Backend unit (no token 401, student and non-boolean claims 403; self refused before Firebase is touched; administrator targets refused, nothing written); Emulator integration (tests 2, 3) |
| K3 | Disable restricts Firestore before Auth; a disabled student cannot sign in; earlier tokens are refused by Firestore and the backend | Backend unit (event order); Emulator integration (test 1) |
| K4 | Enable revokes, sets the threshold, waits and activates the record last; earlier **ID tokens** stay blocked by Firestore and the backend; a fresh sign-in works. *Corrected (post-implementation audit, 26 Nov 2026):* earlier sessions are **not** fully blocked on the backend in the emulator: a **refresh token** issued before the Disable is refused while the account is disabled (`USER_DISABLED`), but after Enable it can still be exchanged for a new ID token, which the backend accepts (`/api/auth/me` 200); Firestore still refuses it (403; threshold). Whether production refuses revoked refresh tokens is unverified (GL1). See M3. | Backend unit (event order including both waits); Emulator integration (tests 1, 7: old ID token → Firestore 403, backend 401; fresh sign-in → 200); audit scratch probe (26 Nov 2026; not a repository test): pre-Disable refresh token after Enable → refresh 200, backend 200, Firestore 403 |
| K5 | A failure at any step never leaves an `active` record, is reported as `OPERATION_INCOMPLETE`, is recorded on the lock and in the audit, and can be resumed | Backend unit (failure injected at each Enable step and at both Disable steps; resume; Disable cancelling an Enable); Emulator integration (tests 6, 7) |
| K6 | Missing, malformed and deletion-state records are refused and left unchanged | Backend unit; Emulator integration (test 4) |
| K7 | Concurrent and repeated actions change the account once | Backend unit (12 threads; a lock appearing between the check and the acquisition is left untouched; a lock taken over concurrently is refused); Emulator integration (test 5: 6 concurrent requests) |
| K8 | Records changed by anything else are never overwritten | Backend unit (change after the check: version mismatch; change just before the write: precondition) |
| K9 | No change without an audit record; a missing audit outcome or lock release is reported, not hidden | Backend unit |
| K10 | Reconciliation only downgrades | Backend unit (all record and Auth combinations); Emulator integration (test 8, including a deleted Auth account) |
| K11 | Responses and logs contain no personal data | Backend unit (allow-listed fields; email sentinel never logged or returned); scratch HTTP check (server log contained no test password or email) |
| K12 | Only the emulators are used | Emulator integration (test 10) |

**Mutation check** (scratch, one process per mutation; repository files not edited): 17 of 17 weakened copies
of the service, the record primitives and the routes were detected by the unit tests, including: Disable
changing Auth before the record; Enable activating the record before Auth; no revocation, no revocation margin,
no settle wait, no threshold; administrators not protected; the self check only after Firebase is touched; no
version check; no precondition on record writes; running locks taken over; leases that never expire; Enable
taking over an unfinished Disable; a lock kept when the audit record cannot be created; unsupported records
allowed; reconciliation that upgrades; and routes available outside emulator mode. Two of these (running locks
and Enable over an unfinished Disable at takeover) were first missed and led to the test "a lock that appears
after the check is never touched".

**Admin UI** (User Details → **Account access** panel; `frontend/src/pages/admin/AdminUserDetail.jsx`,
`frontend/src/components/admin/ConfirmDialog.jsx`, `frontend/src/utils/adminAccountActions.js`):
state badge and explanation (active, disabled, needs attention, incomplete change with the stopped step and
reason, change in progress, protected, not available); buttons only from the server's allowed actions and never
for administrators or the caller (Disable account, Enable account, Resume disable, Resume enable); a modal
confirmation dialog (focus on Cancel, Escape and backdrop cancel, not dismissible while running); loading labels
("Disabling…", "Enabling…"), buttons disabled while an action runs or the state reloads, and a submission guard
against double clicks; success, warning and error messages (an unreachable server is never reported as
"nothing changed"); the page's account details refresh after a change while staying visible. When the server
does not offer account actions (production mode), the panel says so. The browser never calls Firebase to
change accounts. The list page is unchanged apart from its description; its Active/Disabled badge reflects
Firebase Authentication only (incomplete operations are shown on User Details).

**Running locally.** As in section J (steps 1–4, with the experimental rules loaded). Then create a dedicated
emulator administrator (emulator only: the URLs are the local emulator and `Bearer owner` works only there; no
endpoint can create administrators):

```
$admin = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-api-key' -ContentType 'application/json' -Body '{"email":"admin1@example.test","password":"<test password>","returnSecureToken":true}'
$claims = @{ localId = $admin.localId; customAttributes = '{"admin":true}' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/projects/demo-route2unikl/accounts:update' -Headers @{Authorization='Bearer owner'} -ContentType 'application/json' -Body $claims
```

List audit records:
`(Invoke-RestMethod -Uri 'http://127.0.0.1:8080/v1/projects/demo-route2unikl/databases/(default)/documents/account_audit' -Headers @{Authorization='Bearer owner'}).documents | ForEach-Object { '{0} {1} {2} step={3}' -f $_.fields.startedAt.timestampValue, $_.fields.operation.stringValue, $_.fields.outcome.stringValue, $_.fields.failedStep.stringValue }`

These commands were checked in a scratch run on alternative ports (26 Nov 2026), together with an
emulator-mode backend on a scratch port: admin verification 200; CORS preflight for POST with Authorization
from `http://localhost:5173` allowed; access, Disable and Enable over HTTP (Enable took about 4 s); self-disable
and a student caller 403; the server log contained no test password or email.

**Manual browser verification plan (not run as written: the owner's walkthrough on 26 Nov 2026 used its own 13 conversational checkpoints; the coverage of each planned test is given below).** Use example
addresses and test passwords only. Use a normal window for the administrator and a private window for the student.

| # | Step | Expected |
|---|---|---|
| B1 | Prepare: section J steps 1–4 with the experimental rules; create the administrator (above); register two students in the app (S1 SPM leaver, S2 Form 4/5) | Both registrations succeed |
| B2 | Administrator: log in → Manage Users | The administrator and both students are listed |
| B3 | Open your own account's details | Account access: "Protected", your own account; no buttons |
| B4 | Open S1's details | "Active"; "Disable account" button |
| B5 | Private window: log in as S1; open the profile page | Profile loads |
| B6 | Administrator: Disable account → press Escape; then Disable account → Cancel; then Disable account → confirm | Escape and Cancel close the dialog without change; confirming shows "Disabling…", then "Account disabled"; the badge and the Status row show Disabled; the panel offers "Enable account" |
| B7 | Private window: without reloading, open the profile page through the navigation; then sign out and try to log in as S1 | Profile data does not load; login shows the disabled-account message |
| B8 | Administrator: Enable account → confirm | "Enabling…" for about 4–5 seconds, then "Account enabled"; badge Active |
| B9 | Private window: log in as S1 again | Login succeeds and the profile loads |
| B10 | Administrator: on S2, click Disable account → confirm, and click the confirm button again quickly | One change only (the second click has no effect); list the audit records: one `disable completed` for S2 |
| B11 | Make S2 inconsistent outside the app: enable S2's Auth account directly (section J helper "Disable the Auth account" with `"disableUser":false`); refresh S2's details | "Needs attention" with the explanation; Disable account and Enable account offered; Disable completes it (Disabled) |
| B12 | Stop the backend; click Refresh in the panel; start the backend again and click Refresh | "Can't reach the Route2UniKL server…", then the current state again |
| B13 | Private window: as S1, open `http://localhost:5173/admin/users` | Redirected away from the admin area (existing guard); the actions are server-protected (K2) |

Incomplete operations cannot be produced from the browser without fault injection; they are covered by the
automated tests (K5) and their display by the frontend unit tests.

**Actual Browser Walkthrough Results** (owner-reported, 26 Nov 2026; local emulators, `demo-route2unikl`). The
walkthrough used its own 13 conversational checkpoints, labelled B1–B13 in the conversation. **These labels do
not correspond to the planned tests B1–B13 above**; the coverage of each planned test is given in the next table.
All 13 conversational checkpoints were reported as passed.

| Conversational checkpoint | What was verified (owner-reported) |
|---|---|
| Walkthrough B1 | The JL9 test student's User Details showed "Active" and the "Disable account" button. |
| Walkthrough B2 | The Disable confirmation dialog showed the expected warning. |
| Walkthrough B3 | Disable succeeded: the status became "Disabled" and "Enable account" appeared. |
| Walkthrough B4 | The Enable confirmation dialog showed the expected warning about sessions. |
| Walkthrough B5 | Enable succeeded: the status became "Active" and "Disable account" reappeared. |
| Walkthrough B6 | The re-enabled student signed in and opened the profile. Before this check, the student's password was reset with the local Auth emulator. |
| Walkthrough B7 | The current administrator's own account showed "Protected", with no Disable or Enable action. |
| Walkthrough B8 | A second local-emulator administrator account showed "Protected", with no Disable or Enable action. |
| Walkthrough B9 | With the student already signed in, the administrator disabled the account: the existing student session showed a disabled-account message, and a fresh login attempt was refused. |
| Walkthrough B10 | The Disabled status persisted after refreshing the administrator's browser page. |
| Walkthrough B11 | An unauthenticated Admin API request returned `{"detail":"Not authenticated."}`; its HTTP status was not independently recorded (in code this response is HTTP 401, `backend/core/auth.py`). |
| Walkthrough B12 | An authenticated non-administrator request to the Admin API returned HTTP 403. |
| Walkthrough B13 | An independent lookup in the Auth emulator showed `disabled: True` for the JL9 test student. |

After testing, the owner re-enabled the JL9 test student.

**Coverage of the planned tests** (from the walkthrough evidence above). VERIFIED: the planned expectation was
observed. PARTIALLY VERIFIED: only part of it was observed. NOT VERIFIED: no manual check, and no automated test
covers the planned browser behaviour. AUTOMATED TEST ONLY: not observed in the browser; covered by automated tests.

| Planned test | Status | Evidence and gaps |
|---|---|---|
| B1 Prepare (experimental rules, administrator, two new students S1 and S2) | PARTIALLY VERIFIED | An administrator account and the JL9 test student were used (walkthrough B1, B7). Registering S1 and S2 was not recorded (the JL9 test student is an earlier account, section J), and whether the experimental rules were loaded into the emulator was not recorded. |
| B2 Administrator login → Manage Users lists the administrator and both students | PARTIALLY VERIFIED | Administrator login and access to User Details are implied by walkthrough B1 and B7; the content of the list was not recorded. |
| B3 Own account → "Protected", no buttons | VERIFIED | Walkthrough B7. Walkthrough B8 also showed a second administrator as "Protected" (beyond the plan). |
| B4 S1's details → "Active", "Disable account" | VERIFIED | Walkthrough B1, with the JL9 test student in place of S1. |
| B5 Student signs in; profile loads | PARTIALLY VERIFIED | Walkthrough B9 records that the student was already signed in before the Disable; the profile loading at that point was not recorded. |
| B6 Disable: Escape and Cancel close without change; confirm → "Disabling…", "Account disabled"; badge and Status row Disabled; "Enable account" offered | PARTIALLY VERIFIED | Walkthrough B2 (dialog warning), B3 (status Disabled; "Enable account" appeared), B10 (persisted after refresh). The owner also observed the success message "Account disabled. The account has been disabled." Escape, Cancel and the "Disabling…" loading label were not verified; the Status row was not recorded. |
| B7 Earlier session: profile data does not load (Firestore guard); fresh login shows the disabled-account message | PARTIALLY VERIFIED | Walkthrough B9: the existing session showed a disabled-account message and a fresh login was refused; walkthrough B13: Auth emulator `disabled: True`. The Firestore part is **AUTOMATED TEST ONLY**: the message seen is application-level (the backend's disabled-account refusal in `backend/core/auth.py`, or the Firebase SDK), not evidence that Firestore rules rejected the earlier session (K3; integration test 1; rules suite F). |
| B8 Enable: "Enabling…" for about 4–5 s, "Account enabled", badge Active | PARTIALLY VERIFIED | Walkthrough B4 (dialog warning about sessions) and B5 (status Active; "Disable account" reappeared). The owner also observed the success message "Account enabled. The account has been enabled. The student must sign in again." The "Enabling…" loading label and the operation duration were not verified. |
| B9 Student logs in again; profile loads | VERIFIED | Walkthrough B6. The password had first been reset with the local Auth emulator, so this shows only that a fresh sign-in works after Enable; it says nothing about earlier sessions (a password change can itself end earlier sessions in Firebase Authentication; not checked on the emulator). |
| B10 Double click on confirm → one change; the audit records list one `disable completed` | NOT VERIFIED | Not performed. The backend's single change under concurrent requests (K7) and the audit records (K9; integration tests 1 and 5–7) are covered by automated tests, but the browser's double-submission guard has no automated test (KL6), and the audit records were not inspected manually. |
| B11 Inconsistent account → "Needs attention"; Disable completes it | AUTOMATED TEST ONLY | Not performed in the browser. Backend unit tests (states and allowed actions; actions from inconsistent states), integration test 8 (Auth disabled outside the application → Disable downgrades the record), frontend unit tests (texts). |
| B12 Backend stopped → "Can't reach the Route2UniKL server…"; current state after restart | AUTOMATED TEST ONLY | Not performed in the browser. Frontend unit tests cover the message mapping only (no rendered-component test). |
| B13 Student opens the admin area → redirected; actions server-protected | PARTIALLY VERIFIED | Server-side protection: walkthrough B12 (non-administrator → HTTP 403) and B11 (unauthenticated → "Not authenticated."). The browser redirect away from `/admin/users` was not recorded. |

Of the 13 planned tests: 3 VERIFIED, 7 PARTIALLY VERIFIED, 1 NOT VERIFIED, 2 AUTOMATED TEST ONLY. **"13/13" refers
to the conversational checkpoints only, not to the planned tests.**

**Not manually verified:**

- Firestore rules rejection: **not independently observed** during the manual browser walkthrough. Whether the
  experimental rules were loaded was not recorded, and the disabled-account message seen is application-level.
  Firestore enforcement rests on the automated tests only.
- The content of the audit records.
- Old refresh-token behaviour after Enable (M3), and old ID tokens after Enable.
- The access record's state independently of the application. The panel's "Disabled" means the backend read
  both Auth and the record as disabled; walkthrough B13 checked the Auth state only.
- Incomplete-operation handling (not producible from the browser without fault injection).
- Production behaviour.

**Post-implementation security audit (26 Nov 2026; read-only; no file changed).** Verdict: **PASS WITH
LIMITATIONS.** The audit reviewed every M3B-2 change and the Git diff against `7936909`, the experimental and
production rules, and the installed Firebase Admin SDK, and re-ran the automated checks: backend unit 193 `OK`;
frontend unit 142/142; lint passed; emulator integration 55/55 and Firestore rules 44/44 and 100/100 (scratch
ports, so the owner's emulator data was untouched); mutation check 17/17; production build passed; plus a scratch
probe of refresh tokens after Enable (M3). Not run: the repository commands on the default ports (occupied by the
owner's emulators), browser automation, and anything against production. Confirmed during the audit: production
gating (`backend/main.py:41`; `backend/routes/admin_account_actions.py:80–89`, 404 before any token check, then
`require_admin`); self and administrator protection (`backend/services/account_action_service.py:546`, `:230`,
`:275–290`); the Disable and Enable step order (`:491–503`); version and precondition checks; atomic locks; an
audit record before any change (`:563–568`); the guard on every allow of the three student collections
(`firestore-tests/account-access.experimental.rules:169–241`); and catch-all denial of `account_operations` and
`account_audit` in both rules files (experimental `:268–269`; `firestore.rules:189–190`). No Critical or High
finding.

| # | Severity | Finding | Status |
|---|---|---|---|
| M1 | Medium | **Lock lease not longer than the worst-case operation; Firebase Authentication writes are not fenced.** `LEASE_SECONDS = 120` (`account_action_service.py:69`) and an expired lease counts as incomplete (`:216`), but one Admin SDK call can take up to 120 s per attempt with up to 4 retries on HTTP 500/503 (`firebase_admin/_http_client.py:42–50`). Another administrator can therefore take over while the first operation still runs. Record writes stay version-checked, but Auth writes (`:438–445`, `:459–469`) are not, so a late Auth change could leave Auth enabled with the record `disabled` (Firestore closed; the backend accepts the student's tokens, JL1). | Open for Disable and Enable; not tested. Must be resolved before production. For deletion locks, M3B-3 adds lease renewal with an ownership check before every step and a takeover grace period (section L; a timing assumption, not a fence, DL2). |
| M2 | Medium | **Revocation time from the backend host clock.** `valid_since = int(time.time())` (`firebase_admin/_auth_client.py:164`) is compared with Firebase-issued `iat` (`:763`); the 1.1 s margin assumes the two clocks agree (see the corrected design note above). The emulators share one host clock, so the tests cannot show the problem. | Open; production concern (clock synchronisation and a production check needed). |
| M3 | Medium | **An old refresh token restores backend access after Enable in the emulator.** Audit probe: a refresh token from before the Disable was refused while disabled (`USER_DISABLED`), but after Enable it was exchanged for a new ID token (200), which the backend accepted (`/api/auth/me` 200) and Firestore refused (403). Old ID tokens: backend 401, Firestore 403. K4 has been corrected. Production refusal of revoked refresh tokens is unverified (GL1; emulator behaviour in section G). | Open; production verification required. |
| L1 | Low | **Frontend HTTP 403 mapping.** `SELF_ACTION_FORBIDDEN` and `ADMIN_TARGET_FORBIDDEN` are HTTP 403, and `authFetch` turns every 401/403 into `ApiAuthError` without the code (`frontend/src/utils/apiClient.js:87–93`), so the panel shows "Admin access not confirmed" (`frontend/src/utils/adminAccountActions.js:174–176`); the specific messages (`:164–165`) are unreachable. The unit test feeds these codes with HTTP 409 (`adminAccountActions.test.js:207–214`), a false assumption. Reachable only through a race or a direct request (the buttons are hidden). No access is granted. | **Resolved in M3B-3** (section L, DP14): the code is kept on 401/403; regression tests use HTTP 403 |
| L2 | Low | **No automatic sign-out after a 401 during an action.** The panel assumes the page request handles an expired session (`frontend/src/pages/admin/AdminUserDetail.jsx:78`), but a failed action only reloads the panel (`:102`), unlike the automatic sign-out on Manage Users (B1). The backend refuses every request. | Open |
| L3 | Low | **Audit accuracy gaps.** (a) An audit record whose creation outcome is unknown, or an operation interrupted by a crash, stays `started` with no outcome (`account_action_service.py:563–568`, `:593–604`), so `started` can mean "never ran" or "stopped part-way"; a resumed operation gets a new audit record and the earlier one stays `started`. (b) A failure while reading the state in the `verify` step is always recorded as `STORE_UNAVAILABLE`, even when the Auth account was removed or Auth was unavailable (`:580–583`). (c) Refused requests are only logged (KL4), and changes made outside the application are not audited. | Open |
| L4 | Low | **Phantom lock.** A lock create whose outcome is unknown (`:311–317`) can leave a running lock: the account is blocked for up to 120 s, then shown as an incomplete operation with no failed step and no audit record. No account change is made. | Open |
| L5 | Low | **Forged tokens in emulator mode.** The emulator accepts unsigned tokens (GL2), so any local process can forge an administrator token for an emulator account and disable or enable emulator accounts. Loopback and emulator data only. | Accepted for local development (GL2, GL8) |
| L6 | Low | **Resume shortcut.** A resumed Enable skips revocation and a new threshold when the account already looks fully enabled with any `sessionsValidAfter` (`:506–518`); reachable only if something outside the application changes the record. | Informational |
| L7 | Low | **No rate limiting.** Each Enable holds a server worker thread for about 4–5 s. | Informational |

**Untested cases** (no automated or manual test covers them):

- Lock lease expiry while an operation is still running (M1).
- Refresh tokens after Enable (M3): observed only in the audit's scratch probe; no repository test.
- Frontend HTTP 403 error mapping for action responses through the real `authFetch` path (L1): the unit tests
  use HTTP 409.
- Also: the target account gaining the administrator claim during an operation; simultaneous Disable and Enable
  on the emulators (unit tests only); rendered-component behaviour (KL6); production behaviour (KL8).

**Readiness.**

- *Local-emulator development milestone:* acceptable to commit to `feature/admin-module` (audit verdict PASS WITH
  LIMITATIONS). None of the findings can affect production: the account-changing routes exist only in emulator
  mode, no production-mode code path writes to Firebase, and the production rules, `firebase.json` and production
  data are unchanged.
- *Production:* **not ready.** M1–M3 must be resolved or verified, together with the pending production
  requirements below and in section J. Local test results are not production evidence (KL8).

**Pending production requirements** (none implemented; each needs separate approval): everything listed in
section J (backfill of access records, guard deployment after the `auth_time` canary, production registration
through the backend, reconciliation sweep, self-delete fix, backend deployment); mounting these routes in
production mode; a decision on whether backend routes should also consult the record (JL1); monitoring of
incomplete operations and audit retention; a production check of the revocation-time comparison and of Firestore
precondition behaviour under contention. Added by the post-implementation audit (26 Nov 2026): resolution of M1
(a lease longer than the worst-case operation, or lock-ownership checks before Firebase Authentication writes);
M2 (clock synchronisation of the backend host, or a revocation time taken from Firebase, verified in production);
M3 (a production check that revoked refresh tokens are refused after Enable).

**Limitations**

| # | Limitation | Type | Status |
|---|---|---|---|
| KL1 | The backend does not consult the access record (JL1): after a Disable that stopped before `disable_auth`, or an Enable that stopped before `activate_record`, the backend still accepts the student's tokens while Auth is enabled; Firestore stays closed. | Boundary (by design) | Open; decide with JL1 |
| KL2 | Leases use the backend's clock and assume one backend instance; an operation running longer than 120 seconds could be taken over. Operations take seconds. | Design constraint | Accepted for local use; review before production. Audit: a single Admin SDK call can exceed the lease, and Auth writes are not fenced (M1, open). |
| KL3 | Enable takes about 4–5 seconds in one request (1.1 s and 3 s waits). | Usability | Accepted |
| KL4 | The audit records have no admin page; they are read with the helper command. Refused requests are logged, not audited. | Future development task | Open |
| KL5 | The list page shows Firebase Authentication status only; incomplete operations are shown on User Details. | Usability | Accepted |
| KL6 | No rendered-component tests (E4); the dialog and panel wiring rely on code inspection and the browser plan. | Test-coverage gap | Owner walkthrough: 13/13 conversational checkpoints; planned tests only partly covered (see "Coverage of the planned tests"); still no rendered-component tests |
| KL7 | The automated detection of the revocation margin is probabilistic (same-second timing); the unit tests pin the waits. | Test-coverage gap | Accepted |
| KL8 | Emulator results are not production evidence (contention, preconditions, revocation and clock behaviour). | Test-coverage gap | Open (see M2 and M3) |
| KL9 | The emulator suites ran on alternative ports (scratch configuration outside the repository) because the owner's emulators were running; the repository command uses the ports in `firebase.json`. | Test process | Recorded |
| KL10 | Post-implementation audit findings M1–M3 (Medium) and L1–L7 (Low) and the untested cases listed under "Post-implementation security audit". | Security limitations and test-coverage gaps | Open (L5 accepted; L6, L7 informational). Updated by M3B-3 (section L): L1 resolved; M1 addressed for deletion locks only; JL1 closed for accounts in deletion (emulator mode only) |

### L. M3B-3 — Admin Delete Student Account (Emulator Only)

> **Status: implemented and tested against the local Firebase emulators only; not committed, not deployed.
> Owner browser walkthrough (26 Nov 2026): the D1–D14 plan was only PARTIALLY verified (5 verified, 8 partially
> verified, 1 not verified; D4, D5 and D13 incomplete; see "Coverage of the planned tests"). Post-implementation
> security audit (26 Nov 2026): PASS WITH LIMITATIONS. Acceptable ONLY as a local-emulator development milestone;
> NOT production-ready (see "Production blockers").**
> Saving S3's SPM results in the app during the walkthrough opened the "Generating AI Assessment" page, so the AI
> generation workflow was triggered. Whether an external AI provider request was sent or completed is NOT verified
> (see "AI assessment generation during the walkthrough"). The browser test plan below has been corrected.
> The new routes exist only when the backend starts in Firebase emulator mode, like M3B-2 (section K). The
> production `firestore.rules`, `firebase.json` and production data are unchanged; no production account, claim
> or document was involved. AI, OCR, RAG and the recommendation algorithm are unchanged.

**Purpose and deletion policy.**

- **Permanent deletion.** There is no soft deletion, undo or restore. Deleted accounts and data cannot be recovered
  through the application.
- **Who can be deleted:** a student account that is `active` or `disabled` (Firebase Authentication and the access
  record agree), or one whose deletion is unfinished. Refused, with nothing changed: the caller's own account;
  every account with the `admin: true` claim; accounts without a valid access record (legacy accounts and
  malformed records are **never** silently deleted, `ACCESS_RECORD_UNSUPPORTED`); inconsistent accounts
  (`DELETE_NOT_ALLOWED`); and accounts with another unfinished operation (`INCOMPLETE_OPERATION_PENDING`).
- **Confirmation.** The browser shows an irreversible-deletion warning and enables the confirm button only after
  the student's email address is typed in full (letter case and surrounding spaces ignored). When the
  sign-in account is already gone (recovery), the account ID must be typed instead. This is a usability safeguard only.
  The server requires the body `{"confirm_uid": "<uid>"}` with exactly the uid in the path. It checks this before
  Firebase is touched (422 `DELETE_CONFIRMATION_MISMATCH`) and rejects any other field (422). It never trusts the
  frontend alone.

**Endpoints** (`backend/routes/admin_account_actions.py`; mounted by `backend/main.py` only in emulator mode;
same order of checks as section K: emulator mode (404), Firebase initialised in emulator mode (503),
`require_admin` (401/403), uid pattern (422), then the body. This order holds for a well-formed JSON body:
FastAPI rejects a malformed JSON body with 422 before any of these checks, audit finding DA7):

| Method and path | Purpose | Notes |
|---|---|---|
| `POST /api/admin/users/{uid}/delete` | Permanently delete a student account, or resume an unfinished deletion | 200 only after verification, with the same body as Disable/Enable (`account.state` `deleted`, `auth_status` `missing`) |
| `GET /api/admin/account-operations/incomplete-deletions` | Unfinished deletions, including accounts whose Firebase Authentication account is already gone | Read-only; at most 100 entries; the same allow-listed fields as `/access` (no email or name) |
| `GET /api/admin/users/{uid}/access` (M3B-2) | Now also answers for an account in deletion whose Auth account is gone (`auth_status: "missing"`) | Otherwise unchanged |

New codes: 422 `DELETE_CONFIRMATION_MISMATCH`; 409 `ACCOUNT_DELETION_IN_PROGRESS` (Disable or Enable on an
unfinished deletion), `ACCOUNT_DELETED`, `DELETE_NOT_ALLOWED`. New reasons for `OPERATION_INCOMPLETE`:
`ADMIN_TARGET`, `LOCK_LOST`, `NESTED_DATA`, `DATA_REMAINS`.

**Account states and allowed actions** (changes to section K):

| State | Condition | Allowed |
|---|---|---|
| `active` | Auth enabled, record `active` | Disable, **Delete** |
| `disabled` | Auth disabled, record `disabled` | Enable, **Delete** |
| `deletion_incomplete` (new) | Record `deleting`, or a deletion lock that is not running, or record `deleted` while the Auth account or a deletion lock remains | Delete (resume) only: a deletion is never undone or cancelled |
| `deleted` (new) | Record `deleted`, Auth account gone, no deletion lock | none |
| `in_progress` | A running lock; for a deletion lock also during the takeover grace period (below) | none |
| `protected` | The caller, or an account with the admin claim (including one promoted during a deletion) | none |
| `unsupported` | Record missing or malformed (no longer `deleting`/`deleted`: those are now the two deletion states) | none |

**Data scope** (inspection of the repository on 26 Nov 2026):

| Data | Where | Handling |
|---|---|---|
| Sign-in account | Firebase Authentication | Deleted |
| Profile | `users/{uid}` | Deleted |
| Academic results | `results/{uid}` | Deleted |
| AI assessment | `ai_assessments/{uid}` | Deleted |
| Subcollections of those documents | None are written by the application | Checked before deleting: if any exists, the deletion stops before deleting anything (`NESTED_DATA`), because deleting a document does not delete its subcollections |
| Access record | `account_access/{uid}` | Kept as the tombstone `{state: "deleted", version}` |
| Operation lock | `account_operations/{uid}` | Removed when the deletion completes |
| Audit record | `account_audit/{operationId}` | Kept (below) |
| Browser storage | `localStorage` `selected_prep_program_id` (a programme ID, not personal data) | Not reachable from the server; left in that browser |
| Server logs | uids, operation IDs, steps and codes (no email, name or academic data) | Not deleted (outside the application) |
| ChromaDB, backend files and caches | Programme data only; the backend writes no student files | Nothing to delete |
| AI providers | Assessment requests send interests only, never the uid (`backend/routes/assessment.py`) | Provider-side retention outside the application's control (S10) |

No Firebase Storage or Realtime Database is used. Gaps: server logs, copies made outside the application (for
example console exports) and, in production, Firestore backups or point-in-time recovery are not covered.

**Retained records.** The tombstone holds only `state` and `version`. The audit record holds the operation
identifier, `operation: "delete"`, `actorUid`, `targetUid`, outcome, failed step, reason, resumed operation,
`before`/`after` summaries (`{auth, record, version, sessionsValidAfterSet}`), timestamps, and
`dataPresentBefore`/`dataPresentAfter`: existence flags for the three documents, never their contents. No name, email
address, SPM results or assessment content is retained. **Retained uids (the tombstone's document ID, `targetUid`,
`actorUid`) are potentially identifying information** and need a retention policy before production.

**Deletion order** (`backend/services/account_action_service.py`; every step is idempotent and a resumed deletion
continues from the current state). Before step 1: the self check (before Firebase is touched); the state check
(administrator, record, other operations); an exclusive lock (create-if-absent, 300-second lease); a re-read under
the lock; and the audit record with `dataPresentBefore`. A failure there changes nothing and gives the lock back.
The lease is renewed, only if this request still owns the lock, before each step below.

| # | Step | What it does | If it fails here (recorded on the lock and in the audit; resumable) |
|---|---|---|---|
| 1 | `mark_deleting` | Record `active`/`disabled` → `deleting` (version-checked, precondition). From here the Firestore guard refuses the student, and so do the backend's student-data endpoints | Record unchanged or `deleting`; nothing deleted |
| 2 | `disable_auth` | Auth account disabled: no sign-in or token refresh; the backend refuses its tokens | Record `deleting` (no access); data intact |
| 3 | `check_admin_before_data_deletion` | The admin claim is re-read | `ADMIN_TARGET`: stops; data and Auth account kept; account shown as `protected`; resume refused |
| 4 | `check_no_nested_data` | No subcollections under the three documents | `NESTED_DATA`: nothing deleted |
| 5 | `delete_student_data` | **One atomic Firestore batch** deletes the three documents and increments the record's version with a precondition (the fence): all or nothing | Nothing deleted (a changed record makes the whole batch fail: `RECORD_CHANGED`) |
| 6 | `confirm_data_removed` | The three documents are re-read: all must be absent | `DATA_REMAINS`: the Auth account is not deleted |
| 7 | `check_admin_before_auth_deletion` | The admin claim is re-read again | `ADMIN_TARGET`: the Auth account is kept (data already gone) |
| 8 | `delete_auth` | Firebase Authentication account deleted (already gone counts as done) | Data gone, Auth account disabled, record `deleting` |
| 9 | `finalize_record` | Record `deleting` → `deleted` (the tombstone; never changed again) | Auth account gone: no longer in Manage Users; listed under "Incomplete deletions" |
| 10 | `verify` | Auth account gone, record `deleted`, and the three documents absent (re-read) | `UNEXPECTED_STATE` or `DATA_REMAINS`; never reported as success |

Firestore and Firebase Authentication cannot be changed atomically. The Auth account is deleted only after the
data removal is confirmed, and the record is finalised after Auth. The batch in step 5 is atomic within Firestore
only. A request is reported as completed only after step 10 passes. Section J sketched "revoke refresh tokens" at
step 2; disabling the Auth account is used instead, because a disabled account can neither refresh tokens nor
pass the backend's check (`check_revoked=True`), and the Auth deletion follows.

**Recovery.** Every failure leaves the lock `incomplete` with the failed step and the reason, and the audit
record `incomplete`. The same Delete resumes the deletion, from User Details ("Resume deletion") while the Auth
account exists. If the Auth account is already gone (failure at step 9 or 10), the account no longer appears in the
Auth-based Manage Users list or details (404). `GET .../incomplete-deletions` finds it from its deletion lock or its
`deleting` record, and the Manage Users page shows it under **Incomplete deletions** with "Finish deletion" (typed
account ID). Disable and Enable refuse an account in deletion (409 `ACCOUNT_DELETION_IN_PROGRESS`) and never take
over its lock; Delete never takes over another operation's lock.

**Security protections**

| # | Protection | Evidence |
|---|---|---|
| DP1 | Routes absent outside emulator mode (both routers) | Backend unit (unset and `production`: 404, including the list route; `main.py` mounts them only in emulator mode); Emulator integration (test 12) |
| DP2 | Administrators only; never the caller or an administrator; legacy, malformed and inconsistent accounts refused unchanged | Backend unit; Emulator integration (tests 3, 4, 5) |
| DP3 | Server-side confirmation bound to the target uid, checked before Firebase is touched; extra fields rejected | Backend unit (service and route); Emulator integration (test 3) |
| DP4 | Order: access closed first, data deleted atomically, Auth deleted only after the data removal is confirmed, tombstone last | Backend unit (event order); Emulator integration (test 1, independent checks through the emulator's REST API) |
| DP5 | A failure at every step is recorded, never reported as success, and resumable; the batch is all or nothing | Backend unit (generic failure at each of the 9 steps with invariants and resume; real failures of the record write, Auth disable, subcollection check, batch and Auth deletion; a silently ineffective step caught by verification); Emulator integration (tests 6–9; test 7 shows the emulator applying none of the batch's deletes when its precondition fails) |
| DP6 | Auth deleted but record not finalised: still found and resumable | Backend unit; Emulator integration (test 9: User Details 404, listed under incomplete deletions, resumed) |
| DP7 | Administrator checks before starting, before the data deletion and before the Auth deletion; a claim appearing mid-deletion stops it and is never reported as success | Backend unit; Emulator integration (test 4, both points) |
| DP8 | Concurrency: one deletion at a time; a lock appearing between the check and the acquisition is never touched; lease renewed with an ownership precondition before every step; a lost lock stops the deletion before its next change; takeover of a running deletion only after lease and grace | Backend unit (10 threads; lock race in both directions; renewal count; lost lock; grace); Emulator integration (test 10: 6 concurrent requests) |
| DP9 | Backend student-data access (JL1, for deletion): `require_student_data_access` (`backend/core/student_access.py`) on `/api/assessment/generate-questions` and `/api/assessment/recommend` refuses `deleting`/`deleted` records with 403 `ACCOUNT_DELETED`, even with a still-valid token, before the handler runs; an unreadable record → 503 (fails closed); production mode unchanged (no read) | Backend unit (AI and recommendation functions replaced by spies that must not run); Emulator integration (test 6: Auth still enabled, both endpoints 403; test 11: active and legacy accounts unchanged) |
| DP10 | Earlier sessions after deletion: Firestore read and re-creation refused; backend 401; refresh token refused; sign-in `EMAIL_NOT_FOUND`; the same email re-registers as a new uid, the tombstone unchanged | Emulator integration (test 1) |
| DP11 | Records never reactivated: transitions `deleting → deleted` only; the tombstone is final; reconciliation never touches them | Backend unit |
| DP12 | No personal data in responses, audit records or logs | Backend unit (email and document contents absent); Emulator integration (tests 1, 9) |
| DP13 | The rules actually loaded in the test emulators are the experimental guard | Emulator integration (test 0, canary: a `disabled` record makes the student's own profile read fail, which the production rules would allow) |
| DP14 | L1 resolved: `authFetch` keeps the backend's code on 401/403 (`frontend/src/utils/apiErrors.js`); `SELF_ACTION_FORBIDDEN`/`ADMIN_TARGET_FORBIDDEN` show their own messages; every other 401/403 keeps its previous meaning, and `AUTH_SERVICE_UNAVAILABLE` never relabels a 401/403 | Frontend unit (`apiErrors.test.js`; L1 regression tests with HTTP 403 in `adminAccountActions.test.js`) |

**Concurrency and in-flight calls (M1).** Deletion locks have a 300-second lease, renewed with a precondition on
the lock before every step. Renewal cannot interrupt a Firebase Authentication call that is already running, and
Firebase offers no conditional (fenced) Auth write. A running deletion lock is therefore treated as abandoned only
after its lease **and** a 30-minute grace period, 35 minutes after its last renewal. The slowest step makes two
Admin SDK calls of up to about 10 minutes each (120 s per attempt, up to 4 retries). This is a timing assumption
(backend clock, documented SDK timeouts), **not a fence**. It is safe because:

- every Auth write of a deletion moves in one direction (disable, delete);
- Enable never runs on an account in deletion;
- every Firestore write is version- or precondition-checked.

A failure that was recorded is resumable at once; only a crashed process waits for the grace period.
M1 remains open for Disable and Enable (120-second lease, no renewal).

**Admin UI.**

- *User Details → Account access:*
  - "Delete account" (danger) for active and disabled students; "Resume deletion" for unfinished ones.
  - The dialog has the irreversible-deletion warning and the typed-email field; the confirm button stays disabled
    until the email matches.
  - Loading label "Deleting…"; double submission prevented.
  - After success, the page returns to Manage Users (keeping the search and filters), replacing the details page
    in the history. A dismissible "Account deleted" notice is shown, built from two flags only.
  - Failures show the stopped step, the reason and what to do next. An unreachable server is never reported as
    "nothing changed".
- *Manage Users → Incomplete deletions:* hidden when there are none or when the server offers no account actions.
  - Auth account present: a link to User Details.
  - Auth account gone: "Finish deletion" with the typed account ID.
  - Promoted administrators and running deletions are explained, without an action.
- *Student pages:* a refused request now shows "This account has been deleted." in the existing access-denied
  panel (L1 change).

**Tests and actual results** (26 Nov 2026; emulator suites on the scratch alternative ports, as in KL9, because
the owner's emulators were running):

| Check | Result |
|---|---|
| Backend unit | 231 tests, `OK`: the existing 193 and 38 new (`tests/test_account_deletion.py`). M3B-2 expectations updated for the new states and allowed actions; test fakes extended (Auth deletion, subcollections, queries, atomic batches with preconditions) |
| Emulator integration | 69 tests, `OK`: the existing 55 and 14 new (`integration_tests/test_account_deletion_emulator.py`); two M3B-2 expectations updated (allowed actions; Disable/Enable on a `deleting` record now `ACCOUNT_DELETION_IN_PROGRESS`). The full suite passed in six full runs (three pairs of consecutive runs, the last pair after the final code change). Students' data is created through registration and the Admin SDK, removal is checked through the emulator's REST API, and no AI provider is called (stubs) |
| Frontend unit | 161/161: the existing 142 and 19 new (`adminAccountActions` 14, `apiErrors` 5); three M3B-2 expectations updated (Delete is now a known action) |
| Firestore rules | 44/44 (production) and 100/100 (experimental); rules unchanged |
| Mutation check (scratch, one process per mutation; repository files not edited) | Backend: 32 of 32 weakened copies detected by the unit tests (step order, admin re-checks, nested-data check, data confirmation, final checks, the batch fence, confirmation, transitions, lock grace, renewal, takeovers, the recovery list, the student-data check on both routes, emulator-only mounting). One was first missed (the batch primitive accepting a record that is not `deleting`) and led to a direct test. Frontend: 13 of 13 (typed confirmation, warning, L1 mapping, error fields, notice state) |
| Frontend build and lint | Production build passed; bundle scan: no provider key, service-account or private-key marker; one Google API key pattern (the public Firebase web configuration, as before). Lint of the changed frontend files passed; project-wide lint unchanged (E6: 21 errors, 2 warnings in 15 untouched files) |
| Post-implementation audit re-run (26 Nov 2026; read-only) | The same results: backend unit 231 `OK`; emulator integration 69 `OK` in two consecutive runs; frontend unit 161/161; Firestore rules 44/44 and 100/100; mutation check 32/32 and 13/13; lint and production build unchanged. Plus a scratch nested-data probe against a real scratch emulator: 2/2 (see "Post-implementation security audit") |
| Manual browser verification | **Partially verified** (owner walkthrough, 26 Nov 2026). Of the 14 planned tests: 5 verified, 8 partially verified, 1 not verified (D13); D4 and D5 incomplete. The original D1–D14 plan was not fully completed (see "Coverage of the planned tests") |

**Manual browser verification plan (corrected after the owner's walkthrough on 26 Nov 2026; the original D1–D14
plan was only partly completed, see "Coverage of the planned tests").** Local emulators with the experimental rules
(section J steps 1–4 and the administrator from section K). Use a normal window for the administrator and a private
window for the student. Use example addresses, test passwords and fictional results only.

**Never trigger AI assessment generation in these tests.** A successful save on the student's Manual Grade Entry or
Upload Results page opens `/ai-assessment` automatically (`frontend/src/pages/user/ManualGradeEntry.jsx:103`,
`frontend/src/pages/user/UploadResults.jsx:118`). That is the "Generating AI Assessment" page, which immediately calls
`POST /api/assessment/generate-questions`, and through it ChromaDB and the live AI providers. The original D1 step
("as S3, enter SPM results manually") could therefore not be followed without triggering it (audit finding DA1).

In deletion tests, students must not save results in the app and must not open `/ai-assessment`: stop at the
dashboard or the profile page. Create the fictional student documents with these emulator-only helpers instead.
They use the local Firestore emulator's REST API (port 8080) with its administrative `Bearer owner` credential.
Replace `<uid>` in the URI and, for `results`, also in the body. Both commands were validated with PowerShell 5.1
against a scratch emulator on 26 Nov 2026.

- `results/{uid}`: the fields of a manual entry in the app, with fictional grades:
  `Invoke-RestMethod -Method Patch -Uri 'http://127.0.0.1:8080/v1/projects/demo-route2unikl/databases/(default)/documents/results/<uid>' -Headers @{Authorization='Bearer owner'} -ContentType 'application/json' -Body '{"fields":{"userId":{"stringValue":"<uid>"},"results":{"arrayValue":{"values":[{"mapValue":{"fields":{"subject":{"stringValue":"MATHEMATICS"},"grade":{"stringValue":"A"}}}},{"mapValue":{"fields":{"subject":{"stringValue":"BAHASA MELAYU"},"grade":{"stringValue":"B+"}}}}]}},"status":{"stringValue":"manual_entry"},"recordType":{"stringValue":"PREDICTED_GRADES"},"verificationMethod":{"stringValue":"MANUAL_ENTRY"},"updatedAt":{"timestampValue":"2026-11-26T00:00:00Z"}}}'`
- `ai_assessments/{uid}`:
  `Invoke-RestMethod -Method Patch -Uri 'http://127.0.0.1:8080/v1/projects/demo-route2unikl/databases/(default)/documents/ai_assessments/<uid>' -Headers @{Authorization='Bearer owner'} -ContentType 'application/json' -Body '{"fields":{"answers":{"arrayValue":{"values":[]}},"isDemoMode":{"booleanValue":true}}}'`

| # | Step | Expected |
|---|---|---|
| D1 | Register students S3 (SPM leaver) and S4 (Form 4/5) in the app. Do **not** save results in the app. Create S3's `results/{uid}` and `ai_assessments/{uid}` documents with the two helpers above | Registrations succeed; both helper calls return the document; the AI-assessment page is never opened |
| D2 | Administrator: Manage Users → S3's details | Account access "Active" with "Disable account" and "Delete account"; Academic records show results and an assessment |
| D3 | Private window: log in as S3 and stay on the profile page | Profile loads |
| D4 | Administrator: Delete account; check the dialog; type a wrong email; press Escape; open it again and press Cancel | Warning "This cannot be undone…"; confirm button disabled until the email matches; Escape and Cancel close it with no change |
| D5 | Delete account; type S3's email in different letter case; confirm | Confirm becomes enabled; "Deleting…"; back on Manage Users with "Account deleted"; S3 not in the list; Dismiss removes the notice |
| D6 | Independent checks with the emulator helpers (Auth lookup, Firestore REST with `Bearer owner`, audit list from section K) | No Auth account; `users`, `results`, `ai_assessments` for S3's uid not found; `account_access/<uid>` = `{state: deleted, version: 4}`; one `delete completed` audit record without email or name |
| D7 | Private window (S3's earlier session): reload the profile page; sign out; log in as S3 again | No profile data loads; login fails (no such account) |
| D8 | Register again with S3's email | Succeeds as a new, empty account (new uid) |
| D9 | Administrator: S4 → Disable account; then Delete account (type the email) | Disabled, then deleted as in D5 |
| D10 | Your own account and another administrator's account | "Protected"; no Delete button |
| D11 | An account without an access record (section J helper) | "Not available"; no Delete button |
| D12 | Manage Users with no unfinished deletions | No "Incomplete deletions" panel |
| D13 | Stop the backend; Delete account on a student → confirm; start the backend; Refresh | "Can't reach the Route2UniKL server…" without "nothing changed"; afterwards the account is still Active |
| D14 | Private window: a student opens `http://localhost:5173/admin/users` | Redirected away; the delete API refuses students (DP2) |

Incomplete deletions (steps 1–10 failing) cannot be produced from the browser without fault injection. They are
covered by the automated tests (DP5, DP6), and their display by the frontend unit tests.

**Actual browser walkthrough results** (owner-reported, 26 Nov 2026; local emulators, `demo-route2unikl`). The
owner reported 25 checks, numbered W1–W25 here. **These numbers do not correspond to the planned tests D1–D14**;
the coverage of each planned test is given in the next table. "Independent" means checked outside the
application's pages, in the Auth emulator or directly in the Firestore emulator's documents.

| Check | What was observed (owner-reported) | Evidence |
|---|---|---|
| W1 | Student S3 registered with fictional personal information | Browser |
| W2 | S3's fictional SPM results saved in the app. **The save redirected automatically to the "Generating AI Assessment" page** (owner-confirmed after the audit; see "AI assessment generation during the walkthrough") | Browser |
| W3 | A disposable AI-assessment document created for S3 directly in the Firestore emulator | Emulator |
| W4 | S3's User Details: "Active", with Disable and Delete actions | Browser |
| W5 | The delete dialog showed the permanent-deletion warning | Browser |
| W6 | An incorrect confirmation email kept the delete button disabled | Browser |
| W7 | The correct email enabled it | Browser |
| W8 | S3 deleted successfully | Browser |
| W9 | S3's Firebase Authentication account no longer existed | Independent |
| W10 | `users/{uid}`, `results/{uid}` and `ai_assessments/{uid}` absent | Independent |
| W11 | Tombstone `account_access/{uid}`: `state=deleted`, `version=4` | Independent |
| W12 | Audit record: `operation=delete`, `outcome=completed`; the three data-presence flags `true` before and `false` after; Auth missing; no student name, email or academic content | Independent |
| W13 | S3's existing browser session redirected to Login; the old credentials failed | Browser |
| W14 | The same email re-registered successfully | Browser |
| W15 | The new Firebase uid differed from the deleted uid | Owner-reported (method not recorded) |
| W16 | The new account had no earlier SPM results or AI-assessment documents | Owner-reported (method not recorded) |
| W17 | Student S4 registered, disabled, then deleted successfully | Browser |
| W18 | S4's Firebase Authentication account no longer existed | Independent |
| W19 | The current administrator's own account: "Protected", no Delete action | Browser |
| W20 | A second administrator account: "Protected", no Delete action | Browser |
| W21 | A legacy Auth account without an access record: "Not available", no Delete action | Browser |
| W22 | No "Incomplete deletions" panel; a read-only Firestore query found zero incomplete operations among the records it returned | Browser; independent query |
| W23 | A regular student opening `/admin/users` was redirected to the Dashboard | Browser |
| W24 | With FastAPI stopped, the Admin area showed "Can't reach the Route2UniKL server"; S3 still existed. This must be the re-registered S3 account (new uid, W14–W15): the original was deleted in W8 | Browser; independent (existence) |
| W25 | After FastAPI restarted, that account remained "Active" with Disable and Delete | Browser |

**Coverage of the planned tests** (from the walkthrough evidence above; categories as in section K). VERIFIED: the
planned expectation was observed. PARTIALLY VERIFIED: only part of it was observed. NOT VERIFIED: the planned check
was not performed in the browser.

| Planned test | Status | Evidence and gaps |
|---|---|---|
| D1 Prepare (as originally written) | PARTIALLY VERIFIED | W1–W3, W17: S3 and S4 registered; S3's results saved and an AI-assessment document created. Not recorded: S4's student type (Form 4/5), and whether the experimental rules were loaded into the emulator. Following the original step opened the AI-assessment page (W2, DA1); the step is corrected above. |
| D2 S3's details: "Active", Disable and Delete; academic records shown | PARTIALLY VERIFIED | W4. The academic-records display was not recorded. |
| D3 S3 signed in; profile loads | PARTIALLY VERIFIED | W13 shows that an S3 session existed before the deletion; the profile loading was not recorded. |
| D4 Dialog: warning; confirm disabled until the email matches; Escape and Cancel close it with no change | PARTIALLY VERIFIED | W5, W6. **Escape and Cancel were not observed.** |
| D5 Delete with the email in different letter case → "Deleting…" → Manage Users with "Account deleted"; S3 not listed; Dismiss | PARTIALLY VERIFIED | W7, W8. **Not recorded: typing the email in different letter case, the "Deleting…" label, the return to Manage Users with the "Account deleted" notice, S3's absence from the list, and Dismiss.** Letter-case matching and the notice texts are covered by frontend unit tests only (no rendered-component test, DL11). |
| D6 Independent checks: Auth, three documents, tombstone version 4, audit record | VERIFIED | W9–W12. Whether exactly one audit record exists for S3 was not stated. |
| D7 S3's earlier session: no profile data; login fails | PARTIALLY VERIFIED | W13: redirect to Login; old credentials refused. Not shown directly: Firestore refusing the earlier ID token (read and re-creation), and the refresh-token refusal. Automated test only (integration test 01). |
| D8 Re-register with S3's email: a new, empty account (new uid) | VERIFIED | W14–W16 (the method for W15–W16 was not recorded). |
| D9 S4: Disable, then Delete | PARTIALLY VERIFIED | W17, W18 (Auth deletion independently verified). S4's Firestore documents, tombstone and audit records were not checked, and the dialog details were not recorded. |
| D10 Own and another administrator's account: "Protected", no Delete | VERIFIED | W19, W20. |
| D11 Account without an access record: "Not available", no Delete | VERIFIED | W21. |
| D12 No unfinished deletions: no "Incomplete deletions" panel | VERIFIED | W22. |
| D13 Backend stopped → Delete → "Can't reach the Route2UniKL server…" without "nothing changed"; afterwards still Active | NOT VERIFIED | **Not performed as planned: no Delete was attempted while the backend was stopped.** W24 shows the Admin area's own server-availability check, not the Delete action's failure handling. W25 shows the state after a restart, with no failed Delete before it. The Delete failure message is covered by frontend unit tests only (message mapping; no rendered-component test). |
| D14 Student opens `/admin/users` → redirected; the delete API refuses students | PARTIALLY VERIFIED | W23 (redirect). The API refusal was not tested manually; automated test only (integration test 03: 403). |

Of the 14 planned tests: **5 VERIFIED, 8 PARTIALLY VERIFIED, 1 NOT VERIFIED. The original D1–D14 plan was not
fully completed.**

**Not manually verified** (automated tests only, or untested):

- Firestore rules refusing the deleted student's earlier ID token (read and re-creation), and whether the
  experimental rules were loaded during the walkthrough (integration tests 00 and 01).
- Refresh-token refusal after deletion (integration test 01).
- In the delete flow:
  - Escape and Cancel in the dialog;
  - the "Deleting…" label;
  - the "Account deleted" notice and Dismiss;
  - letter-case matching of the typed email.

  Frontend unit tests cover only the texts and the matching.
- The Delete action's failure handling while the backend is unreachable (D13).
- The backend's student-data refusal for accounts in deletion (`ACCOUNT_DELETED`; DP9; integration test 06).
- Incomplete deletions and their recovery: "Resume deletion", "Finish deletion" and the panel with entries. These
  cannot be produced from the browser without fault injection (DP5, DP6).
- Concurrent or repeated Delete requests (DP8; integration test 10).
- Production behaviour.

**AI assessment generation during the walkthrough.**

- **Owner-confirmed:** after "Save SPM Results" was clicked during S3's testing (W2), Route2UniKL redirected
  automatically to the "Generating AI Assessment" page. That page calls `POST /api/assessment/generate-questions`
  (`frontend/src/pages/user/DummyAI.jsx:65`), so **the AI generation workflow was triggered**. This does NOT confirm
  that an external AI provider completed a request.
- **Confirmed by the audit (file metadata, read-only):** the three tracked ChromaDB files below were rewritten on
  26 Nov 2026 between 18:54:05 and 18:54:07 (MYT), during the owner's walkthrough. Their sizes are unchanged and
  their contents differ from the state recorded at the start of M3B-3 (SHA-256 prefixes):

  | File (`backend/chroma_db/`) | At the start of M3B-3 (last modified 24 Nov 2026, 16:34) | After the walkthrough (26 Nov 2026) |
  |---|---|---|
  | `chroma.sqlite3` | `d58486415c66acc9` | `edb966c0b31c8528` (18:54:05) |
  | `0d72ed42-…/data_level0.bin` | `ea9ac6972cb46667` | `4883b33d348d4acb` (18:54:07) |
  | `0d72ed42-…/length.bin` | `45f3346c8a0c0a07` | `2c2203cd447511cb` (18:54:07) |

- **Why this points to the AI generation, without proving it:**
  - In the application, ChromaDB is opened only by `backend/services/rag_orchestrator.py` (`retrieve_program_context`,
    reached from `generate-questions`) and by the seeder `backend/seed_chroma.py`.
  - The implementation session had no activity between 18:43 and 20:35.
  - Every automated test replaces the AI functions with stubs.

  The timing and the code paths are consistent with W2. This is a correlation, not proof.
- **Not verified:** whether any request reached an external AI provider, and whether one completed.
  - The orchestrator tries OpenAI, then Gemma via the Gemini API, then Ollama Cloud, and falls back to static
    questions if all fail.
  - The backend's console output from that time was not captured (the backend was restarted at 20:34), and no
    provider-side usage was checked.
  - By code inspection, the prompt contains only the declared interests and the retrieved programme context: no uid,
    name, email or grades (`build_assessment_prompt`).
- **Consequences:**
  - Live AI quota may have been used without the per-call approval CLAUDE.md requires. The cause is the test plan
    (DA1), now corrected.
  - The three ChromaDB files were already modified relative to `HEAD` before M3B-3 and are not part of this
    milestone. They have not been opened, reset, restored or staged since, and are left in their current state; any
    decision about them is the owner's.

**Post-implementation security audit (26 Nov 2026; read-only).** Verdict: **PASS WITH LIMITATIONS.**

- **Scope:**
  - every M3B-3 change and the Git diff against `e5e41a6`;
  - emulator-only routing and `require_admin`;
  - protection of the caller, other administrators and legacy accounts;
  - each deletion step, the batch fence, and recovery at every stage;
  - locks, renewal and in-flight Auth calls;
  - the administrator-claim race;
  - the student-data check, residual data and the audit records;
  - the frontend and the L1 fix;
  - the manual evidence.
- **Automated checks re-run:** see "Post-implementation audit re-run" in the results table above. The emulator suites ran on
  the scratch alternative ports, so the owner's emulators were untouched.
- **Not run:** browser automation, live AI calls, and anything against production.
- **Repository:** the audit changed no repository file, and the production `firestore.rules`, `firebase.json` and
  Firebase project were not touched.
- **No Critical or High finding.**
- **The residual M1 (Disable/Enable) does not undo a deletion.** A delayed Enable call could briefly re-enable Auth
  during a deletion, but the Firestore guard and the backend check still refuse the student (record `deleting`). The
  stale Enable then stops at its next step, and the Auth deletion happens regardless.

| # | Severity | Finding | Status |
|---|---|---|---|
| DA1 | Medium | **Test-plan defect.** The original D1 asked the owner to save results in the app, and a successful save opens the AI-assessment page (`ManualGradeEntry.jsx:103`, `UploadResults.jsx:118`). The plan's own warning "Do not run the AI assessment page" could therefore not be followed. This very likely caused the AI generation in W2. | **Corrected in this document** (D1 and the helpers above); observation recorded above |
| DA2 | Low | **Administrator-claim race.** The claim is checked before the lock, under the lock, before the data deletion and before the Auth deletion. The undetectable window is one Admin SDK call, and claims are set only outside the application. Sufficient for an emulator milestone; production needs an operational control. | Open (DL1; production blocker) |
| DA3 | Low | **The server-side confirmation proves the request names the target, not that a person confirmed it.** The browser always sends `confirm_uid` equal to the path uid, so any administrator token can delete an eligible student. A short-lived confirmation issued by the server would be stronger for production. | Accepted for this milestone (DL10) |
| DA4 | Low | **A stale running deletion lock is shown as running for up to 35 minutes.** Causes: a crashed process, or a lock that could not be released or marked incomplete, including after a completed deletion reported with `lock_released: false`. The panel says "Refresh in a moment" (`frontend/src/utils/adminAccountActions.js:137`), and the success note says resuming clears it (`:246`). Resume is offered only after the grace period, so both texts mislead. Nothing unsafe happens. | Open (DL14); the text correction is a code change and was not made |
| DA5 | Low | **Test-coverage gaps.** The repository suites test the nested-data stop with fakes only. The audit's scratch probe against a real scratch emulator passed 2/2: a subcollection under an existing document, and an orphaned subcollection under a deleted document, both stopped at `check_no_nested_data` with nothing deleted. Several safeguards are detected by a single unit test each. There are no rendered-component tests. | Open (DL11) |
| DA6 | Low | **Scope of the student-data check.** It refuses only `deleting`/`deleted` records, and only in emulator mode. It is checked once per request, so a deletion starting between the check and `/recommend`'s reads lets that one request read the student's own data. `/api/auth/me` is not covered; it returns only the uid and the admin flag. | Accepted for this milestone (DL3) |
| DA7 | Low | **Order of checks.** FastAPI 0.165 decodes the JSON body before any dependency, so a malformed JSON body gets 422 before the 404/503/401/403 checks on the emulator-mounted routes. Nothing is exposed; the routes do not exist in production. | Documented (Endpoints above) |

Issues from earlier milestones, unchanged by M3B-3: the student self-delete (DL5), M1 for Disable and Enable, M2
and M3, and L2–L7 (section K).

**Limitations**

| # | Limitation | Type | Status |
|---|---|---|---|
| DL1 | **Administrator-claim race.** Firebase offers no conditional Auth deletion, so a claim set after the last check (step 7) and before or during the Auth deletion cannot be detected; the window is one Admin SDK call. Claims can be set only outside the application (console, scripts). A claim detected mid-deletion stops it, but leaves the account disabled with the record `deleting`. The promoted administrator then cannot sign in, and the application offers no repair (manual). | Unavoidable race (documented) | Open; operational control: never grant claims to accounts being deleted |
| DL2 | The takeover grace is a timing assumption based on the backend clock and the SDK's documented timeouts, not a fence (see "Concurrency and in-flight calls"). Disable and Enable keep the 120-second lease (M1 open for them). | Design constraint | Open for production |
| DL3 | JL1 is closed only for `deleting`/`deleted` records and only in emulator mode. Disabled, missing and malformed records rely on Firebase Authentication on the backend as before (KL1). The record is checked once per request; `/api/auth/me` is not covered (uid and admin flag only) (audit DA6). | Boundary | Open for production |
| DL4 | The production `firestore.rules` have no account-access guard: with the production rules, an earlier session could re-create `users/{uid}` after a deletion. Not reachable today (no deletion route in production); the guard must be deployed before deletion is. | Production requirement | Open |
| DL5 | **Student self-delete (`Profile.jsx`) is unchanged and still unsafe** (S4, FL6): it deletes `users/{uid}` from the browser and then the Auth account, leaving `results`, `ai_assessments` and the access record. | Future development task | Open; required before production |
| DL6 | Tombstones and audit records are kept indefinitely; the uids in them are potentially identifying. Server logs contain uids. | Privacy | Retention policy needed before production |
| DL7 | A student document re-created after the tombstone is written cannot be removed by resuming: the deletion stays incomplete (`DATA_REMAINS`) until it is cleaned up manually. Not reachable through the application (the guard denies browser writes; no backend route writes these documents). | Edge case | Accepted (never reported as success) |
| DL8 | The recovery list is capped at 100 entries and reads every operation lock; it is not paginated. | Scale | Accepted for local use |
| DL9 | Student pages fall back to client-side recommendations or questions on a non-authentication failure, including 503 `ACCOUNT_STATUS_UNAVAILABLE` from the new check (existing pattern; the student's Firestore reads are refused anyway for an account in deletion). | Existing behaviour | Open (student pages out of scope) |
| DL10 | The typed email is a usability safeguard; an administrator token alone can delete any eligible student through the API (by design: administrators are trusted, every deletion is audited). The server-side `confirm_uid` proves only that the request names the target (audit DA3); a short-lived, server-issued confirmation would be stronger for production. | Boundary | Accepted for this milestone |
| DL11 | No rendered-component tests for the dialog, the panel or the incomplete-deletions list (E4, KL6). The nested-data stop is tested with fakes only in the repository suites (the audit's scratch probe against a real emulator passed 2/2, DA5). | Test-coverage gap | Open |
| DL12 | Emulator results are not production evidence (KL8). The emulator suites ran on alternative ports (KL9). | Test process | Recorded |
| DL13 | M2 and M3 (section K) concern Enable; they do not weaken a deletion (a deleted account's tokens are refused, its refresh token fails, test 1), but they remain open. | Carried over | Open |
| DL14 | A stale running deletion lock is shown as "Deletion in progress … Refresh in a moment", with no action, for up to 35 minutes. This happens after a crash, or when the lock could not be released or marked incomplete, including after a completed deletion reported with `lock_released: false`. The success note says resuming clears it, but Resume is offered only after the grace period (audit DA4). | Usability (texts mislead; nothing unsafe) | Open; text correction pending (code change) |
| DL15 | In the student flow, a successful results save opens the AI-assessment page, which calls the live AI providers at once (`ManualGradeEntry.jsx:103`, `UploadResults.jsx:118`). Browser tests that save results in the app therefore trigger AI generation (DA1; walkthrough W2). | Test process (existing student flow, unchanged) | Plan corrected: emulator deletion tests create `results/{uid}` with the REST helper |

**Production blockers** (none implemented; each needs separate approval):

- Everything pending in sections J and K:
  - access-record backfill;
  - guard deployment after the `auth_time` canary (DL4);
  - production registration through the backend;
  - the reconciliation sweep;
  - backend deployment;
  - M1 for Disable/Enable, M2 and M3.
- The student self-delete fix (DL5, S4, FL6).
- Mounting the account-action routes in production mode, with the student-data check enabled in production
  (DL3).
- A retention and privacy policy for tombstones, audit records, server logs and backups (DL6, data-scope gaps).
- An operational control for administrator claims (DL1).
- Monitoring of incomplete deletions.
- Rate limiting (L7).
- A production check of the Auth deletion and of the batch-precondition behaviour under contention (DL12).

### Future Admin Module report

A comprehensive Admin Module Development and Testing Report will be prepared after all Admin Module
milestones are completed. The report will consolidate implementation decisions, architecture, security
controls, test cases, results, defect history, limitations and supporting evidence from the milestone records.
