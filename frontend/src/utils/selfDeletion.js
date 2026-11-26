// frontend/src/utils/selfDeletion.js
//
// Student self-service account deletion (Milestone M3C, local Firebase emulators only). Replaces the unsafe
// browser deletion in Profile.jsx, which deleted users/{uid} and then the Auth account from the browser and
// left results/ and ai_assessments/ behind (S4, FL6, DL5).
//
// The browser no longer deletes anything itself. Profile.jsx re-authenticates the student with their
// password (a recent sign-in is required by the server), then asks the backend (POST /api/account/delete,
// routes/account_self_service.py) to run the protected deletion, and signs out only after the server
// reports it complete. In production (no emulators) the route does not exist yet, and the page says so.
//
// Plain JavaScript with no React or Firebase imports, so it can be tested with:
//   node --test src/utils/selfDeletion.test.js
// Nothing here repeats the password, the email address or any server text other than fixed codes.

export const SELF_DELETE_PATH = '/api/account/delete';

export const SELF_DELETE_TEXT = Object.freeze({
  productionUnavailable: 'Deleting your account from the app is not available yet. Please contact the Route2UniKL administrator if you want your account and data deleted.',
  warning: 'This permanently deletes your sign-in account and all your Route2UniKL data (profile, SPM results and AI assessment). It cannot be undone.',
  passwordLabel: 'Enter your password to confirm',
  confirmLabel: 'Delete my account permanently',
  pendingLabel: 'Deleting…',
  signOutFailed: 'Your account has been deleted, but this browser could not finish signing out. Close this browser window to end the session.',
});

const result = (ok, kind, tone, title, message) => ({ ok, kind, tone, title, message });

// Re-authentication failed in the browser (Firebase client error codes). The server was not contacted, so
// nothing was changed.
export const describeReauthError = (error) => {
  const code = error?.code;
  if (['auth/wrong-password', 'auth/invalid-credential', 'auth/invalid-login-credentials'].includes(code)) {
    return result(false, 'password', 'error', 'Password not accepted', 'The password is not correct. Nothing was changed.');
  }
  if (code === 'auth/missing-password') {
    return result(false, 'password', 'error', 'Password required', 'Enter your password to confirm. Nothing was changed.');
  }
  if (code === 'auth/too-many-requests') {
    return result(false, 'retry-later', 'error', 'Too many attempts', 'Too many attempts. Wait a few minutes, then try again. Nothing was changed.');
  }
  if (code === 'auth/network-request-failed') {
    return result(false, 'network', 'error', "Can't reach the sign-in service", 'Check your connection, then try again. Nothing was changed.');
  }
  if (['auth/user-disabled', 'auth/user-not-found', 'auth/user-token-expired', 'auth/user-mismatch'].includes(code)) {
    return result(false, 'session', 'error', 'Please sign in again', 'Your session is no longer valid. Sign in again, then try again. Nothing was changed.');
  }
  return result(false, 'error', 'error', 'Password not confirmed', "Your password couldn't be confirmed. Nothing was changed. Try again.");
};

