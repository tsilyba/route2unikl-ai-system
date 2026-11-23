// frontend/src/utils/adminUsersApi.js
//
// Calls to the read-only Admin "Manage Users" endpoints (Milestone M3A), through
// authFetch, which attaches the Firebase ID token. The backend checks the admin
// claim on every request (require_admin); nothing here can modify accounts.
import { signOut } from 'firebase/auth';
import { auth } from '../firebase';
import { authFetch } from './apiClient';
import { AdminUsersRequestError, USERS_API_PATH, signOutThenRedirect } from './adminUsers';

const readJson = async (response) => {
  try {
    return await response.json();
  } catch {
    return null;
  }
};

const getJson = async (path) => {
  const response = await authFetch(path);
  const body = await readJson(response);
  if (!response.ok) {
    throw new AdminUsersRequestError(response.status, body?.detail?.code ?? null);
  }
  if (!body || typeof body !== 'object') {
    throw new AdminUsersRequestError(response.status, 'INVALID_RESPONSE');
  }
  return body;
};

// GET /api/admin/users with a query string built by buildUserListQuery() (starts with "?").
export const fetchAdminUsers = (query) => getJson(`${USERS_API_PATH}${query}`);

// GET /api/admin/users/{uid}
export const fetchAdminUser = (uid) => getJson(`${USERS_API_PATH}/${encodeURIComponent(uid)}`);

// Ends the Firebase session, then goes to the login page (expired sessions and the
// "Sign out" action when the server did not confirm admin access). If sign-out
// fails, the returned promise rejects WITHOUT navigating; callers must handle it.
export const signOutToLogin = (navigate) => signOutThenRedirect(() => signOut(auth), navigate);
