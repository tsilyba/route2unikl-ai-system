// firestore-tests/rules.test.mjs
//
// Route2UniKL - Firestore Security Rules tests (Milestone 1.5B).
//
// Runs ONLY against the local Firestore emulator under the `demo-route2unikl`
// project ID (a "demo-" project can never reach production). All identities
// and documents are mock data created inside the emulator.
//
// Run from this folder:   npm test
// (requires the Firebase CLI and Java; see package.json)
//
// Write payloads below mirror the exact shapes written by the React app so the
// rules are verified against real application behaviour.

import { readFileSync } from 'node:fs';
import { after, before, beforeEach, describe, it } from 'node:test';
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from '@firebase/rules-unit-testing';
import {
  collection,
  deleteDoc,
  deleteField,
  doc,
  getDoc,
  getDocs,
  query,
  setDoc,
  updateDoc,
  where,
} from 'firebase/firestore';

const PROJECT_ID = 'demo-route2unikl';

if (!PROJECT_ID.startsWith('demo-')) {
  throw new Error('Refusing to run: tests must use a demo- project ID.');
}
if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error('FIRESTORE_EMULATOR_HOST is not set. Run via `npm test` (firebase emulators:exec).');
}

// ------------------------------------------------------------- mock identities
const STUDENT_A = { uid: 'studentA', email: 'student.a@example.test' };
const STUDENT_B = { uid: 'studentB', email: 'student.b@example.test' };
const NEW_STUDENT = { uid: 'newStudent', email: 'new.student@example.test' };
const LEGACY = { uid: 'legacyStudent', email: 'legacy.student@example.test' };
const ADMIN = { uid: 'admin1', email: 'admin@example.test' };
const PROGRAM_ID = 'unikl_miit_foundation_computer';

// ------------------------------------------- payloads mirroring the React app
// Register.jsx
const registrationPayload = (user, role = 'spm_leaver') => ({
  name: 'Ali Bin Abu',
  email: user.email,
  role,
  createdAt: new Date(),
});

// ProfileIngestion.jsx
const profileIngestionUpdate = () => ({
  chosenInterests: ['Computing & Digital Technology', 'Engineering Technology'],
  currentStep: 2,
  hasCompletedProfile: true,
  updatedAt: new Date(),
});

const sampleGrades = (count = 5) =>
  [
    { subject: 'BAHASA MELAYU', grade: 'A' },
    { subject: 'BAHASA INGGERIS', grade: 'A-' },
    { subject: 'MATEMATIK', grade: 'B+' },
    { subject: 'SEJARAH', grade: 'B' },
    { subject: 'FIZIK', grade: 'A' },
  ]
    .concat(Array.from({ length: Math.max(0, count - 5) }, (_, i) => ({ subject: `SUBJECT ${i}`, grade: 'C' })))
    .slice(0, count);

// ManualGradeEntry.jsx
const manualResultsPayload = (user) => ({
  userId: user.uid,
  email: user.email,
  results: sampleGrades(),
  updatedAt: new Date(),
  status: 'manual_entry',
  recordType: 'PREDICTED_GRADES',
  verificationMethod: 'MANUAL_ENTRY',
});

// UploadResults.jsx
const ocrResultsPayload = (user) => ({
  userId: user.uid,
  email: user.email,
  results: sampleGrades(),
  updatedAt: new Date(),
  status: 'verified',
  recordType: 'OFFICIAL_SPM_CERT',
  verificationMethod: 'AI_OCR_GEMINI',
});

const sampleAnswers = (count = 10) =>
  Array.from({ length: count }, (_, i) => ({
    category: `Category ${i % 5}`,
    question: `Question ${i + 1}?`,
    selectedOption: 'Option B',
    isCorrect: i % 2 === 0,
  }));

