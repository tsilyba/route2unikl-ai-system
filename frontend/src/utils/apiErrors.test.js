// frontend/src/utils/apiErrors.test.js
//
// How authFetch describes 401 and 403 answers (L1, M3B-3). Synthetic data only: no browser, Firebase or
// network. Run from the frontend folder:
//   node --test src/utils/apiErrors.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { AUTH_SERVICE_UNAVAILABLE, authErrorFields } from './apiErrors.js';

describe('authErrorFields', () => {
  test('string details (token problems) keep their text and have no code, as before', () => {
    assert.deepEqual(authErrorFields(401, 'Session revoked. Please sign in again.'),
      { message: 'Session revoked. Please sign in again.', code: null });
    assert.deepEqual(authErrorFields(403, 'Admin access required.'), { message: 'Admin access required.', code: null });
  });

  test('missing or unreadable details fall back to the previous messages', () => {
    for (const detail of [null, undefined, '', '   ', 42, []]) {
      assert.deepEqual(authErrorFields(401, detail), { message: 'Authentication required.', code: null }, String(detail));
      assert.deepEqual(authErrorFields(403, detail), { message: 'Access denied.', code: null }, String(detail));
    }
  });

  test('object details keep the machine-readable code and the fixed server message (L1)', () => {
    assert.deepEqual(
      authErrorFields(403, { code: 'ADMIN_TARGET_FORBIDDEN', message: 'Administrator accounts cannot be disabled, enabled or deleted here.' }),
      { message: 'Administrator accounts cannot be disabled, enabled or deleted here.', code: 'ADMIN_TARGET_FORBIDDEN' },
    );
    assert.deepEqual(authErrorFields(403, { code: 'ACCOUNT_DELETED', message: 'This account has been deleted.' }),
      { message: 'This account has been deleted.', code: 'ACCOUNT_DELETED' });
    assert.deepEqual(authErrorFields(403, { code: 'SELF_ACTION_FORBIDDEN' }), { message: 'Access denied.', code: 'SELF_ACTION_FORBIDDEN' });
  });

  test('codes must look like codes; messages are bounded', () => {
    for (const code of ['lowercase', 'HAS SPACE', '', 7, null, 'A'.repeat(65), '<script>']) {
      assert.equal(authErrorFields(403, { code, message: 'x' }).code, null, String(code));
    }
    assert.equal(authErrorFields(403, { code: 'X', message: 'y'.repeat(1000) }).message.length, 300);
  });

  test('AUTH_SERVICE_UNAVAILABLE never relabels a 401 or 403 as a temporary outage', () => {
    for (const status of [401, 403]) {
      assert.equal(authErrorFields(status, { code: AUTH_SERVICE_UNAVAILABLE, message: 'x' }).code, null);
    }
  });
});
