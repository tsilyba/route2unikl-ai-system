# Firestore Security Baseline — Route2UniKL

| | |
|---|---|
| Firebase project ID | `route2unikl` |
| Rules file | [`firestore.rules`](../firestore.rules) (`rules_version = '2'`) |
| Deployment configuration | [`firebase.json`](../firebase.json): `firestore.rules` path; emulator on `127.0.0.1:8080`, UI disabled, `singleProjectMode` |
| Project alias | None (no `.firebaserc`). Always pass `--project route2unikl`. |
| Rules introduced in | M1.5B, commit `2287868` |
| Production deployment | 22 November 2026 (MYT), owner-reported |
| Rules tests | [`firestore-tests/rules.test.mjs`](../firestore-tests/rules.test.mjs): 12 suites, 44 tests |
| Related documents | [CLAUDE.md](../CLAUDE.md) · [PROJECT_STATUS.md](PROJECT_STATUS.md) |

Evidence labels (Repo-verified, Emulator tests, Browser smoke test, Console, Rules Playground,
Untested) have the meanings defined in [PROJECT_STATUS.md](PROJECT_STATUS.md#evidence-labels).
Facts marked **owner-reported** were supplied by the project owner and cannot be verified from this repository.

## 1. Historical vulnerability and remediation

### Previous production rules (owner-reported)

The previous production rules contained:

```javascript
match /programs/{programId} {
  allow read: if true;
  allow write: if request.auth != null;
}
```

The student collections (`users`, `results`, `ai_assessments`) used owner-based read/write permissions.
The exact text and field-level behaviour of those rules are not recorded in this repository; the
original rules backup is kept outside Git (see [section 6](#6-backup-and-rollback)).

### Impact

`request.auth != null` is true for every signed-in account, and anyone can self-register a student
account. Therefore **any authenticated student had direct write permission on every programme
document**: they could create, overwrite or delete programmes, including eligibility criteria
(for example `min_spm_credits`) and `preparatory_guideline` learning resources, straight from the
browser without using the app UI. The programme catalogue shown by `AllPrograms.jsx` and
`Dashboard.jsx` reads Firestore `programs`, so such changes would have affected every user.
Recommendations and preparation plans read the bundled JSON, so they were not directly affected.

The application itself relied on this permission: a "Seed Programs to Firestore" button, rendered in
`frontend/src/App.jsx` on every page, ran `seedFoundationPrograms()` from the former
`frontend/src/assets/seedProgram.js`. That function deleted every `programs` document not in the
bundled JSON and merge-wrote the 35 programmes from the browser.

### Remediation (M1.5B, commit `2287868`)

1. `programs`: `allow read: if true; allow write: if false;`. No browser client can write programme
   data, including users with the Admin claim. Programme changes are made only through the Admin SDK.
2. The seed button and `frontend/src/assets/seedProgram.js` were removed.
3. Student collections: owner-only `get`, `list` denied, exact field allow-lists, type and size
   validation, immutable `role` / `email` / `createdAt`, and the written email must equal the token email.
4. Every other path is denied by default (explicit catch-all `match /{document=**}`).
5. 44 emulator tests cover the new rules (section 4.2).

## 2. Current collection permissions

| Path | Not signed in | Owner (student) | Another student | Browser user with `admin: true` | Admin SDK (FastAPI, scripts) |
|---|---|---|---|---|---|
| `users/{uid}` | Denied | `get`; `create` (validated); `update` (allow-listed fields); `delete` | Denied | Same as any signed-in user (own document only); the claim grants nothing extra | Full access (bypasses rules) |
| `results/{uid}` | Denied | `get`; `create` / `update` (validated full document); no `delete` | Denied | Same as any signed-in user | Full access |
| `ai_assessments/{uid}` | Denied | `get`; `create` / `update` (validated full document); no `delete` | Denied | Same as any signed-in user | Full access |
| `programs/{programId}` | Read (`get`, `list`) | Read | Read | Read | Full access |
| Any other path or sub-collection | Denied | Denied | Denied | Denied | Full access |

`list` queries on `users`, `results` and `ai_assessments` are denied for everyone, even when filtered to the caller's own uid.

### Validation details

**`users/{uid}`**, written by `Register.jsx` (create); `ProfileIngestion.jsx`, `ManualGradeEntry.jsx`,
`UploadResults.jsx`, `DummyAI.jsx`, `Recommendation.jsx`, `PreparationPlan.jsx` and `Profile.jsx` (update);
`Profile.jsx` (delete) until M3C. Since M3C (not yet committed) the app no longer deletes from the browser: in
local emulator mode it uses a protected backend endpoint, and the production build offers no self-delete. The
deployed rule still allows the owner's delete (see W1 below; PROJECT_STATUS.md section 8 M).

- Create: exactly `name`, `email`, `role`, `createdAt`. `name` is a non-empty string of at most 100
  characters; `email` is a non-empty string (at most 254) equal to the token email; `role` is
  `spm_leaver` or `form_4_5`; `createdAt` is a timestamp.
- Update: changed fields must be within `name`, `chosenInterests`, `currentStep`,
  `hasCompletedProfile`, `hasUploadedResults`, `hasViewedRecommendations`,
  `hasCompletedPreparationPlan`, `updatedAt`. `chosenInterests` is a list of 1–2 non-empty strings;
  `currentStep` is an integer from 1 to 5; flags are booleans; `updatedAt` is a timestamp.
  `role`, `email` and `createdAt` cannot change. Unchanged fields in a full-document write are ignored.
- Delete: allowed for the owner (accepted limitation W1, section 7).

**`results/{uid}`**, written by `ManualGradeEntry.jsx` and `UploadResults.jsx`:

- Exactly `userId`, `email`, `results`, `updatedAt`, `status`, `recordType`, `verificationMethod`.
- `userId` equals the document uid; `email` equals the token email; `results` is a list of 1–20
  entries; `updatedAt` is a timestamp.
- (`status`, `recordType`, `verificationMethod`) is either (`manual_entry`, `PREDICTED_GRADES`,
  `MANUAL_ENTRY`) or (`verified`, `OFFICIAL_SPM_CERT`, `AI_OCR_GEMINI`).
- The contents of each entry in `results` are not validated.

**`ai_assessments/{uid}`**, written by `DummyAI.jsx`:

- Exactly `userId`, `userRole`, `academicSnapshot`, `answers`, `scoresByPathway`, `completedAt`, `isDemoMode`.
- `userId` equals the document uid; `userRole` is a non-empty string (at most 50); `academicSnapshot`
  is a list of at most 20; `answers` is a list of 1–20; `scoresByPathway` is a map of at most 20 keys;
  `completedAt` is a timestamp; `isDemoMode` is a boolean.
- The contents of these lists and maps are not validated.

## 3. Admin custom-claim authorization design

- **Admin is the Firebase Auth custom claim `admin: true`** (boolean). It was set outside this
  repository with the Firebase Admin SDK; no script in the repository sets claims.
- A non-boolean value such as `"true"` is not Admin: FastAPI checks `decoded.get("admin") is True`,
  and emulator suite 5 confirms the rules grant nothing for it.
- **Frontend (UX only):** `hasAdminClaim(user, { forceRefresh: true })` in
  `frontend/src/utils/adminClaims.js` reads the claim with `getIdTokenResult(true)`. It is used by
  `Login.jsx`, `LandingPage.jsx` and `ProtectedAdminRoute.jsx` for navigation. It is not authorization.
- **Backend (enforcement):** `get_current_user` in `backend/core/auth.py` verifies the ID token with
  `check_revoked=True` and a 5-second clock-skew allowance. `require_admin` returns HTTP 403 unless
  the verified token carries `admin: true`. `GET /api/admin/verify` exposes this check.
- **Firestore rules never reference the Admin claim.** Admins have no extra browser access to student
  collections and cannot write `programs`.
- `users/{uid}.role` stores the student type only and is never used for authorization.
- Claim changes take effect only when the user's ID token is refreshed (forced refresh in the app,
  or sign out and in again).
- When removing Admin access, also revoke the user's refresh tokens. Otherwise an already-issued ID
  token still carrying `admin: true` remains valid until it expires. Revoked tokens are then rejected
  by the backend's `check_revoked=True`.

## 4. Verification evidence

### 4.1 Repository-verified

- `firestore.rules` and `firebase.json` content as described in sections 1–2.
- The seed button and `seedProgram.js` are absent from the current tree (removed in `2287868`).

### 4.2 Automated emulator tests

- Command: `npm test` in `firestore-tests/`, which runs
  `firebase emulators:exec --only firestore --project demo-route2unikl --config ../firebase.json`.
- Safety: the suite refuses to run unless the project ID starts with `demo-` and
  `FIRESTORE_EMULATOR_HOST` is set. It can never reach production.
- Tooling: `@firebase/rules-unit-testing` 5.0.2, `firebase` 12.12.1, Node 22.
- **Recorded result (M1.5B, 22 Nov 2026): 12 suites, 44 tests, 44 passed, 0 failed.**
- Negative control: the W2 regression suite failed against the pre-fix rules (43 passed, 1 failed).
- Not re-run for this documentation baseline.

| Suite | Covers |
|---|---|
| 1 | Unauthenticated access to private student documents is denied |
| 2 | Students can access their own permitted records |
| 3 | Students cannot read or modify other students' records |
| 4 | Protected fields, privilege escalation and payload validation |
| 5 | The Admin custom claim grants no browser access to private student data |
| 6 | Programme data cannot be modified from any browser client |
| 7 | Public / student-visible programme catalogue |
| 8 | Student workflows remain functional with exact app payloads |
| 9 | Unauthorized collections, sub-collections and deletes are blocked |
| 10 | Registration and login-related operations remain compatible |
| 11 | Email must be a non-empty string matching the token email (W2 regression) |
| 12 | Known limitation W1: re-creating one's own profile never grants Admin |

### 4.3 Firebase CLI dry run (owner-reported)

```powershell
firebase deploy --only firestore:rules --project route2unikl --dry-run
```

Completed successfully on 22 Nov 2026 (MYT). Nothing was deployed by this step.

### 4.4 Production deployment (owner-reported)

```powershell
firebase deploy --only firestore:rules --project route2unikl
```

Completed successfully on 22 Nov 2026 (MYT). **Only Firestore Security Rules were deployed.**
The React frontend and the FastAPI backend are not deployed (see [PROJECT_STATUS.md](PROJECT_STATUS.md#4-deployment-status)).

### 4.5 Firebase Console verification (owner-reported)

- The published rules were verified in the Firestore Rules tab of the Firebase Console.
- A saved academic results document was confirmed in the Firestore data view.

### 4.6 Production smoke tests in the real application (owner-reported)

Run from the local React development server connected to production Firebase. None of these tests
needs the FastAPI backend.

| Test | Result | Notes |
|---|---|---|
| Public programme catalogue read | Passed | `programs` read |
| Existing student login and profile read | Passed | Owner `get` on `users/{uid}` |
| Student profile update and persistence | Passed | Allow-listed `users` update |
| New student registration and profile creation | Passed | Validated `users` create |
| Academic results save | Passed; document confirmed in Console | Save method (manual entry or OCR) not recorded. Browser read-back of the saved results was not independently tested. |
| Admin login, dashboard authorization and refresh | Passed | Browser claim check only (`ProtectedAdminRoute`). The dashboard is a placeholder and makes no backend Admin call. |

### 4.7 Rules Playground simulations (owner-reported)

These were simulations in the Firebase Console, not application tests.

| Simulation | Result |
|---|---|
| Student reads their own `results/{uid}` | Allowed (expected) |
| Student deletes a `programs` document | Denied (expected) |

### 4.8 Not verified in production

- Cross-student read/write denial with two real accounts.
- `ai_assessments` write and read (AI assessment flow) and the recommendation flow.
- Browser read-back of saved academic results.
- The OCR upload save path (the save method used in the smoke test was not recorded).
- The Profile "delete account" flow.
- Denial of `list` queries and of unauthenticated access to private documents.
- Denial of student-collection access for an Admin-claim browser user.

## 5. Change procedure for future rules changes

1. Change `firestore.rules` only within an approved milestone.
2. Add or update emulator tests and run `npm test` in `firestore-tests/`. All tests must pass, and
   each new protection needs a negative control (a test that fails without it).
3. Review the rules diff and the test output with the project owner.
4. Back up the currently published production rules outside Git.
5. Run the dry run: `firebase deploy --only firestore:rules --project route2unikl --dry-run`.
6. Deploy only with explicit owner approval: `firebase deploy --only firestore:rules --project route2unikl`.
7. Verify the published rules in the Console, smoke-test with the local dev server against production,
   and update this document with labelled evidence.

## 6. Backup and rollback

- **Backup:** the project owner copied the previous production rules before deployment. The backup
  is stored outside Git and is intentionally not committed, because it contains the vulnerable
  `programs` rule. Its location is not recorded in this repository.
- **Rollback is an emergency measure only.** Restoring the previous rules re-opens the historical
  vulnerability: any authenticated user could again write programme data. It requires explicit
  owner approval and should be followed by a fix-forward deployment.
- **Option A — Firebase Console:** open Firestore → Rules, use the rules history (or paste the backup)
  to restore the previous version, review it, then Publish.
- **Option B — Firebase CLI:** never overwrite the repository's `firestore.rules`. Place the backup
  as `firestore.rules` in a temporary directory with a minimal `firebase.json`, then run the dry run
  and the deploy with `--only firestore:rules --project route2unikl --config <temp>/firebase.json`.
- **After any rollback or redeploy:** confirm the published rules in the Console, allow a few minutes
  for propagation, repeat the smoke tests in section 4.6, and record the event in this document.

## 7. Remaining security test gaps and accepted limitations

**Emulator tests not yet written:**

- An Admin-claim browser client creating or overwriting `results` and `ai_assessments`
  (suite 5 covers reads, `list` on `users`, and `users` update/delete).
- Another student deleting `results` or `ai_assessments` (denied by the rules, but only the owner case is tested, in suite 9).
- A partial `updateDoc` on another student's `results` or `ai_assessments` (suite 3 uses full `setDoc`).

**Not enforced by the rules (design limits):**

- The contents of `results` entries, `academicSnapshot`, `answers` and `scoresByPathway`.
- **W1 (accepted in M1.5B):** an owner may delete and re-create their `users` document, which can
  change the student type and reset `createdAt`. It can never grant Admin (suite 12). Planned fix:
  a protected FastAPI account-deletion endpoint, then remove the client `allow delete`. M3C: the endpoint
  exists for the local emulators only, and the client delete is removed from the test-only experimental
  rules; this production rule is unchanged until a change is approved through section 5.

**Production:** the gaps listed in section 4.8. **Process:** no CI runs the rules tests automatically.

## 8. Limits of client rules versus Admin SDK access

- **The Firebase Admin SDK bypasses Firestore Security Rules.** FastAPI (`backend/core/firebase.py`,
  using `backend/serviceAccountKey.json`) and the scripts (`scripts/seedPrograms.js`,
  `scripts/uploadPrograms.js`) have full read/write access to every collection regardless of
  `firestore.rules`; `allow write: if false` on `programs` does not stop them. The service-account
  key is the most sensitive credential in the project. It stays outside Git and must never be copied.
- **The Admin custom claim must be verified on every protected backend route.** Admin operations must
  depend on `require_admin`, and student operations must use the token uid (`ensure_same_user`).
- **Frontend Admin route checks are not server-side authorization.** `ProtectedAdminRoute` and
  `hasAdminClaim` run in the browser and can be bypassed by modifying client code.
- **App Check (not configured) is not a substitute for authorization, rate limits or cost controls.**
  It can reduce access from unattested clients, but it does not identify or authorize users, and
  public `programs` reads remain billable. Budget alerts, quotas and rate limits are separate controls.
- **Rules validate shape, not truth.** Client-supplied grades, `status: "verified"`,
  `verificationMethod`, assessment answers, `isCorrect` values and `scoresByPathway` must not
  automatically be treated as trusted information by recommendations, Admin reports or decisions.
- **Programme updates need a data-consistency strategy.** Programme data lives in Firestore `programs`
  (catalogue), the bundled JSON (recommendations, preparation plans, RAG programme IDs) and ChromaDB
  (RAG retrieval, seeded from the JSON). Editing one source does not update the others. A single source
  of truth with synchronisation and re-indexing is required before Admin programme management (M4–M6).
- **Account lifecycle is outside the rules.** Deleting or disabling Auth accounts and cleaning up the
  associated `results` / `ai_assessments` documents must be done by a protected backend process.
- **Rules are not filters.** `list` queries on private collections are denied entirely, so Admin
  listings of students must come from `require_admin` FastAPI endpoints. Implemented read-only in M3A:
  `GET /api/admin/users` and `GET /api/admin/users/{uid}` read Firebase Authentication and Firestore
  through the Admin SDK with field masks, and return allow-listed fields and metadata-only record
  summaries (no grades or answers). The rules were not changed.
