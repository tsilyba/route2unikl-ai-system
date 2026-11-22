// frontend/src/utils/adminVerification.js
//
// Server-side confirmation of Admin access via the existing FastAPI endpoint
// GET /api/admin/verify (backend/routes/auth_check.py, protected by require_admin).
//
// Plain JavaScript with no Firebase import, so it can be tested with Node's
// built-in test runner:
//   node --test src/utils/adminVerification.test.js
//
// The caller supplies the fetcher (in the app: authFetch from utils/apiClient.js,
// which attaches the Firebase ID token and throws ApiAuthError on 401, 403 and on
// 503 with code AUTH_SERVICE_UNAVAILABLE). Nothing here logs tokens or user data.

export const ADMIN_VERIFY_PATH = '/api/admin/verify';

// Must match AUTH_SERVICE_UNAVAILABLE in backend/core/auth.py and utils/apiClient.js.
const AUTH_SERVICE_UNAVAILABLE = 'AUTH_SERVICE_UNAVAILABLE';

export const VERIFY_STATUS = Object.freeze({
  CHECKING: 'checking',
  VERIFIED: 'verified',
  FORBIDDEN: 'forbidden',
  SESSION_EXPIRED: 'session-expired',
  AUTH_UNAVAILABLE: 'auth-unavailable',
  SERVER_UNREACHABLE: 'server-unreachable',
  ERROR: 'error',
});

// Classifies an error thrown while calling the endpoint.
export const classifyVerifyError = (error) => {
  if (error?.name === 'ApiAuthError') {
    if (error.status === 401) return VERIFY_STATUS.SESSION_EXPIRED;
    if (error.status === 403) return VERIFY_STATUS.FORBIDDEN;
    if (error.status === 503 && error.code === AUTH_SERVICE_UNAVAILABLE) return VERIFY_STATUS.AUTH_UNAVAILABLE;
    return VERIFY_STATUS.ERROR;
  }
  // fetch() rejects with a TypeError when the server cannot be reached.
  if (error instanceof TypeError) return VERIFY_STATUS.SERVER_UNREACHABLE;
  return VERIFY_STATUS.ERROR;
};

// Classifies an HTTP response. Admin access is granted ONLY for HTTP 200 with
// `is_admin === true` (strict boolean) for the expected user.
export const classifyVerifyResponse = (status, body, expectedUid = null) => {
  if (status === 200) {
    if (!body || typeof body !== 'object' || body.is_admin !== true) return VERIFY_STATUS.FORBIDDEN;
    // A response for a different account (e.g. the user switched accounts
    // mid-request) is never accepted; the caller can retry.
    if (expectedUid && body.uid !== expectedUid) return VERIFY_STATUS.ERROR;
    return VERIFY_STATUS.VERIFIED;
  }
  if (status === 401) return VERIFY_STATUS.SESSION_EXPIRED;
  if (status === 403) return VERIFY_STATUS.FORBIDDEN;
  if (status === 503 && body?.detail?.code === AUTH_SERVICE_UNAVAILABLE) return VERIFY_STATUS.AUTH_UNAVAILABLE;
  return VERIFY_STATUS.ERROR;
};

// Calls the endpoint and returns { status } or, on success, { status, verifiedAt }.
// Never throws.
export const verifyAdminAccess = async (fetcher, { expectedUid = null } = {}) => {
  let response;
  try {
    response = await fetcher(ADMIN_VERIFY_PATH);
  } catch (error) {
    return { status: classifyVerifyError(error) };
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // Missing or non-JSON body: classified as "no body" below.
  }

  const status = classifyVerifyResponse(response?.status, body, expectedUid);
  return status === VERIFY_STATUS.VERIFIED ? { status, verifiedAt: new Date() } : { status };
};