// Fixed texts for the server's codes. "Nothing was changed" appears only for refusals the server makes
// before any change (every code below except OPERATION_INCOMPLETE).
const CODE_TEXT = {
  RECENT_SIGN_IN_REQUIRED: ['reauth', 'Please confirm your password again', 'For your security, confirm your password again just before deleting your account. Nothing was changed.'],
  SESSION_TOO_OLD: ['session', 'Please sign in again', 'Your session started before your account was last re-enabled. Sign in again, then try again. Nothing was changed.'],
  ACCOUNT_ACCESS_DENIED: ['denied', "Your account can't be deleted here", 'Your account cannot use this feature at the moment. Please contact the Route2UniKL administrator. Nothing was changed.'],
  ACCOUNT_DELETED: ['denied', 'Account already deleted', 'This account has already been deleted.'],
  ADMIN_TARGET_FORBIDDEN: ['denied', 'Not available for administrators', 'Administrator accounts cannot be deleted here. Nothing was changed.'],
  ACCESS_RECORD_UNSUPPORTED: ['denied', "Your account can't be deleted here", 'Please contact the Route2UniKL administrator. Nothing was changed.'],
  DELETE_NOT_ALLOWED: ['denied', "Your account can't be deleted now", 'Your account cannot be deleted in its current state. Please contact the Route2UniKL administrator. Nothing was changed.'],
  INCOMPLETE_OPERATION_PENDING: ['denied', "Your account can't be deleted now", 'An earlier change to your account has not finished. Please contact the Route2UniKL administrator. Nothing was changed.'],
  OPERATION_IN_PROGRESS: ['retry-later', 'Another change is in progress', 'Another change to your account is in progress. Try again in a few minutes. Nothing was changed.'],
  DELETE_CONFIRMATION_MISMATCH: ['error', 'Deletion not confirmed', 'The deletion was not confirmed for your account. Nothing was changed.'],
  INVALID_REQUEST: ['error', 'Deletion not confirmed', 'The deletion request was not valid. Nothing was changed.'],
  ACCOUNT_ACTION_UNAVAILABLE: ['retry-later', 'Deletion temporarily unavailable', 'Account deletion is temporarily unavailable. Nothing was changed. Try again in a moment.'],
  ACCOUNT_STATUS_UNAVAILABLE: ['retry-later', 'Deletion temporarily unavailable', 'Your account status could not be checked. Nothing was changed. Try again in a moment.'],
  AUTH_SERVICE_UNAVAILABLE: ['retry-later', 'Sign-in service unavailable', "We couldn't verify your sign-in. Nothing was changed. Try again in a moment."],
};

const fromCode = (code) => {
  const [kind, title, message] = CODE_TEXT[code];
  return result(false, kind, 'error', title, message);
};

// The outcome of the server's answer: { ok, kind, tone, title, message }.
export const selfDeletionOutcome = (status, detail) => {
  const code = typeof detail?.code === 'string' ? detail.code : null;
  if (status === 200) {
    return result(true, 'deleted', 'success', 'Account deleted', 'Your account and your data have been permanently deleted.');
  }
  if (code === 'OPERATION_INCOMPLETE') {
    // Something may already have changed: never "nothing was changed" here.
    return result(false, 'incomplete', 'warning', 'The deletion did not finish',
      'Your account deletion started but did not finish. It has been recorded so that it can be completed. '
      + 'Try again in a moment; if you can no longer sign in, the Route2UniKL administrator can complete it.');
  }
  if (code && CODE_TEXT[code]) return fromCode(code);
  if (status === 401) {
    return result(false, 'session', 'error', 'Please sign in again', 'Your session is no longer valid. Sign in again, then try again. Nothing was changed.');
  }
  if (status === 404) {
    return result(false, 'unavailable', 'error', 'Not available on this server', SELF_DELETE_TEXT.productionUnavailable);
  }
  return result(false, 'error', 'error', 'Something went wrong',
    "The server's answer could not be read. Refresh the page and sign in again to check whether your account still exists.");
};

// A thrown request error: ApiAuthError (401/403/503 from authFetch) or a network failure (TypeError).
export const describeSelfDeletionError = (error) => {
  if (error?.name === 'ApiAuthError') return selfDeletionOutcome(error.status, { code: error.code });
  if (error instanceof TypeError) {
    return result(false, 'network', 'error', "Can't reach the Route2UniKL server",
      'The request may not have reached the server. Refresh the page and sign in again to check whether your account still exists before trying again.');
  }
  return selfDeletionOutcome(null, null);
};

const readBody = async (response) => {
  try {
    return await response.json();
  } catch {
    return null;
  }
};

// Asks the backend to delete the signed-in student's own account. `authFetch` attaches the (freshly
// refreshed) ID token. Resolves to an outcome and never rejects.
export const requestOwnAccountDeletion = async ({ uid, authFetch }) => {
  if (typeof uid !== 'string' || !uid) return selfDeletionOutcome(401, null);
  let response;
  try {
    response = await authFetch(SELF_DELETE_PATH, { method: 'POST', body: JSON.stringify({ confirm_uid: uid }) });
  } catch (error) {
    return describeSelfDeletionError(error);
  }
  const body = await readBody(response);
  if (response.status === 200) {
    // Success only when the server says the deletion was completed (verified on the server).
    return body?.outcome === 'completed' ? selfDeletionOutcome(200, null) : selfDeletionOutcome(null, null);
  }
  return selfDeletionOutcome(response.status, body?.detail ?? null);
};
