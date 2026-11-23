// firestore-tests/account-access.experimental.suite.mjs
//
// EXPERIMENTAL account-access guard (M3B-1B-P0): local emulator tests only.
//
// Loads the TEST-ONLY rules file account-access.experimental.rules, which
// firebase.json does not reference (so `firebase deploy` never uses it), and runs
//   - the original 44 regression tests (sections 1-12, shared with
//     rules.test.mjs), with an active account_access record for every identity;
//   - 56 account-access guard tests (sections 0 and 13-16).
//
// The file name deliberately does not match the node --test default patterns,
// so `npm test` and a bare `node --test` run only the production baseline.
// Run this suite explicitly, from this folder (requires the Firebase CLI and Java):
//   firebase emulators:exec --only firestore --project demo-route2unikl --config ../firebase.json "node --test --test-reporter=spec account-access.experimental.suite.mjs"

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { assertFails, assertSucceeds } from '@firebase/rules-unit-testing';
import {
  Timestamp,
  collection,
  collectionGroup,
  deleteDoc,
  deleteField,
  doc,
  documentId,
  getDoc,
  getDocs,
  query,
  setDoc,
  updateDoc,
  where,
} from 'firebase/firestore';
import {
  ADMIN,
  LEGACY,
  NEW_STUDENT,
  STUDENT_A,
  STUDENT_B,
  adminDb,
  anonDb,
  assessmentPayload,
  dbAs,
  defineRegressionTests,
  manualResultsPayload,
  registrationPayload,
  setupRulesEnvironment,
  stringClaimAdminDb,
  testEnv,
} from './shared-rules-suite.mjs';

// ------------------------------------ account-access guard fixtures (M3B-1B-P0)
// Every identity used in this file starts with an active, well-formed
// account_access record. Without it, the original tests that expect success
// would fail, and the original deny tests would pass for the wrong reason (the
// guard, not the ownership or payload check they are meant to exercise).
// Guard tests overwrite or remove the record where they need another state.
const ACTIVE_RECORD = { state: 'active', version: 1 };
const FIXTURE_UIDS = [
  STUDENT_A.uid, STUDENT_B.uid, NEW_STUDENT.uid, LEGACY.uid, ADMIN.uid,
  'admin2', 'oldStudent', 'noEmailUser', 'anonUser',
];

// Reference second for session-threshold tests: 2027-01-15T08:00:00Z.
const S = 1_800_000_000;

const RULES_SOURCE = setupRulesEnvironment({
  rulesFile: new URL('./account-access.experimental.rules', import.meta.url),
  seed: (db) => Promise.all(FIXTURE_UIDS.map((uid) => setDoc(doc(db, 'account_access', uid), ACTIVE_RECORD))),
});
if (!RULES_SOURCE.includes('function isActiveOwner(uid)')) {
  throw new Error('Refusing to run: the loaded rules file does not contain the account-access guard.');
}

// Backend-side helpers (security rules bypassed), standing in for the Admin SDK.
const setAccessRecord = (uid, record) =>
  testEnv.withSecurityRulesDisabled((context) =>
    setDoc(doc(context.firestore(), 'account_access', uid), record));
const removeAccessRecord = (uid) =>
  testEnv.withSecurityRulesDisabled((context) =>
    deleteDoc(doc(context.firestore(), 'account_access', uid)));
const removePrivateDocuments = (uid) =>
  testEnv.withSecurityRulesDisabled((context) =>
    Promise.all(['users', 'results', 'ai_assessments'].map((name) =>
      deleteDoc(doc(context.firestore(), name, uid)))));

// What the backend sees for one uid (null = document absent).
const backendView = async (uid) => {
  const view = {};
  await testEnv.withSecurityRulesDisabled(async (context) => {
    for (const name of ['account_access', 'users', 'results', 'ai_assessments']) {
      const snap = await getDoc(doc(context.firestore(), name, uid));
      view[name] = snap.exists() ? snap.data() : null;
    }
  });
  return view;
};

