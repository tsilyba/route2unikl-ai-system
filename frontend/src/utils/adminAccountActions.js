// frontend/src/utils/adminAccountActions.js
//
// Helpers for the Admin account actions: Disable / Enable (Milestone M3B-2) and Delete (M3B-3). API paths,
// the account-access state shown on User Details and in "Incomplete deletions", the buttons offered,
// confirmation texts (including the typed confirmation for a deletion), and success and error messages.
// Plain JavaScript with no React or Firebase imports, so it can be tested with:
//   node --test src/utils/adminAccountActions.test.js
//
// The backend (routes/admin_account_actions.py, local emulator mode only) decides which actions are
// allowed and checks the deletion confirmation itself; these helpers only present its answer. Nothing
// here changes accounts.
import { USERS_API_PATH } from './adminUsers.js';

export const ACCOUNT_ACTIONS = Object.freeze(['disable', 'enable', 'delete']);

export const INCOMPLETE_DELETIONS_PATH = '/api/admin/account-operations/incomplete-deletions';

const encoded = (uid) => encodeURIComponent(String(uid));

export const accountAccessPath = (uid) => `${USERS_API_PATH}/${encoded(uid)}/access`;

export const accountActionPath = (uid, action) => {
  if (!ACCOUNT_ACTIONS.includes(action)) throw new Error('Unknown account action');
  return `${USERS_API_PATH}/${encoded(uid)}/${action}`;
};

const ACTION_NAMES = { disable: 'disable', enable: 'enable', delete: 'deletion' };

const STEP_LABELS = {
  restrict_record: 'restricting the access record',
  disable_auth: 'disabling sign-in',
  revoke_sessions: 'ending earlier sessions',
  set_session_threshold: 'recording when new sessions may start',
  settle: 'waiting before re-enabling sign-in',
  enable_auth: 'enabling sign-in',
  activate_record: 'activating the access record',
  mark_deleting: 'marking the account for deletion',
  check_admin_before_data_deletion: 'checking that the account is not an administrator',
  check_no_nested_data: 'checking the student documents for nested data',
  delete_student_data: "deleting the student's data",
  confirm_data_removed: 'confirming that the data was removed',
  check_admin_before_auth_deletion: 'checking again that the account is not an administrator',
  delete_auth: 'deleting the sign-in account',
  finalize_record: 'recording the deletion as complete',
  verify: 'checking the result',
};

const REASON_LABELS = {
  AUTH_UNAVAILABLE: 'Firebase Authentication could not be reached',
  STORE_UNAVAILABLE: 'Firestore could not be reached',
  RECORD_CHANGED: 'the access record was changed by something else',
  ACCOUNT_REMOVED: 'the account no longer exists',
  UNEXPECTED_STATE: 'the final check did not match the expected state',
  INTERNAL_ERROR: 'an unexpected server error occurred',
  ADMIN_TARGET: 'the account became an administrator account',
  LOCK_LOST: 'another request took over this operation',
  NESTED_DATA: "the student's documents contain nested data that this tool does not delete",
  DATA_REMAINS: 'some student data was still present afterwards',
};

export const getStepLabel = (step) => STEP_LABELS[step] ?? 'an unrecorded step';
export const getReasonLabel = (reason) => REASON_LABELS[reason] ?? 'the reason was not recorded';

const ISSUE_TEXT = {
  AUTH_DISABLED_RECORD_ACTIVE: 'Sign-in is disabled in Firebase Authentication, but the access record is still active.',
  AUTH_ENABLED_RECORD_DISABLED: 'Sign-in is enabled in Firebase Authentication, but the access record is disabled.',
};

// What to do next about an unfinished deletion, from its recorded reason.
const deletionGuidance = (reason) => {
  if (reason === 'ADMIN_TARGET') {
    return 'This account is now an administrator account, so the deletion will not continue. Review the account in the Firebase console.';
  }
  if (reason === 'NESTED_DATA') {
    return "The student's documents contain nested data that this tool does not delete. Review it before resuming the deletion.";
  }
  return 'Only the deletion can continue: resume it to finish. It cannot be undone or cancelled.';
};

