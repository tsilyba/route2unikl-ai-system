// frontend/src/utils/adminAccountActions.test.js
//
// Admin Disable / Enable helpers (Milestone M3B-2). Synthetic data only: no browser, Firebase,
// router or network. Run from the frontend folder:
//   node --test src/utils/adminAccountActions.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ACCOUNT_ACTIONS,
  INCOMPLETE_DELETIONS_PATH,
  STALE_LOCK_MINUTES,
  accountAccessPath,
  accountActionPath,
  confirmationMatches,
  deletionNoticeState,
  describeAccessLoadError,
  describeAccountAccess,
  describeActionError,
  describeActionSuccess,
  describeIncompleteDeletionsError,
  formatServerTime,
  getActionButtons,
  getConfirmation,
  getDeleteConfirmationTarget,
  getDeletionNotice,
  getReasonLabel,
  getStepLabel,
  pickErrorDetail,
} from './adminAccountActions.js';
import { AdminUsersRequestError } from './adminUsers.js';

const access = (overrides = {}) => ({
  uid: 'student-uid',
  auth_status: 'enabled',
  is_admin: false,
  is_self: false,
  record: { status: 'valid', state: 'active', version: 1, sessions_valid_after: null },
  issues: [],
  operation: null,
  state: 'active',
  allowed_actions: ['disable'],
  ...overrides,
});

const incomplete = (operation, extra = {}) => access({
  state: 'incomplete',
  allowed_actions: operation === 'enable' ? ['enable', 'disable'] : ['disable'],
  operation: { operation_id: 'op-1', operation, status: 'incomplete', failed_step: 'disable_auth',
    reason: 'AUTH_UNAVAILABLE', started_at: null, updated_at: null, started_by_you: true, ...extra },
});

const apiAuthError = (status, code = null) => Object.assign(new Error('auth'), { name: 'ApiAuthError', status, code });

describe('API paths', () => {
  test('access and action paths under the Manage Users API, with the uid encoded', () => {
    assert.deepEqual(ACCOUNT_ACTIONS, ['disable', 'enable', 'delete']);
    assert.equal(accountAccessPath('abc_123'), '/api/admin/users/abc_123/access');
    assert.equal(accountActionPath('abc_123', 'disable'), '/api/admin/users/abc_123/disable');
    assert.equal(accountActionPath('abc_123', 'enable'), '/api/admin/users/abc_123/enable');
    assert.equal(accountActionPath('abc_123', 'delete'), '/api/admin/users/abc_123/delete');
    assert.equal(accountAccessPath('a/b?c'), '/api/admin/users/a%2Fb%3Fc/access');
    assert.equal(INCOMPLETE_DELETIONS_PATH, '/api/admin/account-operations/incomplete-deletions');
  });

  test('only the three actions exist', () => {
    for (const action of ['purge', 'DELETE', 'DISABLE', '', undefined, '../disable', 'delete/']) {
      assert.throws(() => accountActionPath('abc', action), /Unknown account action/);
    }
  });
});