// Applies assertSucceeds or assertFails to each labelled operation in turn and
// names the operation in any failure.
const expectEach = async (expectation, operations, context) => {
  for (const [label, operation] of operations) {
    try {
      await expectation(operation());
    } catch (error) {
      throw new Error(`${context} / ${label}: ${error.message}`);
    }
  }
};

// Every operation the rules permit on an owner's EXISTING private documents
// (STUDENT_B owns all three). The delete runs last.
const existingDocumentOps = (db, owner) => [
  ['get users', () => getDoc(doc(db, 'users', owner.uid))],
  ['get results', () => getDoc(doc(db, 'results', owner.uid))],
  ['get ai_assessments', () => getDoc(doc(db, 'ai_assessments', owner.uid))],
  ['update users', () => updateDoc(doc(db, 'users', owner.uid), { currentStep: 3, updatedAt: new Date() })],
  ['update results', () => setDoc(doc(db, 'results', owner.uid), manualResultsPayload(owner))],
  ['update ai_assessments', () => setDoc(doc(db, 'ai_assessments', owner.uid), assessmentPayload(owner))],
  ['delete users', () => deleteDoc(doc(db, 'users', owner.uid))],
];

// Every create the rules permit (NEW_STUDENT owns no documents yet).
const createOps = (db, owner) => [
  ['create users', () => setDoc(doc(db, 'users', owner.uid), registrationPayload(owner))],
  ['create results', () => setDoc(doc(db, 'results', owner.uid), manualResultsPayload(owner))],
  ['create ai_assessments', () => setDoc(doc(db, 'ai_assessments', owner.uid), assessmentPayload(owner))],
];

