// frontend/src/utils/apiErrors.js
//
// How authFetch (apiClient.js) describes a 401 or 403 answer from the backend. Plain JavaScript with no
// React or Firebase imports, so it can be tested with:
//   node --test src/utils/apiErrors.test.js
//
// FastAPI sends `detail` either as a string (token problems: core/auth.py) or as an object
// { code, message } (refusals with a machine-readable code, for example the Admin account actions'
// SELF_ACTION_FORBIDDEN / ADMIN_TARGET_FORBIDDEN, or ACCOUNT_DELETED from the student-data check).
// Before M3B-3 the object's code was dropped, so a refusal of a protected account was shown as
// "admin access not confirmed" (L1). The status still decides how a 401 or 403 is handled; the code
// only lets callers show the accurate message.

export const AUTH_SERVICE_UNAVAILABLE = 'AUTH_SERVICE_UNAVAILABLE';

const CODE_PATTERN = /^[A-Z][A-Z0-9_]{0,63}$/;
const MAX_MESSAGE_LENGTH = 300;

const text = (value) => (typeof value === 'string' && value.trim() ? value.trim().slice(0, MAX_MESSAGE_LENGTH) : '');

// { message, code } for an ApiAuthError built from a 401/403 response's `detail` (null if unreadable).
export const authErrorFields = (status, detail) => {
  const fallback = status === 401 ? 'Authentication required.' : 'Access denied.';
  if (typeof detail === 'string') return { message: text(detail) || fallback, code: null };
  if (!detail || typeof detail !== 'object') return { message: fallback, code: null };
  const code = typeof detail.code === 'string' && CODE_PATTERN.test(detail.code) ? detail.code : null;
  return {
    message: text(detail.message) || fallback,
    // AUTH_SERVICE_UNAVAILABLE means "retry later" and belongs to 503 only: it never relabels a 401 or 403.
    code: code === AUTH_SERVICE_UNAVAILABLE ? null : code,
  };
};
