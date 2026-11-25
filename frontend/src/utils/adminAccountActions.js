// frontend/src/utils/adminAccountActions.js
//
// Helpers for the Admin Disable / Enable account actions (Milestone M3B-2): API paths, the account-access
// state shown on User Details, the buttons offered, confirmation texts, and success and error messages.
// Plain JavaScript with no React or Firebase imports, so it can be tested with:
//   node --test src/utils/adminAccountActions.test.js
//
// The backend (routes/admin_account_actions.py, local emulator mode only) decides which actions are
// allowed; these helpers only present its answer. Nothing here changes accounts.
import { USERS_API_PATH } from './adminUsers.js';

export const ACCOUNT_ACTIONS = Object.freeze(['disable', 'enable']);

const encoded = (uid) => encodeURIComponent(String(uid));

export const accountAccessPath = (uid) => `${USERS_API_PATH}/${encoded(uid)}/access`;

export const accountActionPath = (uid, action) => {
  if (!ACCOUNT_ACTIONS.includes(action)) throw new Error('Unknown account action');
  return `${USERS_API_PATH}/${encoded(uid)}/${action}`;
};

const ACTION_NAMES = { disable: 'disable', enable: 'enable' };

const STEP_LABELS = {
  restrict_record: 'restricting the access record',
  disable_auth: 'disabling sign-in',
  revoke_sessions: 'ending earlier sessions',
  set_session_threshold: 'recording when new sessions may start',
  settle: 'waiting before re-enabling sign-in',
  enable_auth: 'enabling sign-in',
  activate_record: 'activating the access record',
  verify: 'checking the result',
};

const REASON_LABELS = {
  AUTH_UNAVAILABLE: 'Firebase Authentication could not be reached',
  STORE_UNAVAILABLE: 'Firestore could not be reached',
  RECORD_CHANGED: 'the access record was changed by something else',
  ACCOUNT_REMOVED: 'the account no longer exists',
  UNEXPECTED_STATE: 'the final check did not match the expected state',
  INTERNAL_ERROR: 'an unexpected server error occurred',
};

export const getStepLabel = (step) => STEP_LABELS[step] ?? 'an unrecorded step';
export const getReasonLabel = (reason) => REASON_LABELS[reason] ?? 'the reason was not recorded';

const ISSUE_TEXT = {
  AUTH_DISABLED_RECORD_ACTIVE: 'Sign-in is disabled in Firebase Authentication, but the access record is still active.',
  AUTH_ENABLED_RECORD_DISABLED: 'Sign-in is enabled in Firebase Authentication, but the access record is disabled.',
};

const resumeGuidance = (operation) =>
  operation === 'enable'
    ? "The student's data stays blocked until the enable finishes. Resume the enable, or disable the account to cancel it."
    : "The student's data is already blocked. Resume the disable to finish it.";