const resumeGuidance = (operation, reason) => {
  if (operation === 'delete') return deletionGuidance(reason);
  return operation === 'enable'
    ? "The student's data stays blocked until the enable finishes. Resume the enable, or disable the account to cancel it."
    : "The student's data is already blocked. Resume the disable to finish it.";
};

const unfinished = (op) => {
  const name = ACTION_NAMES[op?.operation] ?? 'change';
  const where = op?.failed_step
    ? `It stopped while ${getStepLabel(op.failed_step)}: ${getReasonLabel(op.reason)}.`
    : 'It stopped without recording a step (the server may have restarted).';
  return `An earlier ${name} of this account did not finish. ${where}`;
};

const recordShowsDeletion = (access) => ['deleting', 'deleted'].includes(access?.record?.state);

// What the "Account access" card shows: { state, label, tone, description, details }.
export const describeAccountAccess = (access) => {
  const state = access?.state;
  if (state === 'active') {
    return { state, label: 'Active', tone: 'active', details: [],
      description: 'The student can sign in and use their data.' };
  }
  if (state === 'disabled') {
    return { state, label: 'Disabled', tone: 'disabled', details: [],
      description: 'The student cannot sign in, and sessions that were open before cannot read their data.' };
  }
  if (state === 'inconsistent') {
    return { state, label: 'Needs attention', tone: 'warning',
      description: 'Firebase Authentication and the access record disagree. Disable the account to make it consistent, or enable it.',
      details: (access.issues ?? []).map((issue) => ISSUE_TEXT[issue]).filter(Boolean) };
  }
  if (state === 'incomplete') {
    return { state, label: 'Incomplete change', tone: 'warning',
      description: unfinished(access.operation), details: [resumeGuidance(access.operation?.operation)] };
  }
  if (state === 'deletion_incomplete') {
    const details = [];
    if (access.auth_status === 'missing') details.push('The sign-in account has already been deleted.');
    details.push(recordShowsDeletion(access)
      ? 'The student can no longer use their data or the Route2UniKL server.'
      : 'Until the deletion is resumed, the student may still be able to use their account.');
    details.push(deletionGuidance(access.operation?.reason));
    return { state, label: 'Deletion incomplete', tone: 'warning', details,
      description: access.operation
        ? unfinished({ ...access.operation, operation: 'delete' })
        : 'A deletion of this account started but did not finish.' };
  }
  if (state === 'deleted') {
    return { state, label: 'Deleted', tone: 'neutral', details: [],
      description: 'This account has been permanently deleted. Only a minimal deletion record is kept.' };
  }
  if (state === 'in_progress') {
    const who = access.operation?.started_by_you ? 'You started' : 'Another administrator started';
    const what = access.operation?.operation === 'delete' ? 'a deletion of this account' : 'a change to this account';
    return { state, label: access.operation?.operation === 'delete' ? 'Deletion in progress' : 'Change in progress',
      tone: 'info', details: [], description: `${who} ${what} that is still running. Refresh in a moment.` };
  }
  if (state === 'protected') {
    const details = !access.is_self && recordShowsDeletion(access)
      ? ['A deletion of this account was stopped because it became an administrator account. Review it in the Firebase console.']
      : [];
    return { state, label: 'Protected', tone: 'admin', details,
      description: access.is_self
        ? 'This is your own account. You cannot disable, enable or delete it.'
        : 'Administrator accounts cannot be disabled, enabled or deleted here.' };
  }
  if (state === 'unsupported') {
    const record = access.record ?? {};
    let description = 'This account cannot be disabled, enabled or deleted here.';
    if (record.status === 'missing') {
      description = 'This account has no access record (it was registered before the trusted registration), so it cannot be disabled, enabled or deleted here yet.';
    } else if (record.status === 'malformed') {
      description = "This account's access record is not in the expected format. It is never repaired automatically, so the account cannot be changed here.";
    } else if (record.state === 'deleting' || record.state === 'deleted') {
      description = "This account's access record shows a deletion, so the account cannot be disabled or enabled.";
    }
    return { state, label: 'Not available', tone: 'neutral', description, details: [] };
  }
  return { state: 'unknown', label: 'Unknown', tone: 'neutral', details: [],
    description: "The account's access state could not be read." };
};

