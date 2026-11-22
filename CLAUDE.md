# CLAUDE.md — Route2UniKL

Permanent instructions for Claude Code and developers working in this repository.
Before starting any milestone, read:

- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — current baseline, known issues, roadmap and next milestone.
- [docs/FIRESTORE_BASELINE.md](docs/FIRESTORE_BASELINE.md) — Firestore security reference, deployment and rollback.

## Project

Route2UniKL is a major-selection support system for UniKL foundation programmes. Students
(SPM leavers or Form 4/5) register, enter SPM results manually (automatic OCR upload is temporarily
disabled), take an AI-generated assessment, and receive programme recommendations and a preparation plan.
An Admin module is being built one milestone at a time on `feature/admin-module`.

| Area | Technology / location |
|---|---|
| Frontend | React 19, Vite 8, Tailwind CSS 4, React Router 7, Firebase JS SDK 12 — `frontend/` |
| Backend API | FastAPI on Python 3.12 (venv `backend/.venv`), Firebase Admin SDK — `backend/` |
| Identity | Firebase Authentication, Email/Password. Admin = custom claim `admin: true` |
| Database | Cloud Firestore, project `route2unikl` — `firestore.rules`, `firebase.json` |
| RAG | ChromaDB persistent store `backend/chroma_db/`, ONNX MiniLM-L6-v2 embeddings — `backend/core/chroma.py` |
| AI (backend) | `backend/services/rag_orchestrator.py`: OpenAI → Gemma via Gemini API → Ollama Cloud → static fallback; keys only in `backend/.env` |
| AI (browser) | None. Browser-side Gemini OCR is temporarily disabled (M1.5C deferred); `UploadResults.jsx` offers manual results entry |
| OCR (future) | Preferred: React → authenticated FastAPI → Gemini API, subject to a provider-terms and privacy review |
| Programme data | `frontend/src/assets/unikl_foundation_testplan.json` (35 programmes), Firestore `programs`, ChromaDB |

## Responsibilities and trust boundaries

- **Firebase Auth** proves identity. Admin exists only as the custom claim `admin: true` (strict boolean).
- **Firestore (browser SDK)**: students access only their own `users`, `results` and `ai_assessments`
  documents, with exact payload shapes. `programs` is public read; no browser writes for anyone, Admin included.
- **FastAPI** verifies the Firebase ID token on every protected route (`backend/core/auth.py`:
  `get_current_user`, `require_admin`, `ensure_same_user`). The Admin SDK **bypasses Firestore rules**,
  so every backend route must authorize the caller itself.
- **AI providers** (OpenAI, Gemini, Ollama Cloud) are called only by FastAPI. Ollama Cloud uses
  `OLLAMA_API_KEY` from `backend/.env` as a Bearer token. The browser never calls a provider directly.
- **Frontend guards** (`ProtectedAdminRoute`, `hasAdminClaim`) are UX only, never authorization.
- **Recommendations** (`backend/services/recommendation_service.py`) are rule-based over the bundled JSON.
  The **RAG assessment** retrieves context from ChromaDB and calls cloud LLMs; responses keep `source` and `model_used`.
- Client-supplied grades, `status: "verified"` and assessment answers/scores are self-asserted. Never treat them as trusted.

## Commands

| Task | Directory | Command |
|---|---|---|
| Frontend dev server / lint / build | `frontend/` | `npm run dev` · `npm run lint` · `npm run build` |
| Backend server (frontend expects port 8000) | `backend/` (venv active) | `uvicorn main:app --reload --port 8000` |
| Backend tests (mocked: no network, AI or ChromaDB) | `backend/` | `python -m unittest discover -s tests -t . -v` |
| Firestore rules tests (local emulator, `demo-route2unikl`) | `firestore-tests/` | `npm test` |

Rules tests need the Firebase CLI and Java. Keep `@firebase/rules-unit-testing` on 5.x while using Node 22.
Calling the assessment endpoint on a running backend consumes live AI quota.

## Security rules (non-negotiable)

- Never authorize by email address or by the Firestore `role` field (it stores the student type `spm_leaver` / `form_4_5`).
- Admin features go through FastAPI endpoints protected by `require_admin`. Never give the Admin claim
  browser access to student collections or programme writes in `firestore.rules`.
- Identity comes from the verified token, never from a client-supplied user ID.
- Never return mock or fallback data to disguise an authentication or authorization failure.
- Never print, copy or commit credentials: `.env` files, `backend/serviceAccountKey.json`, API keys,
  tokens or user records. Documentation names environment variables, never their values.
- Never place provider credentials or other secrets in `VITE_*` variables. The Vite dev server delivers
  every `VITE_*` variable in `frontend/.env` to the browser (even unused ones), and builds inline the ones
  the code reads. Provider keys belong only in `backend/.env`.
- The Firebase web configuration (`VITE_FIREBASE_*`) is intentionally public. It identifies the Firebase
  project and is not a provider secret; access is controlled by Firebase Auth, `firestore.rules` and
  API-key restrictions.
- Any `firestore.rules` change follows the change procedure in [docs/FIRESTORE_BASELINE.md](docs/FIRESTORE_BASELINE.md).

## Actions that require explicit owner approval every time

- Any deployment: `firebase deploy` (always with `--project route2unikl`; there is no `.firebaserc`), hosting, backend.
- Seeders and data scripts: `npm run seed`, `scripts/seedPrograms.js`, `scripts/uploadPrograms.js`,
  `backend/seed_chroma.py`, `scripts/build_master_json.py`.
- Live AI provider calls (the backend assessment endpoint and any future OCR endpoint).
- Admin SDK writes to production, setting custom claims, creating or deleting accounts.
- Signing in as, or impersonating, any account with privileged credentials or custom tokens.
- Destructive Git commands: `reset --hard`, `clean`, force-push, amending published commits.

## Milestone workflow

Work on one milestone at a time, in this order:

1. Inspect and plan.
2. Obtain owner approval of the plan. STOP until it is given.
3. Implement within the approved scope only.
4. Run the appropriate automated tests and report the results.
5. Obtain owner manual verification of the affected application behaviour, where applicable.
   Automated test results never replace owner verification. For documentation-only changes, the
   owner's review of the documents and the staged diff serves as manual verification.
6. Present the staged diff and the relevant Git status for final review. STOP.
7. Commit and push only after the owner replies with the exact phrase `VERIFIED — COMMIT THIS MILESTONE`.

Git rules:

- Stage explicit paths only. Never `git add .` or `git add -A`.
- Commit message style: `feat(admin): …`, `security(<area>): …`, `docs: …`.
- Never add `Co-Authored-By`, `Signed-off-by` or any AI-attribution trailer.
- Normal push only. No force-push, amend of published commits, merge or pull request without explicit permission.

## Preserve unrelated work

Never modify, stage, revert or delete: local changes to `.gitignore`, `backend/chroma_db/`,
`backend/.cache/`, `scripts/node_modules/`, any `.env` file, or service-account keys.
`backend/chroma_db/`, `backend/.cache/` and `scripts/node_modules/` are listed in `.gitignore`
but already tracked, so Git still reports their changes. Leave them unstaged.

## Windows environment notes

- PowerShell 5.1 `Set-Content -Encoding UTF8` writes a BOM that breaks `firestore.rules`. Write files with
  `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
- `firebase emulators:exec` can leave the Firestore emulator (Java, port 8080) running. Stop it only after
  confirming its command line contains `cloud-firestore-emulator` and `demo-`.
- PowerShell 5.1 mangles quotes in native-command arguments: pass commit messages with `git commit -F <file>`.
