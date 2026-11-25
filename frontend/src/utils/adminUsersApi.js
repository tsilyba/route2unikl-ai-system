// frontend/src/utils/adminUsersApi.js
//
// Calls to the Admin "Manage Users" endpoints, through authFetch, which attaches the
// Firebase ID token. The backend checks the admin claim on every request (require_admin).
// M3A endpoints are read-only. The M3B-2 Disable / Enable actions exist only when the
// backend runs with the local Firebase emulators; the browser never changes Firebase
// accounts itself, it only asks the protected FastAPI endpoints to.
import { signOut } from 'firebase/auth';
import { auth } from '../firebase';
import { authFetch } from './apiClient';
import { AdminUsersRequestError, USERS_API_PATH, signOutThenRedirect } from './adminUsers';
import { accountAccessPath, accountActionPath, pickErrorDetail } from './adminAccountActions';

const readJson = async (response) => {
  try {
    return await response.json();
  } catch {
    return null;
  }
};

const requestJson = async (path, options) => {
  const response = await authFetch(path, options);
  const body = await readJson(response);
  if (!response.ok) {
    throw new AdminUsersRequestError(response.status, body?.detail?.code ?? null, pickErrorDetail(body?.detail));
  }
  if (!body || typeof body !== 'object') {
    throw new AdminUsersRequestError(response.status, 'INVALID_RESPONSE');
  }
  return body;
};

const getJson = (path) => requestJson(path);

// GET /api/admin/users with a query string built by buildUserListQuery() (starts with "?").
export const fetchAdminUsers = (query) => getJson(`${USERS_API_PATH}${query}`);

// GET /api/admin/users/{uid}
export const fetchAdminUser = (uid) => getJson(`${USERS_API_PATH}/${encodeURIComponent(uid)}`);

// GET /api/admin/users/{uid}/access (M3B-2; 404 without a code when the server does not offer account actions)
export const fetchAccountAccess = (uid) => getJson(accountAccessPath(uid));

// POST /api/admin/users/{uid}/disable and /enable (M3B-2). No request body: the target comes from the
// path and the acting administrator from the verified token.
export const disableAccount = (uid) => requestJson(accountActionPath(uid, 'disable'), { method: 'POST' });
export const enableAccount = (uid) => requestJson(accountActionPath(uid, 'enable'), { method: 'POST' });

// Ends the Firebase session, then goes to the login page (expired sessions and the
// "Sign out" action when the server did not confirm admin access). If sign-out
// fails, the returned promise rejects WITHOUT navigating; callers must handle it.
export const signOutToLogin = (navigate) => signOutThenRedirect(() => signOut(auth), navigate);