describe('describeAccountAccess', () => {
  test('active and disabled', () => {
    assert.deepEqual(
      [describeAccountAccess(access()).label, describeAccountAccess(access()).tone],
      ['Active', 'active'],
    );
    const disabled = describeAccountAccess(access({ state: 'disabled', allowed_actions: ['enable'] }));
    assert.equal(disabled.label, 'Disabled');
    assert.match(disabled.description, /cannot sign in/);
  });

  test('inconsistent accounts explain the disagreement', () => {
    const view = describeAccountAccess(access({ state: 'inconsistent', issues: ['AUTH_DISABLED_RECORD_ACTIVE', 'UNKNOWN_ISSUE'] }));
    assert.equal(view.label, 'Needs attention');
    assert.deepEqual(view.details, ['Sign-in is disabled in Firebase Authentication, but the access record is still active.']);
  });

  test('an incomplete change names its step and reason and how to recover', () => {
    const disable = describeAccountAccess(incomplete('disable'));
    assert.equal(disable.label, 'Incomplete change');
    assert.match(disable.description, /earlier disable .* did not finish/);
    assert.match(disable.description, /disabling sign-in: Firebase Authentication could not be reached/);
    assert.match(disable.details[0], /already blocked\. Resume the disable/);

    const enable = describeAccountAccess(incomplete('enable', { failed_step: 'activate_record', reason: 'STORE_UNAVAILABLE' }));
    assert.match(enable.description, /activating the access record: Firestore could not be reached/);
    assert.match(enable.details[0], /stays blocked until the enable finishes.*disable the account to cancel it/);

    const expired = describeAccountAccess(incomplete('disable', { failed_step: null, reason: null }));
    assert.match(expired.description, /without recording a step/);
  });

  test('a running change, protected and unsupported accounts', () => {
    assert.match(describeAccountAccess(access({ state: 'in_progress', operation: { started_by_you: false } })).description,
      /Another administrator started/);
    assert.match(describeAccountAccess(access({ state: 'in_progress', operation: { started_by_you: true } })).description,
      /You started/);
    assert.match(describeAccountAccess(access({ state: 'protected', is_self: true })).description, /your own account/);
    assert.match(describeAccountAccess(access({ state: 'protected', is_admin: true })).description, /Administrator accounts/);
    const unsupported = (record) => describeAccountAccess(access({ state: 'unsupported', allowed_actions: [], record })).description;
    assert.match(unsupported({ status: 'missing', state: null }), /no access record/);
    assert.match(unsupported({ status: 'malformed', state: null }), /never repaired automatically/);
    assert.match(unsupported({ status: 'valid', state: 'deleting' }), /deletion/);
    assert.match(unsupported({ status: 'valid', state: 'deleted' }), /deletion/);
    assert.equal(describeAccountAccess(undefined).label, 'Unknown');
    assert.equal(describeAccountAccess(access({ state: 'surprise' })).label, 'Unknown');
  });

  test('step and reason labels fall back safely', () => {
    assert.equal(getStepLabel('revoke_sessions'), 'ending earlier sessions');
    assert.equal(getStepLabel('anything-else'), 'an unrecorded step');
    assert.equal(getReasonLabel('RECORD_CHANGED'), 'the access record was changed by something else');
    assert.equal(getReasonLabel(undefined), 'the reason was not recorded');
  });
});

describe('getActionButtons', () => {
  const labels = (value) => getActionButtons(value).map((button) => button.label);

  test('buttons follow the allowed actions', () => {
    assert.deepEqual(labels(access()), ['Disable account']);
    assert.deepEqual(labels(access({ state: 'disabled', allowed_actions: ['enable'] })), ['Enable account']);
    assert.deepEqual(labels(access({ state: 'inconsistent', allowed_actions: ['disable', 'enable'] })),
      ['Disable account', 'Enable account']);
    assert.deepEqual(labels(incomplete('disable')), ['Resume disable']);
    assert.deepEqual(labels(incomplete('enable')), ['Resume enable', 'Disable account']);
    assert.deepEqual(getActionButtons(access()).map((button) => button.tone), ['danger']);
  });

  test('never for administrators, the caller, or without allowed actions', () => {
    assert.deepEqual(getActionButtons(access({ is_admin: true })), []);
    assert.deepEqual(getActionButtons(access({ is_self: true })), []);
    assert.deepEqual(getActionButtons(access({ allowed_actions: [] })), []);
    assert.deepEqual(getActionButtons(access({ allowed_actions: undefined })), []);
    assert.deepEqual(getActionButtons(access({ allowed_actions: ['purge', 'disable'] })).map((b) => b.action), ['disable']);
    assert.deepEqual(getActionButtons(null), []);
  });
});

describe('getConfirmation', () => {
  test('disable and enable explain the consequence', () => {
    const disable = getConfirmation('disable', { name: 'Aisyah' });
    assert.equal(disable.title, 'Disable this account?');
    assert.match(disable.message, /^Aisyah will not be able to sign in/);
    assert.equal(disable.tone, 'danger');
    assert.equal(disable.pendingLabel, 'Disabling…');
    const enable = getConfirmation('enable', { name: 'Aisyah' });
    assert.equal(enable.title, 'Enable this account?');
    assert.match(enable.message, /Sessions from before the account was disabled stay blocked/);
    assert.equal(enable.confirmLabel, 'Enable account');
  });

  test('resumed actions and a missing name', () => {
    assert.equal(getConfirmation('disable', { resume: true }).title, 'Resume the unfinished disable?');
    assert.equal(getConfirmation('enable', { resume: true }).confirmLabel, 'Resume enable');
    assert.match(getConfirmation('disable').message, /^This student will not/);
  });
});

