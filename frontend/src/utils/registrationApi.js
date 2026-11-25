// frontend/src/utils/registrationApi.js
//
// Trusted backend registration (M3B-1B-P1-B2A/B), used by Register.jsx only with the local Firebase
// emulators. The backend creates the account, the student profile and the account-access record. The
// password travels only in this request body; it is never stored or logged here, and no message below
// repeats anything the student typed. The password rule below is shared by both registration paths.

export const REGISTRATION_PATH = '/api/account/register';

// The backend's password rule (registration_service.validate_registration), checked here too so an invalid
// password is refused before any registration request, on both registration paths: 6 to 128 characters,
// counted in Unicode code points as the backend counts them, and no control characters (Unicode category
// Cc: TAB, line feed, carriage return, DEL and the others), which cannot be seen in a password field. The
// password is never trimmed, normalised or otherwise changed.
export const PASSWORD_MIN_LENGTH = 6;
export const PASSWORD_MAX_LENGTH = 128;

export const PASSWORD_MESSAGES = {
  length: 'Please check your password (6 to 128 characters).',
  control: 'Password cannot contain hidden control characters.',
};

const CONTROL_CHARACTER = /\p{Cc}/u;

export const isPasswordLengthValid = (password) => {
  if (typeof password !== 'string') return false;
  const length = Array.from(password).length;
  return length >= PASSWORD_MIN_LENGTH && length <= PASSWORD_MAX_LENGTH;
};

export const hasControlCharacter = (password) => typeof password === 'string' && CONTROL_CHARACTER.test(password);

/** The message for an invalid password, or null if it is valid. Never includes the password. */
export const passwordValidationMessage = (password) => {
  if (hasControlCharacter(password)) return PASSWORD_MESSAGES.control;
  if (!isPasswordLengthValid(password)) return PASSWORD_MESSAGES.length;
  return null;
};

export const REGISTRATION_MESSAGES = {
  success: 'Registration Successful! Please login.',
  emailInUse: 'An account with this email already exists. Please log in, or reset your password.',
  incomplete: 'Your account could not be fully set up. Please contact the Route2UniKL administrator before trying again.',
  unavailable: 'Registration is temporarily unavailable. Please try again in a moment.',
  notAvailable: 'Registration is not available on this server.',
  tooLarge: 'The registration details are too long. Please shorten them and try again.',
  network: "We couldn't reach the Route2UniKL server. Please check your connection and try again.",
  failed: 'Registration failed. Please try again.',
};

const FIELD_LABELS = {
  name: 'full name',
  email: 'email address',
  password: 'password (6 to 128 characters)',
  role: 'student type',
};

const invalidMessage = (fields) => {
  const labels = (Array.isArray(fields) ? fields : [])
    .filter((field) => typeof field === 'string' && Object.hasOwn(FIELD_LABELS, field))
    .map((field) => FIELD_LABELS[field]);
  return labels.length
    ? `Please check your ${labels.join(', ')}.`
    : 'Please check the registration details and try again.';
};

/** Map the backend's answer to { ok, message } (codes only; never the submitted values). */
export const registrationResult = (status, body) => {
  const code = body?.code;
  if (status === 201) return { ok: true, message: REGISTRATION_MESSAGES.success };
  if (status === 409 && code === 'EMAIL_IN_USE') return { ok: false, message: REGISTRATION_MESSAGES.emailInUse };
  if (status === 422) return { ok: false, message: invalidMessage(body?.fields) };
  if (status === 503 && code === 'REGISTRATION_INCOMPLETE') return { ok: false, message: REGISTRATION_MESSAGES.incomplete };
  if (status === 503) return { ok: false, message: REGISTRATION_MESSAGES.unavailable };
  if (status === 404) return { ok: false, message: REGISTRATION_MESSAGES.notAvailable };
  if (status === 413) return { ok: false, message: REGISTRATION_MESSAGES.tooLarge };
  return { ok: false, message: REGISTRATION_MESSAGES.failed };
};

/** POST the registration to the backend; resolves to { ok, message } and never rejects. */
export const registerThroughBackend = async (baseUrl, { name, email, password, role }, fetchImpl = fetch) => {
  const passwordProblem = passwordValidationMessage(password);
  if (passwordProblem) {
    return { ok: false, message: passwordProblem };
  }
  let response;
  try {
    response = await fetchImpl(`${baseUrl}${REGISTRATION_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, role }),
    });
  } catch {
    return { ok: false, message: REGISTRATION_MESSAGES.network };
  }
  let body;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return registrationResult(response.status, body);
};
