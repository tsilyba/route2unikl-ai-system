// frontend/src/utils/signOutFlow.test.js
//
// Regression tests for the shared Admin sign-out flow. Sign-out is a fake function:
// no browser, Firebase, router or network. Run from the frontend folder:
//   node --test src/utils/signOutFlow.test.js
import { afterEach, beforeEach, describe, mock, test } from 'node:test';
import assert from 'node:assert/strict';
import process from 'node:process';
import { setImmediate } from 'node:timers/promises';
import {
  SIGN_OUT_FAILED_MESSAGE,
  createAttemptTracker,
  endSession,
  signOutThenRedirect,
} from './signOutFlow.js';
import * as adminUsers from './adminUsers.js';

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

const offline = () => Object.assign(new Error('offline'), { code: 'auth/network-request-failed' });

// Callbacks that record what happened, in order.
const recorder = (events, label = '') => ({
  onSignedOut: () => events.push(`${label}signed out`),
  onFailed: () => events.push(`${label}failed`),
});

// Any unhandled rejection during these tests is a failure.
let unhandled;
const onUnhandled = (reason) => unhandled.push(reason);
beforeEach(() => {
  unhandled = [];
  process.on('unhandledRejection', onUnhandled);
});
afterEach(async () => {
  await setImmediate(); // let any unhandled rejection surface first
  process.off('unhandledRejection', onUnhandled);
  assert.deepEqual(unhandled, [], 'no unhandled promise rejections');
});