const unfinished = (op) => {
  const name = ACTION_NAMES[op?.operation] ?? 'change';
  const where = op?.failed_step
    ? `It stopped while ${getStepLabel(op.failed_step)}: ${getReasonLabel(op.reason)}.`
    : 'It stopped without recording a step (the server may have restarted).';
  return `An earlier ${name} of this account did not finish. ${where}`;
};

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
  if (state === 'in_progress') {
    const who = access.operation?.started_by_you ? 'You started' : 'Another administrator started';
    return { state, label: 'Change in progress', tone: 'info', details: [],
      description: `${who} a change to this account that is still running. Refresh in a moment.` };
  }
  if (state === 'protected') {
    return { state, label: 'Protected', tone: 'admin', details: [],
      description: access.is_self
        ? 'This is your own account. You cannot disable or enable it.'
        : 'Administrator accounts cannot be disabled or enabled here.' };
  }
  if (state === 'unsupported') {
    const record = access.record ?? {};
    let description = 'This account cannot be disabled or enabled here.';
    if (record.status === 'missing') {
      description = 'This account has no access record (it was registered before the trusted registration), so it cannot be disabled or enabled here yet.';
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

// Buttons to offer, from the backend's allowed_actions. Never for administrators or the caller.
export const getActionButtons = (access) => {
  if (!access || access.is_admin === true || access.is_self === true || !Array.isArray(access.allowed_actions)) return [];
  return access.allowed_actions
    .filter((action) => ACCOUNT_ACTIONS.includes(action))
    .map((action) => {
      const resume = access.state === 'incomplete' && access.operation?.operation === action;
      const label = action === 'disable'
        ? (resume ? 'Resume disable' : 'Disable account')
        : (resume ? 'Resume enable' : 'Enable account');
      return { action, label, resume, tone: action === 'disable' ? 'danger' : 'primary' };
    });
};

export const getConfirmation = (action, { name, resume = false } = {}) => {
  const who = name || 'This student';
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

// Feedback after a completed action: { tone, title, message }.
export const describeActionSuccess = (result) => {
  const notes = [];
  if (result?.audit_recorded === false) notes.push('The change was made, but its audit record could not be completed.');
  if (result?.lock_released === false) notes.push('The account may show "Change in progress" for up to two minutes.');
  const base = result?.operation === 'enable'
    ? 'The account has been enabled. The student must sign in again.'
    : 'The account has been disabled.';
  return { tone: notes.length ? 'warning' : 'success', title: result?.operation === 'enable' ? 'Account enabled' : 'Account disabled',
    message: [base, ...notes].join(' ') };
};

const ERROR_TEXT = {
  OPERATION_IN_PROGRESS: ['Another change is in progress', 'Another change to this account is running. Refresh in a moment, then try again.'],
  INCOMPLETE_OPERATION_PENDING: ['An earlier change must be finished first', 'An earlier change to this account did not finish. Resume it before starting another one.'],
  ALREADY_DISABLED: ['Already disabled', 'This account is already disabled. Nothing was changed.'],
  ALREADY_ACTIVE: ['Already active', 'This account is already active. Nothing was changed.'],
  SELF_ACTION_FORBIDDEN: ['Not allowed', 'You cannot disable or enable your own account.'],
  ADMIN_TARGET_FORBIDDEN: ['Not allowed', 'Administrator accounts cannot be disabled or enabled here.'],
  ACCESS_RECORD_UNSUPPORTED: ['Not available for this account', 'This account has no usable access record, so it cannot be changed here.'],
  USER_NOT_FOUND: ['Account not found', 'No account exists with this ID. It may have been removed.'],
  ACCOUNT_ACTION_UNAVAILABLE: ['Account actions unavailable', 'Account actions are temporarily unavailable. Nothing was changed. Try again in a moment.'],
};

// Feedback after a failed action: { tone, title, message }. Never claims "nothing changed" unless the
// server said so.
export const describeActionError = (error) => {
  if (error?.name === 'ApiAuthError') {
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
    return { tone: 'error', title: `The ${name} did not finish`,
      message: `It stopped while ${getStepLabel(detail.failed_step)}: ${getReasonLabel(detail.reason)}. The account was left in a safe state and the change has been recorded. ${resumeGuidance(detail.operation)}` };
  }
  if (ERROR_TEXT[code]) {
    const [title, message] = ERROR_TEXT[code];
    return { tone: code === 'ALREADY_DISABLED' || code === 'ALREADY_ACTIVE' ? 'info' : 'error', title, message };
  }
  if (error?.status === 404) {
    return { tone: 'error', title: 'Not available on this server', message: 'Account actions are available only when the backend runs with the local Firebase emulators.' };
  }
  return { tone: 'error', title: 'Something went wrong', message: "The server's answer could not be read. Refresh to check the account's current state." };
};

// Loading the account-access state failed: { kind, message, retry }.
export const describeAccessLoadError = (error) => {
  if (error?.name === 'AdminUsersRequestError' && error.status === 404 && !error.code) {
    return { kind: 'unavailable', retry: false,
      message: 'Disabling and enabling accounts is available only when the backend runs with the local Firebase emulators.' };
  }
  if (error?.code === 'USER_NOT_FOUND') {
    return { kind: 'not-found', retry: false, message: 'No account exists with this ID.' };
  }
  if (error instanceof TypeError) {
    return { kind: 'server-unreachable', retry: true, message: "Can't reach the Route2UniKL server. Check that the backend is running." };
  }
  return { kind: 'error', retry: true, message: "The account's access state could not be loaded. Try again." };
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