// DummyAI.jsx
const assessmentPayload = (user, overrides = {}) => ({
  userId: user.uid,
  userRole: 'spm_leaver',
  academicSnapshot: sampleGrades(),
  answers: sampleAnswers(),
  scoresByPathway: { 'Category 0': 1, 'Category 1': 0, 'Category 2': 1 },
  completedAt: new Date(),
  isDemoMode: true,
  ...overrides,
});

const sampleProgramme = () => ({
  program_id: PROGRAM_ID,
  title: 'Foundation in Computer Technology',
  level: 'Foundation',
  campuses: 'UniKL MIIT',
  major_category: 'Computing',
  pathway_category: 'Computing & Digital Technology',
  specialisation: 'Information Technology',
  min_spm_credits: 5,
  min_math_grade: 'C',
  min_bm_grade: 'C',
  min_bi_grade: 'C',
  requires_science: false,
  min_requirements_text: '5 credits including Mathematics.',
  short_description: 'Mock programme for emulator tests.',
  knowledge_context: 'Mock context.',
  link: 'https://example.test/programme',
  alternative_pathway_ids: ['a', 'b'],
  preparatory_guideline: [
    { title: 'Mock resource 1', platform: 'YouTube', url: 'https://example.test/1' },
    { title: 'Mock resource 2', platform: 'Khan Academy', url: 'https://example.test/2' },
  ],
});

// ------------------------------------------------------------ test harness
let testEnv;

const anonDb = () => testEnv.unauthenticatedContext().firestore();
const dbAs = (user, extraClaims = {}) =>
  testEnv.authenticatedContext(user.uid, { email: user.email, ...extraClaims }).firestore();
const adminDb = () => dbAs(ADMIN, { admin: true });
const stringClaimAdminDb = () => dbAs({ uid: 'admin2', email: 'admin2@example.test' }, { admin: 'true' });

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: {
      rules: readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8'),
    },
  });
});

after(async () => {
  await testEnv?.cleanup();
});

beforeEach(async () => {
  await testEnv.clearFirestore();
  await testEnv.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    // Existing, partially-progressed students.
    await setDoc(doc(db, 'users', STUDENT_A.uid), {
      ...registrationPayload(STUDENT_A),
      chosenInterests: ['Computing & Digital Technology'],
      currentStep: 2,
      hasCompletedProfile: true,
      updatedAt: new Date(),
    });
    await setDoc(doc(db, 'users', STUDENT_B.uid), registrationPayload(STUDENT_B, 'form_4_5'));
    await setDoc(doc(db, 'results', STUDENT_B.uid), manualResultsPayload(STUDENT_B));
    await setDoc(doc(db, 'ai_assessments', STUDENT_B.uid), assessmentPayload(STUDENT_B));
    // Legacy student document: older role value and an extra legacy field.
    await setDoc(doc(db, 'users', LEGACY.uid), {
      name: 'Legacy Student',
      email: LEGACY.email,
      role: 'upper_secondary',
      createdAt: new Date('2025-01-15T08:00:00Z'),
      legacyNote: 'field written by an older app version',
    });
    // Public programme catalogue entry.
    await setDoc(doc(db, 'programs', PROGRAM_ID), sampleProgramme());
  });
});

// =============================================================================
describe('1. Unauthenticated access to private student documents is denied', () => {
  it('cannot read users, results or ai_assessments documents', async () => {
    const db = anonDb();
    await assertFails(getDoc(doc(db, 'users', STUDENT_A.uid)));
    await assertFails(getDoc(doc(db, 'results', STUDENT_B.uid)));
    await assertFails(getDoc(doc(db, 'ai_assessments', STUDENT_B.uid)));
  });

  it('cannot list private collections', async () => {
    const db = anonDb();
    await assertFails(getDocs(collection(db, 'users')));
    await assertFails(getDocs(collection(db, 'results')));
    await assertFails(getDocs(collection(db, 'ai_assessments')));
  });

  it('cannot create or modify private documents', async () => {
    const db = anonDb();
    await assertFails(setDoc(doc(db, 'users', 'someone'), registrationPayload(NEW_STUDENT)));
    await assertFails(updateDoc(doc(db, 'users', STUDENT_A.uid), { name: 'Hacked' }));
    await assertFails(setDoc(doc(db, 'results', STUDENT_B.uid), manualResultsPayload(STUDENT_B)));
    await assertFails(deleteDoc(doc(db, 'users', STUDENT_A.uid)));
  });
});

