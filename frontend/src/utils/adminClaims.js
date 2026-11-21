// frontend/src/utils/adminClaims.js
//
// Admin access is decided ONLY by the Firebase custom claim `admin: true`,
// which can be set solely with the Firebase Admin SDK (server-side).
// Never use the email address or the user-editable Firestore `users/{uid}.role`
// field for admin decisions.
//
// NOTE: These checks drive UI routing only. They do not protect data.
// Firestore Security Rules and FastAPI endpoints must verify the claim
// independently on every request.

export const ADMIN_HOME = '/admin/dashboard';
export const STUDENT_HOME = '/dashboard';

/**
 * Returns true only if the user's ID token carries `admin: true`.
 * Pass { forceRefresh: true } to fetch a fresh token from Firebase so
 * recently added or removed claims are reflected immediately.
 */
export async function hasAdminClaim(user, { forceRefresh = false } = {}) {
  if (!user) return false;
  const tokenResult = await user.getIdTokenResult(forceRefresh);
  return tokenResult.claims.admin === true;
}
