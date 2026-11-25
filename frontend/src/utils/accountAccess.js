// frontend/src/utils/accountAccess.js
//
// With the account-access guard (local emulators only for now, M3B-1B-P1-B2B/C), Firestore refuses a
// student whose access record is missing or blocked. Login.jsx checks this once and shows a clear
// message instead of letting the student pages fail later. The message reveals no account details.

export const ACCOUNT_ACCESS_DENIED_MESSAGE =
  "Your account can't access student data at the moment. Please contact the Route2UniKL administrator.";

export const isAccountAccessDenied = (error) => error?.code === 'permission-denied';

/**
 * Runs readOwnProfile() and reports 'allowed', 'denied' (Firestore refused: permission-denied) or
 * 'unknown' (any other failure, e.g. the network). This is a UX check only: Firestore rules are what
 * enforce access, so 'unknown' does not block the login.
 */
export const probeAccountAccess = async (readOwnProfile) => {
  try {
    await readOwnProfile();
    return 'allowed';
  } catch (error) {
    return isAccountAccessDenied(error) ? 'denied' : 'unknown';
  }
};
