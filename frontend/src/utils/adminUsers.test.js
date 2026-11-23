// frontend/src/utils/adminUsers.test.js
//
// Tests for the read-only Manage Users helpers. No browser, Firebase or network.
// Run from the frontend folder:
//   node --test src/utils/adminUsers.test.js
import { describe, mock, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  AdminUsersRequestError,
  DEFAULT_PAGE_SIZE,
  MAX_PAGE_SIZE,
  MAX_SEARCH_LENGTH,
  PROFILE_FILTERS,
  SIGN_OUT_FAILED_MESSAGE,
  STATUS_FILTERS,
  STUDENT_TYPE_FILTERS,
  USERS_API_PATH,
  buildListSearchParams,
  buildUserListQuery,
  describeUserRequestError,
  formatDateTime,
  formatYesNo,
  getJourneyStepLabel,
  getPageRange,
  getProviderLabel,
  getSignOutControls,
  getStudentTypeLabel,
  hasActiveFilters,
  isValidUid,
  normaliseSearch,
  readListFilters,
  signOutThenRedirect,
} from './adminUsers.js';

const params = (query) => new URLSearchParams(query);
const apiAuthError = (status, code = null) => Object.assign(new Error('auth'), { name: 'ApiAuthError', status, code });

describe('constants mirror the backend limits', () => {
  test('API path, page sizes and search length', () => {
    assert.equal(USERS_API_PATH, '/api/admin/users');
    assert.equal(DEFAULT_PAGE_SIZE, 20);
    assert.equal(MAX_PAGE_SIZE, 50);
    assert.equal(MAX_SEARCH_LENGTH, 100);
  });

  test('filter options match the backend values', () => {
    assert.deepEqual(STUDENT_TYPE_FILTERS.map((o) => o.value), ['spm_leaver', 'form_4_5', 'legacy', 'unknown']);
    assert.deepEqual(STATUS_FILTERS.map((o) => o.value), ['active', 'disabled']);
    assert.deepEqual(PROFILE_FILTERS.map((o) => o.value), ['present', 'missing']);
  });
});

describe('reading filters from the page URL', () => {
  test('valid values are read', () => {
    assert.deepEqual(readListFilters(params('search=aisyah&student_type=form_4_5&status=disabled&profile=missing&page=3')), {
      search: 'aisyah', studentType: 'form_4_5', status: 'disabled', profile: 'missing', page: 3,
    });
  });

  test('missing, unknown or invalid values fall back to defaults', () => {
    assert.deepEqual(readListFilters(params('')), { search: '', studentType: '', status: '', profile: '', page: 1 });
    const filters = readListFilters(params('student_type=admin&status=deleted&profile=orphaned&page=0'));
    assert.deepEqual(filters, { search: '', studentType: '', status: '', profile: '', page: 1 });
    for (const page of ['-2', '1.5', 'abc', '10001', '']) {
      assert.equal(readListFilters(params(`page=${page}`)).page, 1, page);
    }
  });

  test('search terms are trimmed, whitespace-collapsed and length-limited', () => {
    assert.equal(normaliseSearch('  Ali   Bin  Abu  '), 'Ali Bin Abu');
    assert.equal(normaliseSearch('x'.repeat(150)).length, MAX_SEARCH_LENGTH);
    assert.equal(normaliseSearch(undefined), '');
    assert.equal(readListFilters(params('search=%20%20aisyah%20%20')).search, 'aisyah');
  });
});

describe('building URLs and API queries', () => {
  test('page URL omits empty values and page 1', () => {
    assert.equal(buildListSearchParams({ search: '', studentType: '', status: '', profile: '', page: 1 }).toString(), '');
    assert.equal(
      buildListSearchParams({ search: ' ali ', studentType: 'spm_leaver', status: 'active', profile: 'present', page: 2 }).toString(),
      'search=ali&student_type=spm_leaver&status=active&profile=present&page=2'
    );
  });

  test('API query always includes page and page_size and drops invalid values', () => {
    assert.equal(buildUserListQuery({}), '?page=1&page_size=20');
    assert.equal(
      buildUserListQuery({ search: 'Ben Lee', studentType: 'legacy', status: 'disabled', profile: 'missing', page: 4, pageSize: 50 }),
      '?search=Ben+Lee&student_type=legacy&status=disabled&profile=missing&page=4&page_size=50'
    );
    assert.equal(buildUserListQuery({ studentType: 'admin', status: 'x', profile: 'y', page: -1, pageSize: 500 }),
      '?page=1&page_size=20');
  });

  test('round trip: URL → filters → URL', () => {
    const query = 'search=chong&student_type=legacy&page=2';
    assert.equal(buildListSearchParams(readListFilters(params(query))).toString(), query);
  });

  test('active-filter detection', () => {
    assert.equal(hasActiveFilters({ search: '', studentType: '', status: '', profile: '' }), false);
    assert.equal(hasActiveFilters({ search: 'a', studentType: '', status: '', profile: '' }), true);
    assert.equal(hasActiveFilters({ search: '', studentType: '', status: '', profile: 'missing' }), true);
  });
});