// =============================================================================
describe('0. Rules inventory: every allow on a private collection is guarded (M3B-1B-P0)', () => {
  // Matching allow statements are combined with OR, so a single unguarded allow
  // on a path would bypass the guard. This lists every allow statement in the
  // rules file with its enclosing match and requires the exact reviewed list.
  const EXPECTED_ALLOWS = [
    ['/users/{uid}', 'get', 'isActiveOwner(uid)'],
    ['/users/{uid}', 'create', 'isActiveOwner(uid) && isValidNewUser()'],
    ['/users/{uid}', 'update', 'isActiveOwner(uid) && isValidUserUpdate()'],
    ['/users/{uid}', 'delete', 'isActiveOwner(uid)'],
    ['/results/{uid}', 'get', 'isActiveOwner(uid)'],
    ['/results/{uid}', 'create,update', 'isActiveOwner(uid) && isValidResults(uid)'],
    ['/ai_assessments/{uid}', 'get', 'isActiveOwner(uid)'],
    ['/ai_assessments/{uid}', 'create,update', 'isActiveOwner(uid) && isValidAssessment(uid)'],
    ['/account_access/{uid}', 'read,write', 'false'],
    ['/programs/{programId}', 'read', 'true'],
    ['/programs/{programId}', 'write', 'false'],
    ['/{document=**}', 'read,write', 'false'],
  ];
  const PRIVATE_PATHS = ['/users/{uid}', '/results/{uid}', '/ai_assessments/{uid}'];

  it('the allow statements are exactly the reviewed list, and every private-collection allow starts with the guard', () => {
    const code = RULES_SOURCE.replace(/\/\/.*$/gm, '');
    const allows = [];
    let enclosingMatch = null;
    for (const line of code.split('\n')) {
      const match = line.match(/^\s*match\s+(\S+)\s*\{/);
      if (match) enclosingMatch = match[1];
      const allow = line.match(/^\s*allow\s+([a-z,\s]+?)\s*:\s*if\s+(.+?);\s*$/);
      if (allow) allows.push([enclosingMatch, allow[1].replace(/\s+/g, ''), allow[2]]);
    }
    assert.equal((code.match(/\ballow\b/g) ?? []).length, allows.length, 'every allow statement is on one line and was parsed');
    assert.deepEqual(allows, EXPECTED_ALLOWS);
    const privateAllows = allows.filter(([path]) => PRIVATE_PATHS.includes(path));
    assert.equal(privateAllows.length, 8);
    for (const [path, methods, condition] of privateAllows) {
      assert.match(condition, /^isActiveOwner\(uid\)( && |$)/, `${path} ${methods}`);
    }
  });
});

// Sections 1-12: the original 44 regression tests, run against the experimental rules.
defineRegressionTests();

// =============================================================================
describe('13. Account-access guard: only an active, well-formed record grants access (M3B-1B-P0)', () => {
  it('control: with an active record every permitted operation succeeds', async () => {
    await expectEach(assertSucceeds, existingDocumentOps(dbAs(STUDENT_B), STUDENT_B), 'active STUDENT_B');
    await expectEach(assertSucceeds, createOps(dbAs(NEW_STUDENT), NEW_STUDENT), 'active NEW_STUDENT');
  });

  for (const state of ['disabled', 'deleting', 'deleted']) {
    it(`${state} account: every read, update and delete of own documents is denied; data unchanged`, async () => {
      await setAccessRecord(STUDENT_B.uid, { state, version: 2 });
      const before = await backendView(STUDENT_B.uid);
      await expectEach(assertFails, existingDocumentOps(dbAs(STUDENT_B), STUDENT_B), state);
      assert.deepEqual(await backendView(STUDENT_B.uid), before);
    });

    it(`${state} account: cannot create own documents`, async () => {
      await setAccessRecord(NEW_STUDENT.uid, { state, version: 2 });
      await expectEach(assertFails, createOps(dbAs(NEW_STUDENT), NEW_STUDENT), state);
      const view = await backendView(NEW_STUDENT.uid);
      assert.deepEqual([view.users, view.results, view.ai_assessments], [null, null, null]);
    });
  }

  it('deletion: documents removed by the backend cannot be recreated or read by a still-valid session', async () => {
    const db = dbAs(STUDENT_B); // session that started before the deletion
    for (const state of ['deleting', 'deleted']) {
      await setAccessRecord(STUDENT_B.uid, { state, version: 3 });
      await removePrivateDocuments(STUDENT_B.uid); // backend clean-up step
      await expectEach(assertFails, createOps(db, STUDENT_B), state);
      await expectEach(assertFails, [
        ['get users', () => getDoc(doc(db, 'users', STUDENT_B.uid))],
        ['get results', () => getDoc(doc(db, 'results', STUDENT_B.uid))],
      ], state);
      const view = await backendView(STUDENT_B.uid);
      assert.deepEqual([view.users, view.results, view.ai_assessments], [null, null, null], state);
    }
  });

  it('missing record: every operation is denied (fail closed)', async () => {
    await removeAccessRecord(STUDENT_B.uid);
    await removeAccessRecord(NEW_STUDENT.uid);
    await expectEach(assertFails, existingDocumentOps(dbAs(STUDENT_B), STUDENT_B), 'missing record');
    await expectEach(assertFails, createOps(dbAs(NEW_STUDENT), NEW_STUDENT), 'missing record');
  });

  describe('malformed record: every operation is denied, even for a session newer than any threshold', () => {
    const MALFORMED_RECORDS = [
      ['empty document', {}],
      ['state missing', { version: 1 }],
      ['version missing', { state: 'active' }],
      ['state is not a string', { state: true, version: 1 }],
      ['state is an unknown value', { state: 'enabled', version: 1 }],
      ['state has the wrong case', { state: 'Active', version: 1 }],
      ['state has trailing whitespace', { state: 'active ', version: 1 }],
      ['version is a string', { state: 'active', version: '1' }],
      ['version is a float', { state: 'active', version: 1.5 }],
      ['version is negative', { state: 'active', version: -1 }],
      ['sessionsValidAfter is null', { state: 'active', version: 1, sessionsValidAfter: null }],
      ['sessionsValidAfter is a string', { state: 'active', version: 1, sessionsValidAfter: '2027-01-15T08:00:00Z' }],
      ['sessionsValidAfter is a number (milliseconds)', { state: 'active', version: 1, sessionsValidAfter: S * 1000 }],
      ['sessionsValidAfter is a map', { state: 'active', version: 1, sessionsValidAfter: { seconds: S, nanoseconds: 0 } }],
      ['misspelt threshold field (sessionValidAfter)', { state: 'active', version: 1, sessionValidAfter: new Timestamp(S, 0) }],
      ['unexpected extra field', { state: 'active', version: 1, admin: true }],
    ];
    const freshSession = { auth_time: S + 3600 };

    for (const [label, record] of MALFORMED_RECORDS) {
      it(label, async () => {
        await setAccessRecord(STUDENT_B.uid, record);
        await setAccessRecord(NEW_STUDENT.uid, record);
        await expectEach(assertFails, existingDocumentOps(dbAs(STUDENT_B, freshSession), STUDENT_B), label);
        await expectEach(assertFails, createOps(dbAs(NEW_STUDENT, freshSession), NEW_STUDENT), label);
      });
    }
  });
});

// =============================================================================
describe('14. Re-enabled accounts: the session must start after sessionsValidAfter (M3B-1B-P0)', () => {
  // auth_time is in whole seconds. The rule accepts only auth_time > ceil(threshold).
  const reenabled = (threshold) => ({ state: 'active', version: 4, sessionsValidAfter: threshold });
  const session = (authTime) => ({ auth_time: authTime });
  const readAndWrite = (db) => [
    ['get users', () => getDoc(doc(db, 'users', STUDENT_B.uid))],
    ['update results', () => setDoc(doc(db, 'results', STUDENT_B.uid), manualResultsPayload(STUDENT_B))],
  ];

  // [threshold label, threshold, auth_time, allowed, reason]
  const BOUNDARY_CASES = [
    ['S+0.25s', new Timestamp(S, 250_000_000), S - 3600, false, 'old session'],
    ['S+0.25s', new Timestamp(S, 250_000_000), S - 1, false, 'one second before'],
    ['S+0.25s', new Timestamp(S, 250_000_000), S, false, 'same second; the sign-in may precede the threshold'],
    ['S+0.25s', new Timestamp(S, 250_000_000), S + 1, false, 'ceil(threshold); rejected as a safety margin'],
    ['S+0.25s', new Timestamp(S, 250_000_000), S + 2, true, 'first accepted second'],
    ['S+0.25s', new Timestamp(S, 250_000_000), S + 3600, true, 'new session'],
    ['S exactly', new Timestamp(S, 0), S - 1, false, 'one second before'],
    ['S exactly', new Timestamp(S, 0), S, false, 'same second; a rounded auth_time may be up to 0.5 s early'],
    ['S exactly', new Timestamp(S, 0), S + 1, true, 'first accepted second'],
    ['S+1us', new Timestamp(S, 1_000), S, false, 'a floor(toMillis / 1000) comparison would accept this'],
    ['S+1us', new Timestamp(S, 1_000), S + 1, false, 'ceil(threshold)'],
    ['S+1us', new Timestamp(S, 1_000), S + 2, true, 'first accepted second'],
    ['S+0.999999s', new Timestamp(S, 999_999_000), S + 1, false, 'ceil(threshold)'],
    ['S+0.999999s', new Timestamp(S, 999_999_000), S + 2, true, 'first accepted second'],
  ];

  for (const [thresholdLabel, threshold, authTime, allowed, reason] of BOUNDARY_CASES) {
    const offset = authTime - S;
    const authLabel = `S${offset < 0 ? '' : '+'}${offset}`;
    it(`threshold ${thresholdLabel}, auth_time ${authLabel}: ${allowed ? 'allowed' : 'denied'} (${reason})`, async () => {
      await setAccessRecord(STUDENT_B.uid, reenabled(threshold));
      const expectation = allowed ? assertSucceeds : assertFails;
      await expectEach(expectation, readAndWrite(dbAs(STUDENT_B, session(authTime))), `auth_time ${authLabel}`);
    });
  }

  it('an old session is denied every operation; a new session is allowed every operation', async () => {
    const threshold = new Timestamp(S, 250_000_000);
    await setAccessRecord(STUDENT_B.uid, reenabled(threshold));
    await setAccessRecord(NEW_STUDENT.uid, reenabled(threshold));
    await expectEach(assertFails, existingDocumentOps(dbAs(STUDENT_B, session(S - 60)), STUDENT_B), 'old session');
    await expectEach(assertFails, createOps(dbAs(NEW_STUDENT, session(S - 60)), NEW_STUDENT), 'old session');
    await expectEach(assertSucceeds, existingDocumentOps(dbAs(STUDENT_B, session(S + 60)), STUDENT_B), 'new session');
    await expectEach(assertSucceeds, createOps(dbAs(NEW_STUDENT, session(S + 60)), NEW_STUDENT), 'new session');
  });

  const INVALID_AUTH_TIMES = [
    ['missing', undefined],
    ['null', null],
    ['a numeric string', String(S + 3600)],
    ['a float', S + 3600.5],
    ['a boolean', true],
  ];

  it('a missing or non-integer auth_time is denied when a threshold exists', async () => {
    await setAccessRecord(STUDENT_B.uid, reenabled(new Timestamp(S, 0)));
    for (const [label, authTime] of INVALID_AUTH_TIMES) {
      await expectEach(assertFails, readAndWrite(dbAs(STUDENT_B, { auth_time: authTime })), `auth_time ${label}`);
    }
  });

  it('control: without a threshold auth_time is not consulted (only re-enabled accounts depend on it)', async () => {
    for (const [label, authTime] of INVALID_AUTH_TIMES) {
      await expectEach(assertSucceeds, readAndWrite(dbAs(STUDENT_B, { auth_time: authTime })), `auth_time ${label}`);
    }
  });

  it('a threshold never overrides a non-active state', async () => {
    for (const state of ['disabled', 'deleting', 'deleted']) {
      await setAccessRecord(STUDENT_B.uid, { state, version: 5, sessionsValidAfter: new Timestamp(S, 0) });
      await expectEach(assertFails, existingDocumentOps(dbAs(STUDENT_B, session(S + 3600)), STUDENT_B), state);
    }
  });
});

// =============================================================================
describe('15. account_access is backend-only: no browser reads or writes (M3B-1B-P0)', () => {
  const recordOps = (db, uid, { exists = true } = {}) => [
    ['get', () => getDoc(doc(db, 'account_access', uid))],
    ['list', () => getDocs(collection(db, 'account_access'))],
    ['query by document ID', () => getDocs(query(collection(db, 'account_access'), where(documentId(), '==', uid)))],
    ['collection-group query', () => getDocs(collectionGroup(db, 'account_access'))],
    ['create or overwrite as active', () => setDoc(doc(db, 'account_access', uid), { state: 'active', version: 99 })],
    ...(exists
      ? [
        ['update state to active', () => updateDoc(doc(db, 'account_access', uid), { state: 'active' })],
        ['remove the session threshold', () => updateDoc(doc(db, 'account_access', uid), { sessionsValidAfter: deleteField() })],
        ['move the session threshold back', () => updateDoc(doc(db, 'account_access', uid), { sessionsValidAfter: new Timestamp(0, 0) })],
        ['delete', () => deleteDoc(doc(db, 'account_access', uid))],
      ]
      : []),
    ['write a sub-collection document', () => setDoc(doc(db, 'account_access', uid, 'notes', 'x'), { any: 'value' })],
  ];

  const CALLERS = [
    ['active student, own record', () => dbAs(STUDENT_A), STUDENT_A.uid],
    ['active student, another student\'s record', () => dbAs(STUDENT_A), STUDENT_B.uid],
    ['Admin (admin: true), own record', adminDb, ADMIN.uid],
    ['Admin (admin: true), a student\'s record', adminDb, STUDENT_B.uid],
    ['admin: "true" string claim, a student\'s record', stringClaimAdminDb, STUDENT_B.uid],
    ['signed-out visitor', anonDb, STUDENT_B.uid],
  ];

  for (const [label, makeDb, uid] of CALLERS) {
    it(`${label}: every read and write is denied; record unchanged`, async () => {
      await expectEach(assertFails, recordOps(makeDb(), uid), label);
      assert.deepEqual((await backendView(uid)).account_access, ACTIVE_RECORD);
    });
  }

  it('a disabled student cannot re-activate their own record', async () => {
    const record = { state: 'disabled', version: 2 };
    await setAccessRecord(STUDENT_B.uid, record);
    await expectEach(assertFails, recordOps(dbAs(STUDENT_B), STUDENT_B.uid), 'disabled student');
    assert.deepEqual((await backendView(STUDENT_B.uid)).account_access, record);
    await assertFails(getDoc(doc(dbAs(STUDENT_B), 'users', STUDENT_B.uid)));
  });

  it('a student without a record cannot create one for themselves', async () => {
    await removeAccessRecord(NEW_STUDENT.uid);
    await expectEach(assertFails, recordOps(dbAs(NEW_STUDENT), NEW_STUDENT.uid, { exists: false }), 'no record');
    assert.equal((await backendView(NEW_STUDENT.uid)).account_access, null);
  });

  it('a re-enabled student with an old session cannot remove or move their session threshold', async () => {
    const record = { state: 'active', version: 4, sessionsValidAfter: new Timestamp(S, 0) };
    await setAccessRecord(STUDENT_B.uid, record);
    await expectEach(assertFails, recordOps(dbAs(STUDENT_B, { auth_time: S - 60 }), STUDENT_B.uid), 'old session');
    assert.deepEqual((await backendView(STUDENT_B.uid)).account_access, record);
  });
});

// =============================================================================
describe('16. The guard never widens access: ownership, Admin claim and queries (M3B-1B-P0)', () => {
  it('an active student cannot read, write or create another student\'s documents', async () => {
    const db = dbAs(STUDENT_A);
    await expectEach(assertFails, existingDocumentOps(db, STUDENT_B), 'STUDENT_A on STUDENT_B');
    await expectEach(assertFails, createOps(db, NEW_STUDENT), 'STUDENT_A on NEW_STUDENT');
  });

  it('an Admin with an active record still cannot access students\' documents from the browser', async () => {
    for (const [label, makeDb] of [['admin: true', adminDb], ['admin: "true"', stringClaimAdminDb]]) {
      await expectEach(assertFails, existingDocumentOps(makeDb(), STUDENT_B), label);
      await expectEach(assertFails, createOps(makeDb(), NEW_STUDENT), label);
    }
  });

  it('collection and collection-group queries stay denied for an active owner, even filtered to self', async () => {
    const db = dbAs(STUDENT_B);
    await expectEach(assertFails, [
      ['list users', () => getDocs(collection(db, 'users'))],
      ['query users by own document ID', () => getDocs(query(collection(db, 'users'), where(documentId(), '==', STUDENT_B.uid)))],
      ['query results by own userId', () => getDocs(query(collection(db, 'results'), where('userId', '==', STUDENT_B.uid)))],
      ['query ai_assessments by own userId', () => getDocs(query(collection(db, 'ai_assessments'), where('userId', '==', STUDENT_B.uid)))],
      ['collection group users', () => getDocs(collectionGroup(db, 'users'))],
      ['collection group results', () => getDocs(collectionGroup(db, 'results'))],
      ['collection group ai_assessments', () => getDocs(collectionGroup(db, 'ai_assessments'))],
    ], 'active STUDENT_B');
  });
});
