// frontend/src/utils/adminVerification.test.js
//
// Tests for the classification of GET /api/admin/verify results. The fetcher is
// a fake: no network, no Firebase, no backend.
// Run from the frontend folder:
//   node --test src/utils/adminVerification.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ADMIN_VERIFY_PATH,
  VERIFY_STATUS,
  classifyVerifyError,
  classifyVerifyResponse,
  verifyAdminAccess,
} from './adminVerification.js';

const ADMIN_UID = 'admin-uid-123';

// Minimal stand-ins for fetch Responses and the errors authFetch throws.
const jsonResponse = (status, body) => ({ status, json: async () => body });
const brokenJsonResponse = (status) => ({
  status,
  json: async () => { throw new SyntaxError('Unexpected token < in JSON'); },
});
const apiAuthError = (status, code = null) => Object.assign(new Error('auth'), { name: 'ApiAuthError', status, code });

const verifyWith = (responseOrError, options = { expectedUid: ADMIN_UID }) =>
  verifyAdminAccess(async () => {
    if (responseOrError instanceof Error) throw responseOrError;
    return responseOrError;
  }, options);

describe('successful verification', () => {
  test('HTTP 200 with is_admin === true for the expected user is verified', async () => {
    const before = Date.now();
    const result = await verifyWith(jsonResponse(200, { status: 'ok', uid: ADMIN_UID, is_admin: true }));
    assert.equal(result.status, VERIFY_STATUS.VERIFIED);
    assert.ok(result.verifiedAt instanceof Date);
    assert.ok(result.verifiedAt.getTime() >= before);
    assert.deepEqual(Object.keys(result).sort(), ['status', 'verifiedAt']);
  });

  test('calls the existing /api/admin/verify endpoint', async () => {
    const calls = [];
    await verifyAdminAccess(async (path) => { calls.push(path); return jsonResponse(200, { uid: ADMIN_UID, is_admin: true }); },
      { expectedUid: ADMIN_UID });
    assert.deepEqual(calls, ['/api/admin/verify']);
    assert.equal(ADMIN_VERIFY_PATH, '/api/admin/verify');
  });
});

describe('admin access is denied unless the server explicitly confirms it', () => {
  test('HTTP 200 without an explicit boolean is_admin: true is forbidden', async () => {
    for (const body of [{ status: 'ok', uid: ADMIN_UID }, { uid: ADMIN_UID, is_admin: 'true' },
      { uid: ADMIN_UID, is_admin: 1 }, { uid: ADMIN_UID, is_admin: false }, {}, null, 'ok', []]) {
      const result = await verifyWith(jsonResponse(200, body));
      assert.equal(result.status, VERIFY_STATUS.FORBIDDEN, JSON.stringify(body));
      assert.equal(result.verifiedAt, undefined);
    }
  });

  test('a malformed (non-JSON) HTTP 200 body is forbidden', async () => {
    const result = await verifyWith(brokenJsonResponse(200));
    assert.equal(result.status, VERIFY_STATUS.FORBIDDEN);
  });

  test('a response for a different account is never accepted', async () => {
    const result = await verifyWith(jsonResponse(200, { uid: 'someone-else', is_admin: true }));
    assert.equal(result.status, VERIFY_STATUS.ERROR);
  });

  test('HTTP 403 (thrown by authFetch or returned) is forbidden', async () => {
    assert.equal((await verifyWith(apiAuthError(403))).status, VERIFY_STATUS.FORBIDDEN);
    assert.equal((await verifyWith(jsonResponse(403, { detail: 'Administrator privileges required.' }))).status,
      VERIFY_STATUS.FORBIDDEN);
  });
});

describe('session and service failures', () => {
  test('HTTP 401 means an invalid or expired session', async () => {
    assert.equal((await verifyWith(apiAuthError(401))).status, VERIFY_STATUS.SESSION_EXPIRED);
    assert.equal((await verifyWith(jsonResponse(401, { detail: 'Session expired.' }))).status,
      VERIFY_STATUS.SESSION_EXPIRED);
  });

  test('503 AUTH_SERVICE_UNAVAILABLE means the sign-in service is unavailable', async () => {
    assert.equal((await verifyWith(apiAuthError(503, 'AUTH_SERVICE_UNAVAILABLE'))).status,
      VERIFY_STATUS.AUTH_UNAVAILABLE);
    assert.equal((await verifyWith(jsonResponse(503, { detail: { code: 'AUTH_SERVICE_UNAVAILABLE', message: 'x' } }))).status,
      VERIFY_STATUS.AUTH_UNAVAILABLE);
  });

  test('a network failure (fetch TypeError) means the server is unreachable', async () => {
    const result = await verifyWith(new TypeError('Failed to fetch'));
    assert.equal(result.status, VERIFY_STATUS.SERVER_UNREACHABLE);
  });

  test('other failures are a safe generic error', async () => {
    const cases = [
      new Error('unexpected'),
      apiAuthError(503),                       // 503 without the auth code
      apiAuthError(500),
      jsonResponse(500, { detail: 'Internal Server Error' }),
      jsonResponse(503, { detail: { code: 'OTHER' } }),
      jsonResponse(404, { detail: 'Not Found' }),
      brokenJsonResponse(502),
    ];
    for (const item of cases) {
      const result = await verifyWith(item);
      assert.equal(result.status, VERIFY_STATUS.ERROR);
      assert.equal(result.verifiedAt, undefined);
    }
  });

  test('verification never throws, even for an unusable fetcher result', async () => {
    assert.equal((await verifyAdminAccess(async () => undefined)).status, VERIFY_STATUS.ERROR);
    assert.equal((await verifyAdminAccess(async () => null)).status, VERIFY_STATUS.ERROR);
  });
});

describe('classification helpers', () => {
  test('classifyVerifyError covers ApiAuthError, network and unknown errors', () => {
    assert.equal(classifyVerifyError(apiAuthError(401)), VERIFY_STATUS.SESSION_EXPIRED);
    assert.equal(classifyVerifyError(apiAuthError(403)), VERIFY_STATUS.FORBIDDEN);
    assert.equal(classifyVerifyError(apiAuthError(503, 'AUTH_SERVICE_UNAVAILABLE')), VERIFY_STATUS.AUTH_UNAVAILABLE);
    assert.equal(classifyVerifyError(new TypeError('Failed to fetch')), VERIFY_STATUS.SERVER_UNREACHABLE);
    assert.equal(classifyVerifyError(new Error('x')), VERIFY_STATUS.ERROR);
    assert.equal(classifyVerifyError(undefined), VERIFY_STATUS.ERROR);
  });

  test('classifyVerifyResponse grants access only for 200 with is_admin === true', () => {
    assert.equal(classifyVerifyResponse(200, { uid: ADMIN_UID, is_admin: true }, ADMIN_UID), VERIFY_STATUS.VERIFIED);
    assert.equal(classifyVerifyResponse(200, { uid: ADMIN_UID, is_admin: true }), VERIFY_STATUS.VERIFIED);
    assert.equal(classifyVerifyResponse(201, { uid: ADMIN_UID, is_admin: true }, ADMIN_UID), VERIFY_STATUS.ERROR);
    assert.equal(classifyVerifyResponse(undefined, null), VERIFY_STATUS.ERROR);
  });
});
