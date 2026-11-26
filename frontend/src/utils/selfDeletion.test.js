// frontend/src/utils/selfDeletion.test.js
//
// M3C student self-service deletion helper. Synthetic data only: no browser, Firebase or network.
//   node --test src/utils/selfDeletion.test.js
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  SELF_DELETE_PATH,
  SELF_DELETE_TEXT,
  describeReauthError,
  describeSelfDeletionError,
  requestOwnAccountDeletion,
  selfDeletionOutcome,
} from './selfDeletion.js';

const PASSWORD = 'Sentinel-Password-123';
const EMAIL = 'sentinel.student@example.test';

const response = (status, body) => ({
  status,
  json: async () => {
    if (body instanceof Error) throw body;
    return body;
  },
});

const apiAuthError = (status, code = null) =>
  Object.assign(new Error('auth'), { name: 'ApiAuthError', status, code });

describe('requestOwnAccountDeletion', () => {
  test('posts only the confirmation of the own uid to the self-deletion path', async () => {
    const calls = [];
    const outcome = await requestOwnAccountDeletion({
      uid: 'uid-1',
      authFetch: async (path, options) => {
        calls.push([path, options]);
        return response(200, { outcome: 'completed', operation: 'delete', operation_id: 'op' });
      },
    });
    assert.deepEqual(calls, [[SELF_DELETE_PATH, { method: 'POST', body: JSON.stringify({ confirm_uid: 'uid-1' }) }]]);
    assert.equal(SELF_DELETE_PATH, '/api/account/delete');
    assert.deepEqual(outcome, { ok: true, kind: 'deleted', tone: 'success', title: 'Account deleted',
      message: 'Your account and your data have been permanently deleted.' });
  });

  test('success only when the server reports the deletion completed', async () => {
    for (const body of [{}, { outcome: 'started' }, null, new SyntaxError('bad json')]) {
      const outcome = await requestOwnAccountDeletion({ uid: 'uid-1', authFetch: async () => response(200, body) });
      assert.equal(outcome.ok, false, JSON.stringify(body));
      assert.equal(outcome.kind, 'error');
    }
  });

  test('never calls the server without a uid, and never rejects', async () => {
    let called = false;
    const outcome = await requestOwnAccountDeletion({ uid: '', authFetch: async () => { called = true; } });
    assert.equal(called, false);
    assert.equal(outcome.ok, false);
    const network = await requestOwnAccountDeletion({ uid: 'u', authFetch: async () => { throw new TypeError('fetch failed'); } });
    assert.equal(network.kind, 'network');
    assert.match(network.message, /may not have reached the server/);
    assert.doesNotMatch(network.message, /Nothing was changed/, 'the outcome is unknown, so never claimed');
  });

  test('server refusals map to fixed texts, by code', async () => {
    const cases = [
      [403, 'RECENT_SIGN_IN_REQUIRED', 'reauth'],
      [401, 'SESSION_TOO_OLD', 'session'],
      [403, 'ACCOUNT_ACCESS_DENIED', 'denied'],
      [403, 'ADMIN_TARGET_FORBIDDEN', 'denied'],
      [403, 'ACCOUNT_DELETED', 'denied'],
      [409, 'DELETE_NOT_ALLOWED', 'denied'],
      [409, 'INCOMPLETE_OPERATION_PENDING', 'denied'],
      [409, 'OPERATION_IN_PROGRESS', 'retry-later'],
      [422, 'DELETE_CONFIRMATION_MISMATCH', 'error'],
      [422, 'INVALID_REQUEST', 'error'],
      [503, 'ACCOUNT_ACTION_UNAVAILABLE', 'retry-later'],
      [503, 'ACCOUNT_STATUS_UNAVAILABLE', 'retry-later'],
    ];
    for (const [status, code, kind] of cases) {
      const outcome = await requestOwnAccountDeletion({
        uid: 'u', authFetch: async () => response(status, { detail: { code, message: `server text ${EMAIL}` } }),
      });
      assert.equal(outcome.ok, false, code);
      assert.equal(outcome.kind, kind, code);
      assert.doesNotMatch(outcome.message, /server text/, 'server text is never shown');
    }
  });

  test('authFetch errors (401/403/503) keep their code', async () => {
    const reauth = await requestOwnAccountDeletion({ uid: 'u', authFetch: async () => { throw apiAuthError(403, 'RECENT_SIGN_IN_REQUIRED'); } });
    assert.equal(reauth.kind, 'reauth');
    const tooOld = await requestOwnAccountDeletion({ uid: 'u', authFetch: async () => { throw apiAuthError(401, 'SESSION_TOO_OLD'); } });
    assert.equal(tooOld.kind, 'session');
    assert.equal(describeSelfDeletionError(apiAuthError(401)).kind, 'session');
    assert.equal(describeSelfDeletionError(apiAuthError(503, 'AUTH_SERVICE_UNAVAILABLE')).kind, 'retry-later');
    assert.equal(describeSelfDeletionError(new Error('other')).kind, 'error');
  });

  test('an incomplete deletion is reported as recorded and never as "nothing was changed"', async () => {
    const outcome = await requestOwnAccountDeletion({
      uid: 'u',
      authFetch: async () => response(503, { detail: { code: 'OPERATION_INCOMPLETE', operation: 'delete',
        operation_id: 'op-1', failed_step: 'delete_auth', reason: 'AUTH_UNAVAILABLE' } }),
    });
    assert.equal(outcome.kind, 'incomplete');
    assert.equal(outcome.tone, 'warning');
    assert.match(outcome.message, /recorded so that it can be completed/);
    assert.match(outcome.message, /administrator can complete it/);
    assert.doesNotMatch(outcome.message, /Nothing was changed/);
  });

  test('a server without the route (production) explains that deletion is not available', () => {
    const outcome = selfDeletionOutcome(404, { detail: 'Not Found' });
    assert.equal(outcome.kind, 'unavailable');
    assert.equal(outcome.message, SELF_DELETE_TEXT.productionUnavailable);
    assert.equal(selfDeletionOutcome(500, null).kind, 'error');
  });
});