describe('describeActionSuccess', () => {
  test('completed actions', () => {
    assert.deepEqual(describeActionSuccess({ operation: 'disable', audit_recorded: true, lock_released: true }),
      { tone: 'success', title: 'Account disabled', message: 'The account has been disabled.' });
    assert.match(describeActionSuccess({ operation: 'enable', audit_recorded: true, lock_released: true }).message,
      /must sign in again/);
  });

  test('a missing audit outcome or lock release is reported, not hidden', () => {
    const result = describeActionSuccess({ operation: 'disable', audit_recorded: false, lock_released: false });
    assert.equal(result.tone, 'warning');
    assert.match(result.message, /audit record could not be completed/);
    assert.match(result.message, /Change in progress/);
  });
});

describe('describeActionError', () => {
  test('sign-in problems: nothing was changed', () => {
    assert.equal(describeActionError(apiAuthError(401)).title, 'Session expired');
    assert.equal(describeActionError(apiAuthError(403)).title, 'Admin access not confirmed');
    assert.equal(describeActionError(apiAuthError(503, 'AUTH_SERVICE_UNAVAILABLE')).title, 'Sign-in service unavailable');
    for (const status of [401, 403, 503]) assert.match(describeActionError(apiAuthError(status)).message, /Nothing was changed/);
  });

  test('an unreachable server is not reported as "nothing changed"', () => {
    const info = describeActionError(new TypeError('Failed to fetch'));
    assert.doesNotMatch(info.message, /Nothing was changed/);
    assert.match(info.message, /Refresh to check/);
  });

  test('an incomplete operation names the step, the reason and the recovery', () => {
    const error = new AdminUsersRequestError(503, 'OPERATION_INCOMPLETE',
      { operation: 'enable', operation_id: 'op-9', failed_step: 'enable_auth', reason: 'AUTH_UNAVAILABLE' });
    const info = describeActionError(error);
    assert.equal(info.title, 'The enable did not finish');
    assert.match(info.message, /enabling sign-in: Firebase Authentication could not be reached/);
    assert.match(info.message, /Resume the enable, or disable the account to cancel it/);
    assert.match(describeActionError(new AdminUsersRequestError(503, 'OPERATION_INCOMPLETE')).message, /an unrecorded step/);
  });

  test('refusals have fixed messages', () => {
    const cases = {
      OPERATION_IN_PROGRESS: 'Another change is in progress',
      INCOMPLETE_OPERATION_PENDING: 'An earlier change must be finished first',
      ALREADY_DISABLED: 'Already disabled',
      ALREADY_ACTIVE: 'Already active',
      SELF_ACTION_FORBIDDEN: 'Not allowed',
      ADMIN_TARGET_FORBIDDEN: 'Not allowed',
      ACCESS_RECORD_UNSUPPORTED: 'Not available for this account',
      USER_NOT_FOUND: 'Account not found',
      ACCOUNT_ACTION_UNAVAILABLE: 'Account actions unavailable',
    };
    for (const [code, title] of Object.entries(cases)) {
      assert.equal(describeActionError(new AdminUsersRequestError(409, code)).title, title, code);
    }
    assert.equal(describeActionError(new AdminUsersRequestError(409, 'ALREADY_DISABLED')).tone, 'info');
    assert.match(describeActionError(new AdminUsersRequestError(503, 'ACCOUNT_ACTION_UNAVAILABLE')).message, /Nothing was changed/);
  });

  test('a server without account actions and unknown answers', () => {
    assert.equal(describeActionError(new AdminUsersRequestError(404, null)).title, 'Not available on this server');
    assert.equal(describeActionError(new AdminUsersRequestError(500, 'SOMETHING')).title, 'Something went wrong');
    assert.equal(describeActionError(undefined).title, 'Something went wrong');
  });
});