const BUTTON_LABELS = {
  disable: ['Disable account', 'Resume disable'],
  enable: ['Enable account', 'Resume enable'],
  delete: ['Delete account', 'Resume deletion'],
};

// Buttons to offer, from the backend's allowed_actions. Never for administrators or the caller.
export const getActionButtons = (access) => {
  if (!access || access.is_admin === true || access.is_self === true || !Array.isArray(access.allowed_actions)) return [];
  return access.allowed_actions
    .filter((action) => ACCOUNT_ACTIONS.includes(action))
    .map((action) => {
      const resume = action === 'delete'
        ? access.state === 'deletion_incomplete'
        : access.state === 'incomplete' && access.operation?.operation === action;
      return { action, label: BUTTON_LABELS[action][resume ? 1 : 0], resume, tone: action === 'enable' ? 'primary' : 'danger' };
    });
};

// What the administrator must type to confirm a deletion: the student's email address, or the account ID
// when no email address is known (for example when the sign-in account is already gone).
export const getDeleteConfirmationTarget = ({ email, uid } = {}) => {
  if (typeof email === 'string' && email.trim()) {
    return { kind: 'email', value: email.trim(), label: "Type the student's email address to confirm" };
  }
  return { kind: 'uid', value: String(uid ?? ''), label: 'Type the account ID to confirm' };
};

// Email addresses match ignoring surrounding spaces and letter case; account IDs must match exactly
// (apart from surrounding spaces). A usability safeguard only: the server checks its own confirmation.
export const confirmationMatches = (typed, target) => {
  if (typeof typed !== 'string' || !target?.value) return false;
  const value = typed.trim();
  return target.kind === 'email' ? value.toLowerCase() === target.value.toLowerCase() : value === target.value;
};

export const getConfirmation = (action, { name, resume = false, email, uid } = {}) => {
  const who = name || 'This student';
  if (action === 'delete') {
    return {
      title: resume ? 'Finish deleting this account?' : 'Permanently delete this account?',
      message: resume
        ? 'The unfinished deletion will continue: the sign-in account and any remaining student data will be permanently deleted.'
        : `${who}'s sign-in account and all their data (profile, SPM results and AI assessment) will be permanently deleted.`,
      warning: 'This cannot be undone. Deleted accounts and data cannot be restored.',
      confirmLabel: resume ? 'Resume deletion' : 'Delete permanently',
      pendingLabel: 'Deleting…',
      tone: 'danger',
      typed: getDeleteConfirmationTarget({ email, uid }),
    };
  }
  if (action === 'disable') {
    return {
      title: resume ? 'Resume the unfinished disable?' : 'Disable this account?',
      message: `${who} will not be able to sign in, and sessions that are open now lose access to their data. You can enable the account again later.`,
      confirmLabel: resume ? 'Resume disable' : 'Disable account',
      pendingLabel: 'Disabling…',
      tone: 'danger',
    };
  }
  return {
    title: resume ? 'Resume the unfinished enable?' : 'Enable this account?',
    message: `${who} will be able to sign in again. Sessions from before the account was disabled stay blocked, so the student must sign in again. This takes a few seconds.`,
    confirmLabel: resume ? 'Resume enable' : 'Enable account',
    pendingLabel: 'Enabling…',
    tone: 'primary',
  };
};