// =============================================================================
describe('2. Students can access their own permitted records', () => {
  it('reads own users document', async () => {
    await assertSucceeds(getDoc(doc(dbAs(STUDENT_A), 'users', STUDENT_A.uid)));
  });

  it('reads own results and ai_assessments documents', async () => {
    const db = dbAs(STUDENT_B);
    await assertSucceeds(getDoc(doc(db, 'results', STUDENT_B.uid)));
    await assertSucceeds(getDoc(doc(db, 'ai_assessments', STUDENT_B.uid)));
  });

  it('reading an own document that does not exist yet is allowed (e.g. admin on Profile page)', async () => {
    await assertSucceeds(getDoc(doc(adminDb(), 'users', ADMIN.uid)));
    await assertSucceeds(getDoc(doc(dbAs(STUDENT_A), 'results', STUDENT_A.uid)));
  });
});

// =============================================================================
describe('3. Students cannot read or modify other students\' records', () => {
  it('cannot read another student\'s documents', async () => {
    const db = dbAs(STUDENT_A);
    await assertFails(getDoc(doc(db, 'users', STUDENT_B.uid)));
    await assertFails(getDoc(doc(db, 'results', STUDENT_B.uid)));
    await assertFails(getDoc(doc(db, 'ai_assessments', STUDENT_B.uid)));
  });

  it('cannot write or delete another student\'s documents', async () => {
    const db = dbAs(STUDENT_A);
    await assertFails(updateDoc(doc(db, 'users', STUDENT_B.uid), { name: 'Changed by A' }));
    await assertFails(deleteDoc(doc(db, 'users', STUDENT_B.uid)));
    await assertFails(setDoc(doc(db, 'results', STUDENT_B.uid), manualResultsPayload(STUDENT_B)));
    await assertFails(setDoc(doc(db, 'ai_assessments', STUDENT_B.uid), assessmentPayload(STUDENT_B)));
  });

  it('cannot create documents for another uid, or claim another uid inside own document', async () => {
    const db = dbAs(STUDENT_A);
    await assertFails(setDoc(doc(db, 'users', NEW_STUDENT.uid), registrationPayload(STUDENT_A)));
    await assertFails(setDoc(doc(db, 'results', STUDENT_A.uid), { ...manualResultsPayload(STUDENT_A), userId: STUDENT_B.uid }));
    await assertFails(setDoc(doc(db, 'ai_assessments', STUDENT_A.uid), assessmentPayload(STUDENT_A, { userId: STUDENT_B.uid })));
  });

  it('cannot enumerate student collections (list queries denied, even filtered to self)', async () => {
    const db = dbAs(STUDENT_A);
    await assertFails(getDocs(collection(db, 'users')));
    await assertFails(getDocs(collection(db, 'results')));
    await assertFails(getDocs(query(collection(db, 'results'), where('userId', '==', STUDENT_A.uid))));
    await assertFails(getDocs(collection(db, 'ai_assessments')));
  });
});