describe('describeAccessLoadError', () => {
  test('a server without account actions is explained, not treated as an error', () => {
    assert.deepEqual(describeAccessLoadError(new AdminUsersRequestError(404, null)).kind, 'unavailable');
    assert.equal(describeAccessLoadError(new AdminUsersRequestError(404, null)).retry, false);
  });

  test('other failures', () => {
    assert.equal(describeAccessLoadError(new AdminUsersRequestError(404, 'USER_NOT_FOUND')).kind, 'not-found');
    assert.equal(describeAccessLoadError(new TypeError('Failed to fetch')).kind, 'server-unreachable');
    assert.equal(describeAccessLoadError(new AdminUsersRequestError(503, 'ACCOUNT_ACTION_UNAVAILABLE')).retry, true);
    assert.equal(describeAccessLoadError(apiAuthError(401)).kind, 'error');
  });
});

describe('pickErrorDetail', () => {
  test('keeps only identifiers and codes', () => {
    assert.deepEqual(
      pickErrorDetail({ code: 'OPERATION_INCOMPLETE', message: 'text', operation: 'disable', operation_id: 'op-1',
        failed_step: 'disable_auth', reason: 'AUTH_UNAVAILABLE', email: 'someone@example.test', extra: { a: 1 } }),
      { operation: 'disable', operation_id: 'op-1', failed_step: 'disable_auth', reason: 'AUTH_UNAVAILABLE' },
    );
    assert.deepEqual(pickErrorDetail({ operation: 5, reason: null }), {});
    assert.equal(pickErrorDetail('Not Found'), null);
    assert.equal(pickErrorDetail(null), null);
  });

  test('AdminUsersRequestError carries the detail, null by default', () => {
    assert.equal(new AdminUsersRequestError(404, 'USER_NOT_FOUND').detail, null);
    assert.deepEqual(new AdminUsersRequestError(503, 'OPERATION_INCOMPLETE', { reason: 'X' }).detail, { reason: 'X' });
  });
});

// ------------------------------------------------------------------- M3B-3: Delete Student Account
const deletion = (overrides = {}) => access({
  state: 'deletion_incomplete',
  auth_status: 'disabled',
  record: { status: 'valid', state: 'deleting', version: 3, sessions_valid_after: null },
  allowed_actions: ['delete'],
  operation: { operation_id: 'op-d', operation: 'delete', status: 'incomplete', failed_step: 'delete_auth',
    reason: 'AUTH_UNAVAILABLE', started_at: null, updated_at: null, started_by_you: true },
  ...overrides,
});

