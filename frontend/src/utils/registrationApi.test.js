// frontend/src/utils/registrationApi.test.js
//
// Trusted backend registration from the browser (local emulator mode). fetch is a fake:
// no browser, Firebase, backend or network. Run from the frontend folder:
//   node --test src/utils/registrationApi.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MESSAGES,
  PASSWORD_MIN_LENGTH,
  REGISTRATION_MESSAGES,
  REGISTRATION_PATH,
  hasControlCharacter,
  isPasswordLengthValid,
  passwordValidationMessage,
  registerThroughBackend,
  registrationResult,
} from './registrationApi.js';

const FORM = Object.freeze({
  name: 'Ali Bin Abu <script>',
  email: 'student-secret-address@example.test',
  password: 'Pw-not-a-real-password-123',
  role: 'form_4_5',
});

// A fake fetch that records its calls and answers with the given status and body.
const fakeFetch = (status, body, { invalidJson = false } = {}) => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      status,
      json: async () => {
        if (invalidJson) throw new SyntaxError('Unexpected token');
        return body;
      },
    };
  };
  return { calls, fetchImpl };
};

// No message may repeat anything the student typed.
const assertNoInputEchoed = (message) => {
  for (const value of [FORM.name, FORM.email, FORM.password, 'student-secret-address', 'Pw-not-a-real']) {
    assert.ok(!message.includes(value), `message echoes input: ${message}`);
  }
};

describe('registerThroughBackend', () => {
  test('posts the four form fields as JSON to the registration route, without credentials', async () => {
    const { calls, fetchImpl } = fakeFetch(201, { status: 'registered' });
    const result = await registerThroughBackend('http://localhost:8000', FORM, fetchImpl);

    assert.deepEqual(result, { ok: true, message: REGISTRATION_MESSAGES.success });
    assert.equal(calls.length, 1);
    assert.equal(REGISTRATION_PATH, '/api/account/register');
    assert.equal(calls[0].url, 'http://localhost:8000/api/account/register');
    assert.equal(calls[0].init.method, 'POST');
    assert.deepEqual(calls[0].init.headers, { 'Content-Type': 'application/json' });
    assert.deepEqual(JSON.parse(calls[0].init.body), FORM);
    assert.equal(calls[0].init.credentials, undefined);
  });

  test('both student roles are sent unchanged', async () => {
    for (const role of ['spm_leaver', 'form_4_5']) {
      const { calls, fetchImpl } = fakeFetch(201, { status: 'registered' });
      await registerThroughBackend('http://localhost:8000', { ...FORM, role }, fetchImpl);
      assert.equal(JSON.parse(calls[0].init.body).role, role);
    }
  });

  test('a network failure resolves to a message and never rejects', async () => {
    const fetchImpl = async () => {
      throw new TypeError(`Failed to fetch ${FORM.password}`);
    };
    const result = await registerThroughBackend('http://localhost:8000', FORM, fetchImpl);
    assert.deepEqual(result, { ok: false, message: REGISTRATION_MESSAGES.network });
  });

  test('an unreadable response body falls back to the status', async () => {
    const created = fakeFetch(201, null, { invalidJson: true });
    assert.equal((await registerThroughBackend('', FORM, created.fetchImpl)).ok, true);
    const failed = fakeFetch(500, null, { invalidJson: true });
    assert.deepEqual(await registerThroughBackend('', FORM, failed.fetchImpl),
      { ok: false, message: REGISTRATION_MESSAGES.failed });
  });

  test('backend error answers become friendly messages without the input', async () => {
    const cases = [
      [409, { code: 'EMAIL_IN_USE' }, REGISTRATION_MESSAGES.emailInUse],
      [503, { code: 'REGISTRATION_INCOMPLETE' }, REGISTRATION_MESSAGES.incomplete],
      [503, { code: 'REGISTRATION_UNAVAILABLE' }, REGISTRATION_MESSAGES.unavailable],
      [404, { detail: 'Not Found' }, REGISTRATION_MESSAGES.notAvailable],
      [413, { code: 'INVALID_REGISTRATION' }, REGISTRATION_MESSAGES.tooLarge],
    ];
    for (const [status, body, message] of cases) {
      const { fetchImpl } = fakeFetch(status, body);
      const result = await registerThroughBackend('', FORM, fetchImpl);
      assert.deepEqual(result, { ok: false, message }, `${status}`);
      assertNoInputEchoed(result.message);
    }
  });
});