// =============================================================================
describe('4. Protected fields, privilege escalation and payload validation', () => {
  it('role, email and createdAt are immutable after registration', async () => {
    const ref = doc(dbAs(STUDENT_A), 'users', STUDENT_A.uid);
    await assertFails(updateDoc(ref, { role: 'form_4_5' }));
    await assertFails(updateDoc(ref, { email: 'other@example.test' }));
    await assertFails(updateDoc(ref, { createdAt: new Date('2020-01-01') }));
    await assertFails(updateDoc(ref, { role: deleteField() }));
  });

  it('students cannot grant themselves Admin through Firestore fields', async () => {
    const ref = doc(dbAs(STUDENT_A), 'users', STUDENT_A.uid);
    await assertFails(updateDoc(ref, { role: 'admin' }));
    await assertFails(updateDoc(ref, { admin: true }));
    await assertFails(updateDoc(ref, { isAdmin: true }));
    await assertFails(updateDoc(ref, { customClaims: { admin: true } }));
  });

  it('registration rejects escalation and malformed payloads', async () => {
    const db = dbAs(NEW_STUDENT);
    const ref = doc(db, 'users', NEW_STUDENT.uid);
    await assertFails(setDoc(ref, registrationPayload(NEW_STUDENT, 'admin')));
    await assertFails(setDoc(ref, { ...registrationPayload(NEW_STUDENT), admin: true }));
    await assertFails(setDoc(ref, { ...registrationPayload(NEW_STUDENT), email: 'someone.else@example.test' }));
    const { createdAt, ...missingCreatedAt } = registrationPayload(NEW_STUDENT);
    await assertFails(setDoc(ref, missingCreatedAt));
    await assertFails(setDoc(ref, { ...registrationPayload(NEW_STUDENT), name: '' }));
    await assertFails(setDoc(ref, { ...registrationPayload(NEW_STUDENT), role: 'upper_secondary' }));
  });

  it('rejects invalid values for editable profile fields', async () => {
    const ref = doc(dbAs(STUDENT_A), 'users', STUDENT_A.uid);
    await assertFails(updateDoc(ref, { currentStep: 9 }));
    await assertFails(updateDoc(ref, { currentStep: '3' }));
    await assertFails(updateDoc(ref, { chosenInterests: ['A', 'B', 'C'] }));
    await assertFails(updateDoc(ref, { chosenInterests: [] }));
    await assertFails(updateDoc(ref, { chosenInterests: [123] }));
    await assertFails(updateDoc(ref, { name: 'x'.repeat(101) }));
    await assertFails(updateDoc(ref, { hasUploadedResults: 'yes' }));
    await assertFails(updateDoc(ref, { unexpectedField: 'value' }));
  });

  it('rejects invalid results payloads', async () => {
    const db = dbAs(STUDENT_A);
    const ref = doc(db, 'results', STUDENT_A.uid);
    const base = manualResultsPayload(STUDENT_A);
    await assertFails(setDoc(ref, { ...base, status: 'verified' })); // mixed status/method combination
    await assertFails(setDoc(ref, { ...base, verificationMethod: 'AI_OCR_GEMINI' }));
    await assertFails(setDoc(ref, { ...base, email: 'other@example.test' }));
    await assertFails(setDoc(ref, { ...base, results: [] }));
    await assertFails(setDoc(ref, { ...base, results: sampleGrades(21) }));
    await assertFails(setDoc(ref, { ...base, extra: 'field' }));
    const { updatedAt, ...missingUpdatedAt } = base;
    await assertFails(setDoc(ref, missingUpdatedAt));
  });

  it('rejects invalid ai_assessments payloads', async () => {
    const ref = doc(dbAs(STUDENT_A), 'ai_assessments', STUDENT_A.uid);
    await assertFails(setDoc(ref, assessmentPayload(STUDENT_A, { extra: 'field' })));
    await assertFails(setDoc(ref, assessmentPayload(STUDENT_A, { answers: sampleAnswers(21) })));
    await assertFails(setDoc(ref, assessmentPayload(STUDENT_A, { answers: [] })));
    await assertFails(setDoc(ref, assessmentPayload(STUDENT_A, { isDemoMode: 'true' })));
    await assertFails(setDoc(ref, assessmentPayload(STUDENT_A, { userRole: '' })));
    const { completedAt, ...missingCompletedAt } = assessmentPayload(STUDENT_A);
    await assertFails(setDoc(ref, missingCompletedAt));
  });
});