describe('M3B-3 deletion states', () => {
  test('active and disabled accounts offer Delete as a danger action', () => {
    const buttons = (value) => getActionButtons(value).map(({ action, label, tone, resume }) => [action, label, tone, resume]);
    assert.deepEqual(buttons(access({ allowed_actions: ['disable', 'delete'] })),
      [['disable', 'Disable account', 'danger', false], ['delete', 'Delete account', 'danger', false]]);
    assert.deepEqual(buttons(access({ state: 'disabled', allowed_actions: ['enable', 'delete'] })),
      [['enable', 'Enable account', 'primary', false], ['delete', 'Delete account', 'danger', false]]);
    assert.deepEqual(buttons(deletion()), [['delete', 'Resume deletion', 'danger', true]]);
    assert.deepEqual(getActionButtons(access({ state: 'protected', is_admin: true, allowed_actions: ['delete'] })), []);
    assert.deepEqual(getActionButtons(access({ state: 'protected', is_self: true, allowed_actions: ['delete'] })), []);
  });

  test('an unfinished deletion explains where it stopped, that it cannot be undone, and whether Auth is gone', () => {
    const view = describeAccountAccess(deletion());
    assert.equal(view.label, 'Deletion incomplete');
    assert.match(view.description, /earlier deletion of this account did not finish/);
    assert.match(view.description, /deleting the sign-in account: Firebase Authentication could not be reached/);
    assert.match(view.details.join(' '), /can no longer use their data/);
    assert.match(view.details.join(' '), /cannot be undone or cancelled/);
    assert.doesNotMatch(view.details.join(' '), /already been deleted/);

    const gone = describeAccountAccess(deletion({ auth_status: 'missing',
      operation: { ...deletion().operation, failed_step: 'finalize_record', reason: 'STORE_UNAVAILABLE' } }));
    assert.equal(gone.details[0], 'The sign-in account has already been deleted.');
    assert.match(gone.description, /recording the deletion as complete: Firestore could not be reached/);

    // Stopped before the record was marked: access may not be closed yet, and the text does not claim it is.
    const early = describeAccountAccess(deletion({ record: { status: 'valid', state: 'active', version: 1 },
      operation: { ...deletion().operation, failed_step: 'mark_deleting', reason: 'STORE_UNAVAILABLE' } }));
    assert.match(early.details.join(' '), /may still be able to use their account/);
    assert.doesNotMatch(early.details.join(' '), /can no longer use/);

    assert.match(describeAccountAccess(deletion({ operation: null })).description, /started but did not finish/);
    assert.match(describeAccountAccess(deletion({ operation: { ...deletion().operation, reason: 'NESTED_DATA' } })).details.join(' '),
      /nested data that this tool does not delete/);
  });

  test('deleted, running and protected deletions', () => {
    const deleted = describeAccountAccess(access({ state: 'deleted', auth_status: 'missing', allowed_actions: [],
      record: { status: 'valid', state: 'deleted', version: 4 } }));
    assert.equal(deleted.label, 'Deleted');
    assert.match(deleted.description, /permanently deleted\. Only a minimal deletion record is kept/);
    const running = describeAccountAccess(access({ state: 'in_progress', allowed_actions: [],
      operation: { operation: 'delete', started_by_you: false } }));
    assert.equal(running.label, 'Deletion in progress');
    assert.match(running.description, /Another administrator started a deletion/);
    assert.equal(describeAccountAccess(access({ state: 'in_progress', operation: { operation: 'disable' } })).label,
      'Change in progress');
    const promoted = describeAccountAccess(access({ state: 'protected', is_admin: true, allowed_actions: [],
      record: { status: 'valid', state: 'deleting', version: 2 } }));
    assert.match(promoted.description, /cannot be disabled, enabled or deleted/);
    assert.match(promoted.details[0], /stopped because it became an administrator account/);
    assert.deepEqual(describeAccountAccess(access({ state: 'protected', is_admin: true })).details, []);
    assert.match(describeAccountAccess(access({ state: 'protected', is_self: true })).description, /disable, enable or delete it/);
  });

  test('deletion step and reason labels', () => {
    for (const step of ['mark_deleting', 'check_admin_before_data_deletion', 'check_no_nested_data', 'delete_student_data',
      'confirm_data_removed', 'check_admin_before_auth_deletion', 'delete_auth', 'finalize_record']) {
      assert.notEqual(getStepLabel(step), 'an unrecorded step', step);
    }
    for (const reason of ['ADMIN_TARGET', 'LOCK_LOST', 'NESTED_DATA', 'DATA_REMAINS', 'LOCK_CONTENTION', 'LEASE_EXPIRED']) {
      assert.notEqual(getReasonLabel(reason), 'the reason was not recorded', reason);
    }
  });
});

