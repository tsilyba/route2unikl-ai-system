// frontend/src/utils/adminAccountActions.test.js
//
// Admin Disable / Enable helpers (Milestone M3B-2). Synthetic data only: no browser, Firebase,
// router or network. Run from the frontend folder:
//   node --test src/utils/adminAccountActions.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ACCOUNT_ACTIONS,
  accountAccessPath,
  accountActionPath,
  describeAccessLoadError,
  describeAccountAccess,
  describeActionError,
  describeActionSuccess,
  getActionButtons,
  getConfirmation,
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
    assert.deepEqual(ACCOUNT_ACTIONS, ['disable', 'enable']);
    assert.equal(accountAccessPath('abc_123'), '/api/admin/users/abc_123/access');
    assert.equal(accountActionPath('abc_123', 'disable'), '/api/admin/users/abc_123/disable');
    assert.equal(accountActionPath('abc_123', 'enable'), '/api/admin/users/abc_123/enable');
    assert.equal(accountAccessPath('a/b?c'), '/api/admin/users/a%2Fb%3Fc/access');
  });

  test('only the two actions exist', () => {
    for (const action of ['delete', 'DISABLE', '', undefined, '../disable']) {
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
    assert.deepEqual(getActionButtons(access({ allowed_actions: ['delete', 'disable'] })).map((b) => b.action), ['disable']);
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