describe('describeReauthError', () => {
  test('a wrong password and other sign-in failures change nothing and never echo input', () => {
    for (const code of ['auth/wrong-password', 'auth/invalid-credential', 'auth/invalid-login-credentials']) {
      const outcome = describeReauthError({ code, message: `${PASSWORD} ${EMAIL}` });
      assert.equal(outcome.kind, 'password', code);
      assert.match(outcome.message, /Nothing was changed/);
    }
    assert.equal(describeReauthError({ code: 'auth/too-many-requests' }).kind, 'retry-later');
    assert.equal(describeReauthError({ code: 'auth/network-request-failed' }).kind, 'network');
    assert.equal(describeReauthError({ code: 'auth/user-disabled' }).kind, 'session');
    assert.equal(describeReauthError({ code: 'auth/missing-password' }).kind, 'password');
    assert.equal(describeReauthError(undefined).kind, 'error');
    for (const outcome of [describeReauthError({ code: 'auth/x', message: PASSWORD })]) {
      assert.doesNotMatch(JSON.stringify(outcome), new RegExp(PASSWORD));
    }
  });
});

describe('texts', () => {
  test('the warning states what is deleted and that it is permanent', () => {
    assert.match(SELF_DELETE_TEXT.warning, /sign-in account and all your Route2UniKL data \(profile, SPM results and AI assessment\)/);
    assert.match(SELF_DELETE_TEXT.warning, /cannot be undone/);
    assert.match(SELF_DELETE_TEXT.productionUnavailable, /contact the Route2UniKL administrator/);
    assert.match(SELF_DELETE_TEXT.signOutFailed, /has been deleted/);
  });
});