describe('M3B-3 deletion confirmation', () => {
  test('the dialog warns that deletion is permanent and requires the email address typed in full', () => {
    const confirmation = getConfirmation('delete', { name: 'Aisyah', email: 'Aisyah@Example.test', uid: 'uid-1' });
    assert.equal(confirmation.title, 'Permanently delete this account?');
    assert.match(confirmation.message, /^Aisyah's sign-in account and all their data \(profile, SPM results and AI assessment\)/);
    assert.match(confirmation.warning, /cannot be undone/);
    assert.equal(confirmation.tone, 'danger');
    assert.equal(confirmation.confirmLabel, 'Delete permanently');
    assert.equal(confirmation.pendingLabel, 'Deleting…');
    assert.deepEqual(confirmation.typed,
      { kind: 'email', value: 'Aisyah@Example.test', label: "Type the student's email address to confirm" });
    const resume = getConfirmation('delete', { resume: true, uid: 'uid-1' });
    assert.equal(resume.title, 'Finish deleting this account?');
    assert.equal(resume.confirmLabel, 'Resume deletion');
    assert.deepEqual(resume.typed, { kind: 'uid', value: 'uid-1', label: 'Type the account ID to confirm' });
  });

  test('typed email: case and surrounding spaces ignored; anything else refused', () => {
    const target = getDeleteConfirmationTarget({ email: 'aisyah@example.test', uid: 'uid-1' });
    for (const typed of ['aisyah@example.test', ' AISYAH@example.TEST ']) {
      assert.equal(confirmationMatches(typed, target), true, typed);
    }
    for (const typed of ['', 'aisyah@example', 'aisyah@example.test.', 'uid-1', 'aisyah @example.test', null, undefined, 5]) {
      assert.equal(confirmationMatches(typed, target), false, String(typed));
    }
  });

  test('typed account ID: exact apart from surrounding spaces; no target matches nothing', () => {
    const target = getDeleteConfirmationTarget({ email: '  ', uid: 'AbC-123' });
    assert.equal(target.kind, 'uid');
    assert.equal(confirmationMatches('AbC-123', target), true);
    assert.equal(confirmationMatches(' AbC-123 ', target), true);
    assert.equal(confirmationMatches('abc-123', target), false);
    assert.equal(confirmationMatches('', getDeleteConfirmationTarget({})), false);
    assert.equal(confirmationMatches('x', null), false);
  });
});

describe('M3B-3 deletion outcomes', () => {
  test('success is reported, with any audit or lock problem disclosed', () => {
    assert.deepEqual(describeActionSuccess({ operation: 'delete', audit_recorded: true, lock_released: true }), {
      tone: 'success', title: 'Account deleted',
      message: "The account and the student's data have been permanently deleted. Only a minimal deletion record is kept." });
    const partial = describeActionSuccess({ operation: 'delete', audit_recorded: false, lock_released: false });
    assert.equal(partial.tone, 'warning');
    assert.match(partial.message, /audit record could not be completed/);
    assert.match(partial.message, /Incomplete deletions/);
  });

  test('M3C (DL14/DA4): a running lock explains when it can be resumed; no misleading "in a moment"', () => {
    const resumableAfter = '2026-11-26T12:35:00Z';
    const running = describeAccountAccess(access({ state: 'in_progress', allowed_actions: [],
      operation: { operation: 'delete', started_by_you: true, resumable_after: resumableAfter } }));
    assert.match(running.description, /^You started a deletion of this account that has not finished\./);
    assert.match(running.description, /If it is still running, it normally finishes within a few minutes\./);
    assert.ok(running.description.includes(`it can be resumed after ${formatServerTime(resumableAfter)}`));
    assert.doesNotMatch(running.description, /Refresh in a moment/);
    const unknownTime = describeAccountAccess(access({ state: 'in_progress', operation: { operation: 'disable',
      resumable_after: 'not-a-time' } }));
    assert.match(unknownTime.description, new RegExp(`about ${STALE_LOCK_MINUTES} minutes after its last activity`));
    assert.equal(STALE_LOCK_MINUTES, 35, 'LEASE_SECONDS (300) + TAKEOVER_GRACE_SECONDS (1800) on the server');
    assert.equal(formatServerTime(undefined), null);
    assert.equal(formatServerTime(''), null);
  });

  test('M3C (DL14): an uncleared lock after success states the real waiting time', () => {
    const deleted = describeActionSuccess({ operation: 'delete', audit_recorded: true, lock_released: false });
    assert.match(deleted.message, /"Incomplete deletions" as "Deletion in progress" for up to about 35 minutes/);
    assert.match(deleted.message, /After that, resuming the deletion there clears it/);
    const disabled = describeActionSuccess({ operation: 'disable', audit_recorded: true, lock_released: false });
    assert.match(disabled.message, /"Change in progress" for up to about 35 minutes/);
    assert.doesNotMatch(disabled.message, /two minutes/);
  });

  test('the notice carried to Manage Users holds two flags only', () => {
    const state = deletionNoticeState({ operation: 'delete', operation_id: 'op-1', audit_recorded: true, lock_released: false,
      account: { uid: 'uid-1', email: 'someone@example.test' } });
    assert.deepEqual(state, { accountDeleted: { audit_recorded: true, lock_released: false } });
    assert.equal(getDeletionNotice(state).title, 'Account deleted');
    assert.equal(getDeletionNotice(state).tone, 'warning');
    assert.equal(getDeletionNotice({ accountDeleted: { audit_recorded: true, lock_released: true } }).tone, 'success');
    for (const value of [null, undefined, {}, { accountDeleted: 'yes' }, { other: 1 }]) {
      assert.equal(getDeletionNotice(value), null);
    }
  });

  test('an unfinished deletion is never reported as success and names what to do next', () => {
    const error = new AdminUsersRequestError(503, 'OPERATION_INCOMPLETE',
      { operation: 'delete', operation_id: 'op-2', failed_step: 'finalize_record', reason: 'STORE_UNAVAILABLE' });
    const info = describeActionError(error);
    assert.equal(info.tone, 'error');
    assert.equal(info.title, 'The deletion did not finish');
    assert.match(info.message, /recording the deletion as complete: Firestore could not be reached/);
    assert.match(info.message, /resume it to finish/);
    assert.doesNotMatch(info.message, /safe state|Nothing was changed/);
    const admin = describeActionError(new AdminUsersRequestError(503, 'OPERATION_INCOMPLETE',
      { operation: 'delete', failed_step: 'check_admin_before_auth_deletion', reason: 'ADMIN_TARGET' }));
    assert.match(admin.message, /now an administrator account, so the deletion will not continue/);
  });

  test('deletion refusals have fixed messages', () => {
    const cases = {
      ACCOUNT_DELETION_IN_PROGRESS: ['Deletion in progress', 'error'],
      ACCOUNT_DELETED: ['Already deleted', 'info'],
      DELETE_NOT_ALLOWED: ['Cannot delete this account now', 'error'],
      DELETE_CONFIRMATION_MISMATCH: ['Deletion not confirmed', 'error'],
    };
    for (const [code, [title, tone]] of Object.entries(cases)) {
      const info = describeActionError(new AdminUsersRequestError(code === 'DELETE_CONFIRMATION_MISMATCH' ? 422 : 409, code));
      assert.deepEqual([info.title, info.tone], [title, tone], code);
      assert.match(info.message, /Nothing was changed/, code);
    }
  });

  test('incomplete-deletions loading errors: hidden without account actions or on sign-in problems', () => {
    assert.equal(describeIncompleteDeletionsError(new AdminUsersRequestError(404, null)), null);
    assert.equal(describeIncompleteDeletionsError(apiAuthError(401)), null);
    assert.equal(describeIncompleteDeletionsError(apiAuthError(403)), null);
    assert.match(describeIncompleteDeletionsError(new TypeError('Failed to fetch')), /Can't reach/);
    assert.match(describeIncompleteDeletionsError(new AdminUsersRequestError(503, 'ACCOUNT_ACTION_UNAVAILABLE')),
      /could not be checked/);
  });
});

describe('L1: protected-account refusals are not reported as missing admin access', () => {
  test('a 403 with a protected-target code shows the refusal, not "Admin access not confirmed"', () => {
    const self = describeActionError(apiAuthError(403, 'SELF_ACTION_FORBIDDEN'));
    assert.deepEqual([self.title, self.tone], ['Not allowed', 'error']);
    assert.match(self.message, /your own account\. Nothing was changed/);
    const admin = describeActionError(apiAuthError(403, 'ADMIN_TARGET_FORBIDDEN'));
    assert.match(admin.message, /Administrator accounts cannot be disabled, enabled or deleted here/);
  });

  test('every other 401 and 403 keeps its meaning', () => {
    assert.equal(describeActionError(apiAuthError(403)).title, 'Admin access not confirmed');
    assert.equal(describeActionError(apiAuthError(403, 'SOMETHING_ELSE')).title, 'Admin access not confirmed');
    assert.equal(describeActionError(apiAuthError(403, 'ACCOUNT_DELETED')).title, 'Admin access not confirmed');
    assert.equal(describeActionError(apiAuthError(401, 'SELF_ACTION_FORBIDDEN')).title, 'Session expired');
    assert.equal(describeActionError(apiAuthError(401, 'ADMIN_TARGET_FORBIDDEN')).title, 'Session expired');
  });
});