// =============================================================================
describe('5. Admin custom claim grants NO browser access to private student data', () => {
  it('Admin cannot read or list private student collections from the browser', async () => {
    const db = adminDb();
    await assertFails(getDoc(doc(db, 'users', STUDENT_A.uid)));
    await assertFails(getDocs(collection(db, 'users')));
    await assertFails(getDoc(doc(db, 'results', STUDENT_B.uid)));
    await assertFails(getDoc(doc(db, 'ai_assessments', STUDENT_B.uid)));
  });

  it('Admin cannot modify student documents from the browser', async () => {
    const db = adminDb();
    await assertFails(updateDoc(doc(db, 'users', STUDENT_A.uid), { name: 'Edited by admin' }));
    await assertFails(deleteDoc(doc(db, 'users', STUDENT_A.uid)));
  });

  it('a non-boolean admin claim ("true") grants nothing either', async () => {
    const db = stringClaimAdminDb();
    await assertFails(getDoc(doc(db, 'users', STUDENT_A.uid)));
    await assertFails(setDoc(doc(db, 'programs', PROGRAM_ID), sampleProgramme()));
  });
});

// =============================================================================
describe('6. Programme master data cannot be modified from any browser client', () => {
  const attempts = (db) => [
    ['create a new programme', () => setDoc(doc(db, 'programs', 'new_programme'), sampleProgramme())],
    ['overwrite a programme', () => setDoc(doc(db, 'programs', PROGRAM_ID), sampleProgramme())],
    ['merge-write a programme (old seeder pattern)', () => setDoc(doc(db, 'programs', PROGRAM_ID), sampleProgramme(), { merge: true })],
    ['change eligibility criteria', () => updateDoc(doc(db, 'programs', PROGRAM_ID), { min_spm_credits: 1 })],
    ['change learning resources', () => updateDoc(doc(db, 'programs', PROGRAM_ID), { preparatory_guideline: [] })],
    ['delete a programme', () => deleteDoc(doc(db, 'programs', PROGRAM_ID))],
  ];

  for (const [label, makeDb] of [
    ['unauthenticated visitor', anonDb],
    ['student', () => dbAs(STUDENT_A)],
    ['Admin (custom claim) browser client', adminDb],
  ]) {
    it(`${label} cannot write programmes`, async () => {
      for (const [, attempt] of attempts(makeDb())) {
        await assertFails(attempt());
      }
    });
  }

  it('programme data is unchanged after all denied attempts', async () => {
    for (const [, attempt] of attempts(dbAs(STUDENT_A))) {
      await assertFails(attempt());
    }
    await testEnv.withSecurityRulesDisabled(async (context) => {
      const snap = await getDoc(doc(context.firestore(), 'programs', PROGRAM_ID));
      const data = snap.data();
      if (data.min_spm_credits !== 5 || data.preparatory_guideline.length !== 2) {
        throw new Error('Programme document was modified');
      }
    });
  });
});

// =============================================================================
describe('7. Public / student-visible programme catalogue', () => {
  it('unauthenticated visitors can read and list programmes (AllPrograms while signed out)', async () => {
    const db = anonDb();
    await assertSucceeds(getDoc(doc(db, 'programs', PROGRAM_ID)));
    await assertSucceeds(getDocs(collection(db, 'programs')));
  });

  it('students and Admin can read and list programmes (Dashboard, AllPrograms)', async () => {
    await assertSucceeds(getDocs(collection(dbAs(STUDENT_A), 'programs')));
    await assertSucceeds(getDocs(collection(adminDb(), 'programs')));
  });
});

