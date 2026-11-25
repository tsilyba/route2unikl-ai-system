// frontend/src/utils/accountAccess.test.js
//
// The login-time account-access check (local emulator mode). The profile read is a fake:
// no browser, Firebase or network. Run from the frontend folder:
//   node --test src/utils/accountAccess.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { ACCOUNT_ACCESS_DENIED_MESSAGE, isAccountAccessDenied, probeAccountAccess } from './accountAccess.js';

const firestoreError = (code) => Object.assign(new Error(`Firestore error ${code}`), { code });

describe('isAccountAccessDenied', () => {
  test('only a Firestore permission-denied error', () => {
    assert.equal(isAccountAccessDenied(firestoreError('permission-denied')), true);
    for (const code of ['unavailable', 'not-found', 'unauthenticated', 'auth/user-disabled', undefined]) {
      assert.equal(isAccountAccessDenied(firestoreError(code)), false, String(code));
    }
    assert.equal(isAccountAccessDenied(null), false);
    assert.equal(isAccountAccessDenied(undefined), false);
  });
});

describe('probeAccountAccess', () => {
  test('a readable profile (or a missing one the student may read) is allowed', async () => {
    assert.equal(await probeAccountAccess(async () => ({ exists: () => true })), 'allowed');
    assert.equal(await probeAccountAccess(async () => ({ exists: () => false })), 'allowed');
  });

  test('a refused read is denied', async () => {
    assert.equal(await probeAccountAccess(async () => { throw firestoreError('permission-denied'); }), 'denied');
  });

  test('any other failure is unknown and never rejects', async () => {
    for (const code of ['unavailable', 'deadline-exceeded', undefined]) {
      assert.equal(await probeAccountAccess(async () => { throw firestoreError(code); }), 'unknown', String(code));
    }
    assert.equal(await probeAccountAccess(() => { throw new Error('synchronous failure'); }), 'unknown');
  });

  test('the probe reads exactly once', async () => {
    let reads = 0;
    await probeAccountAccess(async () => { reads += 1; });
    assert.equal(reads, 1);
  });
});

describe('ACCOUNT_ACCESS_DENIED_MESSAGE', () => {
  test('is clear and reveals no account state or details', () => {
    assert.match(ACCOUNT_ACCESS_DENIED_MESSAGE, /administrator/);
    for (const word of ['disabled', 'deleted', 'deleting', 'record', 'uid', 'permission-denied', 'account_access']) {
      assert.ok(!ACCOUNT_ACCESS_DENIED_MESSAGE.toLowerCase().includes(word), word);
    }
  });
});