const SUCCESS = {
  disable: ['Account disabled', 'The account has been disabled.'],
  enable: ['Account enabled', 'The account has been enabled. The student must sign in again.'],
  delete: ['Account deleted', "The account and the student's data have been permanently deleted. Only a minimal deletion record is kept."],
};

// Feedback after a completed action: { tone, title, message }.
export const describeActionSuccess = (result) => {
  const operation = SUCCESS[result?.operation] ? result.operation : 'disable';
  const notes = [];
  if (result?.audit_recorded === false) notes.push('The change was made, but its audit record could not be completed.');
  if (result?.lock_released === false) {
    notes.push(operation === 'delete'
      ? 'Its operation record could not be cleared, so it may still appear under "Incomplete deletions"; resuming it there clears it.'
      : 'The account may show "Change in progress" for up to two minutes.');
  }
  const [title, base] = SUCCESS[operation];
  return { tone: notes.length ? 'warning' : 'success', title, message: [base, ...notes].join(' ') };
};

// History state carried from User Details to Manage Users after a completed deletion: two flags only, no
// identifier or personal data.
export const deletionNoticeState = (result) => ({
  accountDeleted: { audit_recorded: result?.audit_recorded !== false, lock_released: result?.lock_released !== false },
});

// The Manage Users notice for that history state, or null when there is none.
export const getDeletionNotice = (state) => {
  const flags = state?.accountDeleted;
  if (!flags || typeof flags !== 'object') return null;
  return describeActionSuccess({ operation: 'delete', audit_recorded: flags.audit_recorded !== false,
    lock_released: flags.lock_released !== false });
};

const ERROR_TEXT = {
  OPERATION_IN_PROGRESS: ['Another change is in progress', 'Another change to this account is running. Refresh in a moment, then try again.'],
  INCOMPLETE_OPERATION_PENDING: ['An earlier change must be finished first', 'An earlier change to this account did not finish. Resume it before starting another one.'],
  ALREADY_DISABLED: ['Already disabled', 'This account is already disabled. Nothing was changed.'],
  ALREADY_ACTIVE: ['Already active', 'This account is already active. Nothing was changed.'],
  SELF_ACTION_FORBIDDEN: ['Not allowed', 'You cannot disable, enable or delete your own account. Nothing was changed.'],
  ADMIN_TARGET_FORBIDDEN: ['Not allowed', 'Administrator accounts cannot be disabled, enabled or deleted here. Nothing was changed.'],
  ACCESS_RECORD_UNSUPPORTED: ['Not available for this account', 'This account has no usable access record, so it cannot be changed here.'],
  USER_NOT_FOUND: ['Account not found', 'No account exists with this ID. It may have been removed.'],
  ACCOUNT_ACTION_UNAVAILABLE: ['Account actions unavailable', 'Account actions are temporarily unavailable. Nothing was changed. Try again in a moment.'],
  ACCOUNT_DELETION_IN_PROGRESS: ['Deletion in progress', 'This account is being deleted. Only the deletion can be resumed. Nothing was changed.'],
  ACCOUNT_DELETED: ['Already deleted', 'This account has already been deleted. Nothing was changed.'],
  DELETE_NOT_ALLOWED: ['Cannot delete this account now', 'Only an active or disabled account can be deleted. Resolve its state first. Nothing was changed.'],
  DELETE_CONFIRMATION_MISMATCH: ['Deletion not confirmed', 'The server did not receive a confirmation for this account. Nothing was changed.'],
};
const INFO_CODES = new Set(['ALREADY_DISABLED', 'ALREADY_ACTIVE', 'ACCOUNT_DELETED']);

// Refusals the server sends with HTTP 403 and a code: the target account is protected, not the caller's
// administrator access (L1). Every other 403 still means "admin access not confirmed".
const PROTECTED_TARGET_CODES = new Set(['SELF_ACTION_FORBIDDEN', 'ADMIN_TARGET_FORBIDDEN']);