// =============================================================================
describe('8. Student workflows remain functional (exact app payloads)', () => {
  it('full five-step journey for a newly registered SPM leaver', async () => {
    const db = dbAs(NEW_STUDENT);
    const userRef = doc(db, 'users', NEW_STUDENT.uid);

    // Register.jsx
    await assertSucceeds(setDoc(userRef, registrationPayload(NEW_STUDENT, 'spm_leaver')));
    // Dashboard.jsx
    await assertSucceeds(getDoc(userRef));
    await assertSucceeds(getDocs(collection(db, 'programs')));
    // ProfileIngestion.jsx
    await assertSucceeds(updateDoc(userRef, profileIngestionUpdate()));
    // UploadResults.jsx (SPM leaver, OCR path)
    await assertSucceeds(setDoc(doc(db, 'results', NEW_STUDENT.uid), ocrResultsPayload(NEW_STUDENT)));
    await assertSucceeds(updateDoc(userRef, { hasUploadedResults: true }));
    // DummyAI.jsx
    await assertSucceeds(getDoc(doc(db, 'results', NEW_STUDENT.uid)));
    await assertSucceeds(setDoc(doc(db, 'ai_assessments', NEW_STUDENT.uid), assessmentPayload(NEW_STUDENT)));
    await assertSucceeds(updateDoc(userRef, { currentStep: 3 }));
    // Recommendation.jsx
    await assertSucceeds(getDoc(doc(db, 'ai_assessments', NEW_STUDENT.uid)));
    await assertSucceeds(updateDoc(userRef, { currentStep: 4, hasViewedRecommendations: true }));
    // PreparationPlan.jsx
    await assertSucceeds(updateDoc(userRef, { currentStep: 5, hasCompletedPreparationPlan: true }));
  });

  it('Form 4/5 student: registration and manual grade entry', async () => {
    const db = dbAs(NEW_STUDENT);
    await assertSucceeds(setDoc(doc(db, 'users', NEW_STUDENT.uid), registrationPayload(NEW_STUDENT, 'form_4_5')));
    await assertSucceeds(setDoc(doc(db, 'results', NEW_STUDENT.uid), manualResultsPayload(NEW_STUDENT)));
    await assertSucceeds(updateDoc(doc(db, 'users', NEW_STUDENT.uid), { hasUploadedResults: true }));
  });

  it('retaking the assessment and re-saving results overwrites own documents', async () => {
    const db = dbAs(STUDENT_B);
    await assertSucceeds(setDoc(doc(db, 'ai_assessments', STUDENT_B.uid), assessmentPayload(STUDENT_B, { isDemoMode: false })));
    await assertSucceeds(setDoc(doc(db, 'results', STUDENT_B.uid), manualResultsPayload(STUDENT_B)));
  });

  it('revisiting the profile step (currentStep back to 2) is allowed', async () => {
    const ref = doc(dbAs(STUDENT_A), 'users', STUDENT_A.uid);
    await assertSucceeds(updateDoc(ref, { currentStep: 5 }));
    await assertSucceeds(updateDoc(ref, profileIngestionUpdate()));
  });

  it('Profile.jsx full-document save that only edits the name is allowed', async () => {
    const db = dbAs(STUDENT_A);
    const ref = doc(db, 'users', STUDENT_A.uid);
    const snap = await assertSucceeds(getDoc(ref));
    await assertSucceeds(updateDoc(ref, { ...snap.data(), name: 'Ali Updated' }));
  });

  it('Profile.jsx full-document save that sneaks in a role change is denied', async () => {
    const db = dbAs(STUDENT_A);
    const ref = doc(db, 'users', STUDENT_A.uid);
    const snap = await assertSucceeds(getDoc(ref));
    await assertFails(updateDoc(ref, { ...snap.data(), name: 'Ali Updated', role: 'form_4_5' }));
  });

  it('Profile.jsx delete account removes own users document (existing behaviour)', async () => {
    await assertSucceeds(deleteDoc(doc(dbAs(STUDENT_A), 'users', STUDENT_A.uid)));
  });

  it('legacy student document (old role value + extra field) keeps working', async () => {
    const db = dbAs(LEGACY);
    const ref = doc(db, 'users', LEGACY.uid);
    const snap = await assertSucceeds(getDoc(ref));
    await assertSucceeds(updateDoc(ref, profileIngestionUpdate()));
    await assertSucceeds(updateDoc(ref, { ...snap.data(), name: 'Legacy Renamed' }));
    // Legacy fields stay read-only like other non-editable fields.
    await assertFails(updateDoc(ref, { legacyNote: 'changed' }));
    await assertFails(updateDoc(ref, { role: 'form_4_5' }));
  });
});

