// frontend/src/utils/apiClient.js
//
// Authenticated requests to the Route2UniKL FastAPI backend.
// Every request carries the signed-in user's Firebase ID token as
// `Authorization: Bearer <token>`; the backend verifies it on each call.
import { auth } from '../firebase';
import { AUTH_SERVICE_UNAVAILABLE, authErrorFields } from './apiErrors.js';

export const API_BASE_URL = 'http://localhost:8000';

// Machine-readable code sent by the backend (core/auth.py) with HTTP 503 when
// token verification cannot be completed. Also used when the browser cannot
// obtain a token at all. Must match AUTH_SERVICE_UNAVAILABLE in the backend.
export { AUTH_SERVICE_UNAVAILABLE };

// Firebase client error codes meaning the stored session is no longer valid.
const SESSION_ENDED_CODES = new Set([
  'auth/user-token-expired',
  'auth/user-disabled',
  'auth/user-not-found',
  'auth/invalid-user-token',
]);

/**
 * Raised for authentication/authorization failures:
 * - status 401 / 403: the request was rejected (sign-in invalid or not allowed);
 *   `code` is the backend's machine-readable code when it sent one (for example
 *   ADMIN_TARGET_FORBIDDEN or ACCOUNT_DELETED), otherwise null (see apiErrors.js);
 * - status 503 with code AUTH_SERVICE_UNAVAILABLE: sign-in could not be verified
 *   right now (temporary outage), so the request was NOT authenticated.
 * Callers must surface this to the user and must NOT replace it with
 * fallback/mock data — fallbacks are only for an unreachable backend.
 */
export class ApiAuthError extends Error {
  constructor(status, message, code = null) {
    super(message);
    this.name = 'ApiAuthError';
    this.status = status;
    this.code = code;
  }
}

// Returns the `detail` field of a JSON error body, or null if unreadable.
async function readErrorDetail(response) {
  try {
    return (await response.json())?.detail ?? null;
  } catch {
    return null;
  }
}

/**
 * fetch() wrapper that attaches the Firebase ID token.
 * - Throws ApiAuthError on 401/403, on 503 carrying AUTH_SERVICE_UNAVAILABLE,
 *   and whenever no valid token can be obtained.
 * - Returns the Response for every other status (including other 503s), like fetch().
 * - Network failures reaching the backend propagate as normal fetch errors.
 */
export async function authFetch(path, { headers, ...options } = {}) {
  const user = auth.currentUser;
  if (!user) {
    throw new ApiAuthError(401, 'You are not signed in.');
  }

  let token;
  try {
    // Returns the cached token, refreshing it automatically when near expiry.
    token = await user.getIdToken();
  } catch (err) {
    if (SESSION_ENDED_CODES.has(err?.code)) {
      throw new ApiAuthError(401, 'Your session has expired. Please sign in again.');
    }
    // Any other failure (e.g. Firebase unreachable): we cannot authenticate right now.
    throw new ApiAuthError(
      503,
      'The sign-in service could not be reached. Please check your connection and try again.',
      AUTH_SERVICE_UNAVAILABLE
    );
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
      Authorization: `Bearer ${token}`,
    },
  });

  if (response.status === 401 || response.status === 403) {
    const { message, code } = authErrorFields(response.status, await readErrorDetail(response));
    throw new ApiAuthError(response.status, message, code);
  }

  if (response.status === 503) {
    // Classify by the machine-readable code only. Read a clone so that any other
    // 503 (e.g. an AI/backend outage) is returned untouched to the caller.
    const detail = await readErrorDetail(response.clone());
    if (detail?.code === AUTH_SERVICE_UNAVAILABLE) {
      throw new ApiAuthError(
        503,
        detail.message || 'Authentication service is temporarily unavailable. Please try again.',
        AUTH_SERVICE_UNAVAILABLE
      );
    }
  }

  return response;
}