// Regression for browser check M5 (26 Nov 2026): the 6–128 character password rule at its boundaries.
describe('password length (6 to 128 characters)', () => {
  const PASSWORD_MESSAGE = 'Please check your password (6 to 128 characters).';
  const passwordOf = (length) => 'Zq9-'.repeat(40).slice(0, length);
  const EMOJI = '\u{1F600}'; // one character (code point), two UTF-16 units

  test('matches the backend limits', () => {
    assert.equal(PASSWORD_MIN_LENGTH, 6);
    assert.equal(PASSWORD_MAX_LENGTH, 128);
  });

  test('5 and 129 characters are refused before any request, without echoing the password', async () => {
    for (const password of [passwordOf(5), passwordOf(129), '', EMOJI.repeat(129)]) {
      const { calls, fetchImpl } = fakeFetch(201, { status: 'registered' });
      const result = await registerThroughBackend('http://localhost:8000', { ...FORM, password }, fetchImpl);
      assert.deepEqual(result, { ok: false, message: PASSWORD_MESSAGE }, `length ${Array.from(password).length}`);
      assert.equal(calls.length, 0, 'no request is sent');
      if (password) assert.ok(!result.message.includes(password));
    }
  });

  test('6 and 128 characters are sent exactly as typed', async () => {
    for (const password of [passwordOf(6), passwordOf(128), 'ab cd1', EMOJI.repeat(128)]) {
      const { calls, fetchImpl } = fakeFetch(201, { status: 'registered' });
      const result = await registerThroughBackend('http://localhost:8000', { ...FORM, password }, fetchImpl);
      assert.equal(result.ok, true, `length ${Array.from(password).length}`);
      assert.equal(JSON.parse(calls[0].init.body).password, password, 'not trimmed or changed');
    }
  });

  test('length is counted in characters (code points), not UTF-16 units', () => {
    assert.equal(EMOJI.repeat(128).length, 256);
    assert.equal(isPasswordLengthValid(EMOJI.repeat(128)), true);
    assert.equal(isPasswordLengthValid(EMOJI.repeat(5)), false);
  });

  test('spaces count towards the length and are never trimmed', async () => {
    // The M5 input (a leading TAB plus 5 characters) is refused since the JL9 control-character rule
    // (see the next describe block); ordinary spaces are kept.
    assert.equal(isPasswordLengthValid(` ${passwordOf(4)} `), true);
    assert.equal(isPasswordLengthValid(`   ${passwordOf(2)}`), false);
    for (const password of [` ${passwordOf(5)}`, `${passwordOf(5)} `, 'Test 123']) {
      const { calls, fetchImpl } = fakeFetch(201, { status: 'registered' });
      await registerThroughBackend('http://localhost:8000', { ...FORM, password }, fetchImpl);
      assert.equal(JSON.parse(calls[0].init.body).password, password, 'sent exactly as typed');
    }
  });

  test('a missing or non-string password is refused', () => {
    for (const password of [undefined, null, 123456, ['abcdef']]) {
      assert.equal(isPasswordLengthValid(password), false, String(password));
      assert.equal(passwordValidationMessage(password), PASSWORD_MESSAGES.length, String(password));
    }
  });
});