// =============================================================================
describe('9. Unauthorized collections, sub-collections and deletes are blocked', () => {
  it('unknown collections cannot be read or written', async () => {
    const db = dbAs(STUDENT_A);
    for (const path of ['recommendations/studentA', 'learning_resources/x', 'admin_settings/config', 'announcements/1']) {
      await assertFails(getDoc(doc(db, path)));
      await assertFails(setDoc(doc(db, path), { any: 'value' }));
    }
    await assertFails(setDoc(doc(anonDb(), 'anything/else'), { any: 'value' }));
    await assertFails(setDoc(doc(adminDb(), 'system_info/settings'), { any: 'value' }));
  });

  it('sub-collections under a student document are denied, even for the owner', async () => {
    const db = dbAs(STUDENT_A);
    await assertFails(setDoc(doc(db, 'users', STUDENT_A.uid, 'private', 'x'), { any: 'value' }));
    await assertFails(getDoc(doc(db, 'users', STUDENT_A.uid, 'private', 'x')));
  });

  it('owners cannot delete results or ai_assessments documents (no such feature)', async () => {
    const db = dbAs(STUDENT_B);
    await assertFails(deleteDoc(doc(db, 'results', STUDENT_B.uid)));
    await assertFails(deleteDoc(doc(db, 'ai_assessments', STUDENT_B.uid)));
  });
});

// =============================================================================
describe('10. Registration and login-related operations remain compatible', () => {
  it('a new account can create and immediately read its own users document', async () => {
    const db = dbAs(NEW_STUDENT);
    const ref = doc(db, 'users', NEW_STUDENT.uid);
    await assertSucceeds(setDoc(ref, registrationPayload(NEW_STUDENT)));
    await assertSucceeds(getDoc(ref));
  });

  it('re-running registration on an existing document cannot reset createdAt or role', async () => {
    const db = dbAs(STUDENT_A);
    await assertFails(setDoc(doc(db, 'users', STUDENT_A.uid), registrationPayload(STUDENT_A, 'form_4_5')));
  });

  it('a signed-in user without an email claim cannot register a users document', async () => {
    const db = testEnv.authenticatedContext('noEmailUser').firestore();
    await assertFails(setDoc(doc(db, 'users', 'noEmailUser'), {
      name: 'No Email', email: 'claimed@example.test', role: 'spm_leaver', createdAt: new Date(),
    }));
  });
});