describe('labels and formatting', () => {
  test('student types, including legacy, unknown and no profile', () => {
    assert.equal(getStudentTypeLabel('spm_leaver'), 'SPM leaver');
    assert.equal(getStudentTypeLabel('form_4_5'), 'Form 4/5 student');
    assert.equal(getStudentTypeLabel('legacy'), 'Legacy student type');
    assert.equal(getStudentTypeLabel('unknown'), 'Unknown student type');
    assert.equal(getStudentTypeLabel(null), 'No student profile');
    assert.equal(getStudentTypeLabel('admin'), 'No student profile');
  });

  test('learning-journey steps', () => {
    assert.equal(getJourneyStepLabel(2), 'Interests chosen');
    assert.equal(getJourneyStepLabel(5), 'Preparation plan opened');
    assert.equal(getJourneyStepLabel(null), 'Not started');
    assert.equal(getJourneyStepLabel(9), 'Not started');
  });

  test('providers, yes/no and dates', () => {
    assert.equal(getProviderLabel('password'), 'Email and password');
    assert.equal(getProviderLabel('saml.something'), 'Other');
    assert.equal(formatYesNo(true), 'Yes');
    assert.equal(formatYesNo(false), 'No');
    assert.equal(formatYesNo(null), '—');
    assert.equal(formatDateTime(null), '—');
    assert.equal(formatDateTime('not-a-date'), '—');
    assert.notEqual(formatDateTime('2026-03-01T08:00:00Z'), '—');
  });

  test('page ranges', () => {
    assert.deepEqual(getPageRange({ page: 1, pageSize: 20, total: 0 }), { from: 0, to: 0 });
    assert.deepEqual(getPageRange({ page: 1, pageSize: 20, total: 57 }), { from: 1, to: 20 });
    assert.deepEqual(getPageRange({ page: 3, pageSize: 20, total: 57 }), { from: 41, to: 57 });
    assert.deepEqual(getPageRange({ page: 9, pageSize: 20, total: 57 }), { from: 0, to: 0 });
  });

  test('uid validation matches the backend pattern', () => {
    assert.equal(isValidUid('AbC_123-xyz'), true);
    for (const uid of ['', 'bad uid', 'x.y', 'a/b', 'a'.repeat(129), null, undefined]) {
      assert.equal(isValidUid(uid), false, String(uid));
    }
  });
});

describe('error descriptions', () => {
  test('authentication failures', () => {
    const expired = describeUserRequestError(apiAuthError(401));
    assert.equal(expired.kind, 'session-expired');
    assert.equal(expired.autoSignOut, true);
    assert.equal(expired.retry, false);
    assert.doesNotMatch(expired.message, /redirect/i); // never claims a redirect before sign-out succeeds
    const forbidden = describeUserRequestError(apiAuthError(403));
    assert.equal(forbidden.kind, 'forbidden');
    assert.equal(forbidden.signOut, true);
    assert.equal(forbidden.autoSignOut, undefined);
    assert.equal(forbidden.retry, false);
    const outage = describeUserRequestError(apiAuthError(503, 'AUTH_SERVICE_UNAVAILABLE'));
    assert.equal(outage.kind, 'auth-unavailable');
    assert.equal(outage.retry, true);
  });

  test('network and backend failures', () => {
    assert.equal(describeUserRequestError(new TypeError('Failed to fetch')).kind, 'server-unreachable');
    assert.equal(describeUserRequestError(new AdminUsersRequestError(404, 'USER_NOT_FOUND')).kind, 'not-found');
    assert.equal(describeUserRequestError(new AdminUsersRequestError(503, 'USER_SERVICE_UNAVAILABLE')).kind, 'service-unavailable');
    assert.equal(describeUserRequestError(new AdminUsersRequestError(422)).kind, 'invalid-request');
    assert.equal(describeUserRequestError(new AdminUsersRequestError(500)).kind, 'error');
    assert.equal(describeUserRequestError(new AdminUsersRequestError(200, 'INVALID_RESPONSE')).kind, 'error');
    assert.equal(describeUserRequestError(undefined).kind, 'error');
  });

  test('messages never include server-provided text', () => {
    const info = describeUserRequestError(new AdminUsersRequestError(503, 'USER_SERVICE_UNAVAILABLE'));
    assert.equal(info.message, 'Firebase could not be reached. Please try again in a moment.');
    assert.ok(!new AdminUsersRequestError(500, 'X').message.includes('X'));
  });
});