// JL9 (26 Nov 2026): passwords containing Unicode control characters (category Cc) are refused on both
// registration paths (Register.jsx calls passwordValidationMessage before either path sends anything).
describe('hidden control characters', () => {
  const CONTROL_PASSWORDS = [
    '\tTest1', // the M5 input: a leading TAB
    'Test1\t',
    'Test\n123', // line feed
    'Test\r123', // carriage return
    'Test\r\n123',
    'Test\u007f123', // DEL
    '\u0000Test123', // NUL
    'Test\u001b123', // ESC
    'Test\u0085123', // NEL (C1 control)
    'Test\u009f123', // last C1 control
  ];

  test('the owner cases', () => {
    assert.equal(passwordValidationMessage('Test1'), PASSWORD_MESSAGES.length); // 5 characters
    assert.equal(passwordValidationMessage('Test123'), null); // 7 characters
    assert.equal(passwordValidationMessage('\tTest1'), PASSWORD_MESSAGES.control); // TAB + Test1
    assert.equal(passwordValidationMessage('Test\n123'), PASSWORD_MESSAGES.control);
    assert.equal(passwordValidationMessage('Test\r123'), PASSWORD_MESSAGES.control);
    assert.equal(passwordValidationMessage('Test 123'), null); // an internal space is ordinary
  });

  test('every control character is refused with the generic message, before any request', async () => {
    assert.equal(PASSWORD_MESSAGES.control, 'Password cannot contain hidden control characters.');
    for (const password of CONTROL_PASSWORDS) {
      assert.equal(hasControlCharacter(password), true, JSON.stringify(password));
      const { calls, fetchImpl } = fakeFetch(201, { status: 'registered' });
      const result = await registerThroughBackend('http://localhost:8000', { ...FORM, password }, fetchImpl);
      assert.deepEqual(result, { ok: false, message: PASSWORD_MESSAGES.control }, JSON.stringify(password));
      assert.equal(calls.length, 0, 'no registration request');
      assert.ok(!result.message.includes(password) && !result.message.includes('Test'));
    }
  });

  test('every code point in category Cc is refused, and its printable neighbours are not', () => {
    for (let code = 0x00; code <= 0x1f; code += 1) {
      assert.equal(hasControlCharacter(`Test${String.fromCodePoint(code)}12`), true, code.toString(16));
    }
    for (let code = 0x7f; code <= 0x9f; code += 1) {
      assert.equal(hasControlCharacter(`Test${String.fromCodePoint(code)}12`), true, code.toString(16));
    }
    for (const neighbour of [' ', '~', ' ', '¡']) {
      assert.equal(passwordValidationMessage(`Test${neighbour}12`), null, JSON.stringify(neighbour));
    }
  });

  test('control characters are refused even when the length is also wrong, with the control message', () => {
    assert.equal(passwordValidationMessage('\tTest'), PASSWORD_MESSAGES.control); // 5 characters
    assert.equal(passwordValidationMessage(`\t${'a'.repeat(128)}`), PASSWORD_MESSAGES.control); // 129
  });

  test('128 and 129 characters', () => {
    assert.equal(passwordValidationMessage('a'.repeat(128)), null);
    assert.equal(passwordValidationMessage('a'.repeat(129)), PASSWORD_MESSAGES.length);
  });
});

describe('registrationResult', () => {
  test('only 201 is success', () => {
    assert.equal(registrationResult(201, { status: 'registered' }).ok, true);
    for (const status of [200, 202, 204, 400, 401, 403, 409, 422, 429, 500, 503]) {
      assert.equal(registrationResult(status, { status: 'registered' }).ok, false, `${status}`);
    }
  });

  test('invalid fields are named, never their values', () => {
    const { ok, message } = registrationResult(422, { code: 'INVALID_REGISTRATION', fields: ['email', 'password'] });
    assert.equal(ok, false);
    assert.equal(message, 'Please check your email address, password (6 to 128 characters).');
    assertNoInputEchoed(message);
  });

  test('unknown or missing field names give a general message', () => {
    const general = 'Please check the registration details and try again.';
    assert.equal(registrationResult(422, { fields: [FORM.password, '__proto__'] }).message, general);
    assert.equal(registrationResult(422, { fields: 'email' }).message, general);
    assert.equal(registrationResult(422, null).message, general);
  });

  test('a 409 without the expected code is not reported as an existing account', () => {
    assert.equal(registrationResult(409, null).message, REGISTRATION_MESSAGES.failed);
  });

  test('any other answer is a generic failure', () => {
    for (const [status, body] of [[500, { detail: FORM.email }], [400, null], [0, undefined]]) {
      assert.deepEqual(registrationResult(status, body), { ok: false, message: REGISTRATION_MESSAGES.failed });
    }
  });

  test('no message repeats the input', () => {
    for (const message of Object.values(REGISTRATION_MESSAGES)) assertNoInputEchoed(message);
  });
});