describe('failure message', () => {
  test('is actionable and never claims a redirect', () => {
    assert.match(SIGN_OUT_FAILED_MESSAGE, /couldn't sign you out/i);
    assert.match(SIGN_OUT_FAILED_MESSAGE, /try again/i);
    assert.doesNotMatch(SIGN_OUT_FAILED_MESSAGE, /redirect|login page/i);
  });
});

describe('endSession: success and failure', () => {
  test('successful sign-out: onSignedOut runs once, only after sign-out has finished', async () => {
    const events = [];
    const signOut = async () => {
      events.push('sign-out started');
      await Promise.resolve();
      events.push('sign-out finished');
    };
    const result = await endSession({ signOut, ...recorder(events) });
    assert.equal(result, true);
    assert.deepEqual(events, ['sign-out started', 'sign-out finished', 'signed out']);
  });

  test('failed asynchronous sign-out: onFailed runs once, no redirect, and it does not reject', async () => {
    const events = [];
    const result = await endSession({ signOut: async () => { throw offline(); }, ...recorder(events) });
    assert.equal(result, false);
    assert.deepEqual(events, ['failed']);
  });

  test('immediately thrown sign-out error is handled the same way', async () => {
    const events = [];
    const result = await endSession({ signOut: () => { throw offline(); }, ...recorder(events) });
    assert.equal(result, false);
    assert.deepEqual(events, ['failed']);
  });

  test('onFailed runs only after the failure, never before sign-out settles', async () => {
    const events = [];
    const pending = deferred();
    const run = endSession({ signOut: () => pending.promise, ...recorder(events) });
    await Promise.resolve();
    assert.deepEqual(events, [], 'nothing happens while sign-out is pending');
    pending.reject(offline());
    assert.equal(await run, false);
    assert.deepEqual(events, ['failed']);
  });

  test('retry after a failure signs out again and redirects exactly once', async () => {
    const events = [];
    let calls = 0;
    const signOut = async () => {
      calls += 1;
      if (calls === 1) throw offline();
    };
    assert.equal(await endSession({ signOut, ...recorder(events) }), false);
    assert.equal(await endSession({ signOut, ...recorder(events) }), true);
    assert.equal(calls, 2);
    assert.deepEqual(events, ['failed', 'signed out']);
  });
});

describe('endSession: stale callbacks are ignored', () => {
  test('a component that unmounted (or re-verified) while signing out runs no callback', async () => {
    for (const outcome of ['success', 'failure']) {
      const events = [];
      let active = true;
      const pending = deferred();
      const run = endSession({ signOut: () => pending.promise, ...recorder(events), isActive: () => active });
      active = false; // unmount, verification restarted, or StrictMode's discarded run
      if (outcome === 'success') pending.resolve();
      else pending.reject(offline());
      await run;
      assert.deepEqual(events, [], outcome);
    }
  });

  test('isActive is checked when sign-out settles, not when it starts', async () => {
    const events = [];
    let active = false;
    const pending = deferred();
    const run = endSession({ signOut: () => pending.promise, ...recorder(events), isActive: () => active });
    active = true;
    pending.resolve();
    await run;
    assert.deepEqual(events, ['signed out']);
  });
});

describe('createAttemptTracker: retries cannot run obsolete callbacks', () => {
  test('begin() supersedes the previous attempt; cancel() supersedes the current one', () => {
    const tracker = createAttemptTracker();
    const first = tracker.begin();
    assert.equal(first(), true);
    const second = tracker.begin();
    assert.equal(first(), false);
    assert.equal(second(), true);
    tracker.cancel(); // e.g. unmount
    assert.equal(second(), false);
    assert.equal(tracker.begin()(), true, 'a new attempt after cancel() is current');
  });

  test('trackers are independent', () => {
    const a = createAttemptTracker();
    const b = createAttemptTracker();
    const fromA = a.begin();
    b.begin();
    b.cancel();
    assert.equal(fromA(), true);
  });

  test('an attempt superseded by a retry runs no callback; only the retry reports the outcome', async () => {
    for (const outcome of ['success', 'failure']) {
      const events = [];
      const tracker = createAttemptTracker();
      const pending = deferred();
      const signOut = mock.fn(() => pending.promise);
      const old = endSession({ signOut, ...recorder(events, 'old: '), isActive: tracker.begin() });
      // The retry starts while the old attempt is still in progress, so it joins it.
      const retry = endSession({ signOut, ...recorder(events, 'retry: '), isActive: tracker.begin() });
      if (outcome === 'success') pending.resolve();
      else pending.reject(offline());
      await Promise.all([old, retry]);
      assert.equal(signOut.mock.callCount(), 1, outcome);
      assert.deepEqual(events, [outcome === 'success' ? 'retry: signed out' : 'retry: failed'], outcome);
    }
  });
});

describe('overlapping attempts share one sign-out', () => {
  test('concurrent requests call sign-out once; each active caller gets the outcome, in order', async () => {
    const events = [];
    const pending = deferred();
    const signOut = mock.fn(() => pending.promise);
    const first = endSession({ signOut, ...recorder(events, 'A: ') });
    const second = endSession({ signOut, ...recorder(events, 'B: ') });
    pending.resolve();
    assert.deepEqual(await Promise.all([first, second]), [true, true]);
    assert.equal(signOut.mock.callCount(), 1);
    assert.deepEqual(events, ['A: signed out', 'B: signed out']);
  });

  test('a shared failure reaches every active caller and redirects none', async () => {
    const events = [];
    const pending = deferred();
    const signOut = mock.fn(() => pending.promise);
    const navigate = mock.fn();
    const first = endSession({ signOut, ...recorder(events, 'A: ') });
    // The M3A helper joins the same attempt; its rejection is checked immediately.
    const second = assert.rejects(signOutThenRedirect(signOut, navigate), { code: 'auth/network-request-failed' });
    pending.reject(offline());
    assert.equal(await first, false);
    await second;
    assert.equal(signOut.mock.callCount(), 1);
    assert.equal(navigate.mock.callCount(), 0);
    assert.deepEqual(events, ['A: failed']);
  });

  test('a joining caller that is no longer active is ignored; the other still completes', async () => {
    const events = [];
    const pending = deferred();
    let bActive = true;
    const signOut = mock.fn(() => pending.promise);
    const first = endSession({ signOut, ...recorder(events, 'A: ') });
    const second = endSession({ signOut, ...recorder(events, 'B: '), isActive: () => bActive });
    bActive = false;
    pending.resolve();
    await Promise.all([first, second]);
    assert.deepEqual(events, ['A: signed out']);
  });

  test('after an attempt settles, the next request starts a fresh sign-out', async () => {
    const signOut = mock.fn(async () => {});
    await endSession({ signOut, onSignedOut() {}, onFailed() {} });
    await endSession({ signOut, onSignedOut() {}, onFailed() {} });
    assert.equal(signOut.mock.callCount(), 2);
  });
});

describe('M3A compatibility (signOutThenRedirect)', () => {
  test('adminUsers.js re-exports the same helper and message', () => {
    assert.equal(adminUsers.signOutThenRedirect, signOutThenRedirect);
    assert.equal(adminUsers.SIGN_OUT_FAILED_MESSAGE, SIGN_OUT_FAILED_MESSAGE);
  });

  test('redirects to /login (replacing history) only after a successful sign-out', async () => {
    const events = [];
    await signOutThenRedirect(
      async () => events.push('signed out'),
      (path, options) => events.push(['navigate', path, options])
    );
    assert.deepEqual(events, ['signed out', ['navigate', '/login', { replace: true }]]);
  });

  test('a failed sign-out rejects with the original error and never redirects', async () => {
    const failure = offline();
    const navigate = mock.fn();
    await assert.rejects(signOutThenRedirect(async () => { throw failure; }, navigate), (error) => error === failure);
    await assert.rejects(signOutThenRedirect(() => { throw failure; }, navigate), (error) => error === failure);
    assert.equal(navigate.mock.callCount(), 0);
  });
});