describe('signing out before redirecting to the login page', () => {
  test('successful sign-out redirects to /login (replacing history) only after sign-out finishes', async () => {
    const events = [];
    const signOut = async () => {
      events.push('sign-out started');
      await Promise.resolve();
      events.push('sign-out finished');
    };
    const navigate = (path, options) => events.push(['navigate', path, options]);

    await signOutThenRedirect(signOut, navigate);
    assert.deepEqual(events, ['sign-out started', 'sign-out finished', ['navigate', '/login', { replace: true }]]);
  });

  test('failed sign-out rejects with the original error and does not redirect', async () => {
    const failure = Object.assign(new Error('offline'), { code: 'auth/network-request-failed' });
    const navigate = mock.fn();

    await assert.rejects(signOutThenRedirect(async () => { throw failure; }, navigate), (error) => error === failure);
    await assert.rejects(signOutThenRedirect(() => { throw failure; }, navigate), (error) => error === failure);
    assert.equal(navigate.mock.callCount(), 0);
  });

  test('retrying after a failed sign-out signs out and redirects exactly once', async () => {
    let attempts = 0;
    const signOut = async () => {
      attempts += 1;
      if (attempts === 1) throw new Error('offline');
    };
    const navigate = mock.fn();

    await assert.rejects(signOutThenRedirect(signOut, navigate));
    assert.equal(navigate.mock.callCount(), 0);
    await signOutThenRedirect(signOut, navigate);
    assert.equal(attempts, 2);
    assert.equal(navigate.mock.callCount(), 1);
    assert.deepEqual(navigate.mock.calls[0].arguments, ['/login', { replace: true }]);
  });
});

describe('sign-out controls on the error panel', () => {
  const expired = describeUserRequestError(apiAuthError(401));
  const forbidden = describeUserRequestError(apiAuthError(403));
  const retryButton = { label: 'Try signing out again', disabled: false };

  test('expired session: shows progress while signing out automatically, with no button', () => {
    assert.deepEqual(getSignOutControls(expired, 'pending'), {
      progress: 'Signing you out and returning to the login page…', error: null, button: null,
    });
  });

  test('expired session: a failed sign-out replaces the progress message with an error and a retry button', () => {
    const controls = getSignOutControls(expired, 'failed');
    assert.deepEqual(controls, { progress: null, error: SIGN_OUT_FAILED_MESSAGE, button: retryButton });
    assert.doesNotMatch(`${expired.message} ${controls.error}`, /redirect|returning to the login/i);
    assert.match(controls.error, /try again/i);
  });

  test('admin access not confirmed: Sign out button, disabled while signing out, retry after failure', () => {
    assert.deepEqual(getSignOutControls(forbidden, 'idle').button, { label: 'Sign out', disabled: false });
    assert.deepEqual(getSignOutControls(forbidden, 'pending').button, { label: 'Signing out…', disabled: true });
    assert.deepEqual(getSignOutControls(forbidden, 'failed'), { progress: null, error: SIGN_OUT_FAILED_MESSAGE, button: retryButton });
  });

  test('other errors have no sign-out controls', () => {
    const errors = [
      apiAuthError(503, 'AUTH_SERVICE_UNAVAILABLE'), new TypeError('Failed to fetch'),
      new AdminUsersRequestError(404, 'USER_NOT_FOUND'), new AdminUsersRequestError(503, 'USER_SERVICE_UNAVAILABLE'),
      new AdminUsersRequestError(422), new AdminUsersRequestError(500),
    ];
    for (const error of errors) {
      assert.equal(getSignOutControls(describeUserRequestError(error), 'failed'), null, String(error));
    }
  });
});