const fixedError = (code) => {
  const [title, message] = ERROR_TEXT[code];
  return { tone: INFO_CODES.has(code) ? 'info' : 'error', title, message };
};

// Feedback after a failed action: { tone, title, message }. Never claims "nothing changed" unless the
// server said so.
export const describeActionError = (error) => {
  if (error?.name === 'ApiAuthError') {
    if (error.status === 403 && PROTECTED_TARGET_CODES.has(error.code)) return fixedError(error.code);
    if (error.status === 401) return { tone: 'error', title: 'Session expired', message: 'Your session is no longer valid. Sign in again to continue. Nothing was changed.' };
    if (error.status === 403) return { tone: 'error', title: 'Admin access not confirmed', message: 'The server did not confirm administrator access. Nothing was changed.' };
    return { tone: 'error', title: 'Sign-in service unavailable', message: "We couldn't verify your sign-in. Nothing was changed. Try again in a moment." };
  }
  if (error instanceof TypeError) {
    return { tone: 'error', title: "Can't reach the Route2UniKL server",
      message: 'The request may not have reached the server. Refresh to check the account before trying again.' };
  }
  const code = error?.code;
  if (code === 'OPERATION_INCOMPLETE') {
    const detail = error.detail ?? {};
    const name = ACTION_NAMES[detail.operation] ?? 'change';
    const stopped = `It stopped while ${getStepLabel(detail.failed_step)}: ${getReasonLabel(detail.reason)}.`;
    if (detail.operation === 'delete') {
      return { tone: 'error', title: 'The deletion did not finish',
        message: `${stopped} The deletion has been recorded. ${deletionGuidance(detail.reason)}` };
    }
    return { tone: 'error', title: `The ${name} did not finish`,
      message: `${stopped} The account was left in a safe state and the change has been recorded. ${resumeGuidance(detail.operation)}` };
  }
  if (ERROR_TEXT[code]) return fixedError(code);
  if (error?.status === 404) {
    return { tone: 'error', title: 'Not available on this server', message: 'Account actions are available only when the backend runs with the local Firebase emulators.' };
  }
  return { tone: 'error', title: 'Something went wrong', message: "The server's answer could not be read. Refresh to check the account's current state." };
};

// Loading the account-access state failed: { kind, message, retry }.
export const describeAccessLoadError = (error) => {
  if (error?.name === 'AdminUsersRequestError' && error.status === 404 && !error.code) {
    return { kind: 'unavailable', retry: false,
      message: 'Disabling, enabling and deleting accounts are available only when the backend runs with the local Firebase emulators.' };
  }
  if (error?.code === 'USER_NOT_FOUND') {
    return { kind: 'not-found', retry: false, message: 'No account exists with this ID.' };
  }
  if (error instanceof TypeError) {
    return { kind: 'server-unreachable', retry: true, message: "Can't reach the Route2UniKL server. Check that the backend is running." };
  }
  return { kind: 'error', retry: true, message: "The account's access state could not be loaded. Try again." };
};

// Loading "Incomplete deletions" failed: null hides the panel (a server without account actions, or a
// sign-in problem that the page's own request already reports), otherwise a short message.
export const describeIncompleteDeletionsError = (error) => {
  if (error?.name === 'ApiAuthError') return null;
  if (error?.name === 'AdminUsersRequestError' && error.status === 404 && !error.code) return null;
  if (error instanceof TypeError) return "Can't reach the Route2UniKL server to check for incomplete deletions.";
  return 'Incomplete deletions could not be checked. Try again.';
};

// Keeps only the allow-listed fields of an error response's detail (identifiers and codes, no text).
export const pickErrorDetail = (detail) => {
  if (!detail || typeof detail !== 'object') return null;
  const picked = {};
  for (const key of ['operation', 'operation_id', 'failed_step', 'reason']) {
    if (typeof detail[key] === 'string') picked[key] = detail[key];
  }
  return picked;
};