// =============================================================================
describe('11. Email must be a non-empty string matching the token email (W2 regression)', () => {
  // Accounts whose Firebase token carries no email claim (e.g. anonymous or
  // phone sign-in, should such providers ever be enabled).
  const noEmailContexts = () => [
    ['no email claim', 'noEmailUser', testEnv.authenticatedContext('noEmailUser').firestore()],
    ['anonymous sign-in', 'anonUser',
      testEnv.authenticatedContext('anonUser', { firebase: { sign_in_provider: 'anonymous' } }).firestore()],
  ];

  const userDocWith = (email) => ({ name: 'Test User', email, role: 'spm_leaver', createdAt: new Date() });
  const resultsWith = (uid, email) => ({ ...manualResultsPayload({ uid, email: 'placeholder' }), email });

  it('a legitimate Email/Password student can register and save results with their own email', async () => {
    const db = dbAs(NEW_STUDENT);
    await assertSucceeds(setDoc(doc(db, 'users', NEW_STUDENT.uid), registrationPayload(NEW_STUDENT)));
    await assertSucceeds(setDoc(doc(db, 'results', NEW_STUDENT.uid), manualResultsPayload(NEW_STUDENT)));
    await assertSucceeds(setDoc(doc(db, 'results', NEW_STUDENT.uid), ocrResultsPayload(NEW_STUDENT)));
  });

  it('accounts without an email claim cannot create users or results documents', async () => {
    for (const [, uid, db] of noEmailContexts()) {
      for (const email of [null, '', 'someone@example.test']) {
        await assertFails(setDoc(doc(db, 'users', uid), userDocWith(email)));
        await assertFails(setDoc(doc(db, 'results', uid), resultsWith(uid, email)));
      }
    }
  });

  it('a student cannot write a null, empty, non-string or different email', async () => {
    const db = dbAs(NEW_STUDENT);
    for (const email of [null, '', 123, 'other.person@example.test', `${NEW_STUDENT.email} `]) {
      await assertFails(setDoc(doc(db, 'users', NEW_STUDENT.uid), userDocWith(email)));
      await assertFails(setDoc(doc(db, 'results', NEW_STUDENT.uid), resultsWith(NEW_STUDENT.uid, email)));
    }
    const { email, ...missingEmail } = manualResultsPayload(NEW_STUDENT);
    await assertFails(setDoc(doc(db, 'results', NEW_STUDENT.uid), missingEmail));
  });

  it('existing authorized updates still work and email stays read-only', async () => {
    // Existing documents are not re-validated on unrelated updates, including
    // an older document that has no email field at all.
    await testEnv.withSecurityRulesDisabled(async (context) => {
      await setDoc(doc(context.firestore(), 'users', 'oldStudent'), {
        name: 'Old Student', role: 'spm_leaver', createdAt: new Date('2024-06-01T00:00:00Z'),
      });
    });
    const oldDb = dbAs({ uid: 'oldStudent', email: 'old.student@example.test' });
    await assertSucceeds(updateDoc(doc(oldDb, 'users', 'oldStudent'), profileIngestionUpdate()));
    await assertFails(updateDoc(doc(oldDb, 'users', 'oldStudent'), { email: 'old.student@example.test' }));

    const dbA = dbAs(STUDENT_A);
    const refA = doc(dbA, 'users', STUDENT_A.uid);
    await assertSucceeds(updateDoc(refA, profileIngestionUpdate()));
    const snap = await assertSucceeds(getDoc(refA));
    await assertSucceeds(updateDoc(refA, { ...snap.data(), name: 'Renamed Student' }));
    await assertFails(updateDoc(refA, { email: null }));
    await assertFails(updateDoc(refA, { email: '' }));

    await assertSucceeds(setDoc(doc(dbAs(STUDENT_B), 'results', STUDENT_B.uid), manualResultsPayload(STUDENT_B)));
    await assertSucceeds(getDoc(doc(dbAs(STUDENT_B), 'results', STUDENT_B.uid)));
  });
});

// =============================================================================
describe('12. Known limitation W1 (accepted for 1.5B): re-creating own profile', () => {
  it('can change the student type, but can never grant Admin or widen access', async () => {
    const db = dbAs(STUDENT_A);
    const ref = doc(db, 'users', STUDENT_A.uid);
    await assertSucceeds(deleteDoc(ref));

    // Admin can never be obtained through re-creation.
    await assertFails(setDoc(ref, registrationPayload(STUDENT_A, 'admin')));
    await assertFails(setDoc(ref, { ...registrationPayload(STUDENT_A), admin: true }));
    await assertFails(setDoc(ref, { ...registrationPayload(STUDENT_A), isAdmin: true }));

    // Documented limitation: switching between the two student types succeeds.
    await assertSucceeds(setDoc(ref, registrationPayload(STUDENT_A, 'form_4_5')));

    // Access is still limited to the student's own data afterwards.
    await assertFails(getDoc(doc(db, 'users', STUDENT_B.uid)));
    await assertFails(getDocs(collection(db, 'users')));
    await assertFails(updateDoc(doc(db, 'programs', PROGRAM_ID), { min_spm_credits: 1 }));
  });
});
