// frontend/src/utils/firebaseEmulator.test.js
//
// The browser may use the Firebase emulators only in the Vite dev server with
// VITE_USE_FIREBASE_EMULATORS=true, and then never with a production configuration value.
// Pure functions only: no browser, Firebase or network. Run from the frontend folder:
//   node --test src/utils/firebaseEmulator.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  AUTH_EMULATOR_URL,
  EMULATOR_PROJECT_ID,
  FIRESTORE_EMULATOR_HOST,
  FIRESTORE_EMULATOR_PORT,
  emulatorFirebaseConfig,
  firebaseSetup,
  productionFirebaseConfig,
  shouldUseEmulators,
} from './firebaseEmulator.js';

// Placeholder values only; never real configuration.
const PRODUCTION_ENV = {
  VITE_FIREBASE_API_KEY: 'production-api-key-placeholder',
  VITE_FIREBASE_AUTH_DOMAIN: 'production.example.test',
  VITE_FIREBASE_PROJECT_ID: 'production-project-placeholder',
  VITE_FIREBASE_STORAGE_BUCKET: 'production-bucket-placeholder',
  VITE_FIREBASE_MESSAGING_SENDER_ID: 'production-sender-placeholder',
  VITE_FIREBASE_APP_ID: 'production-app-id-placeholder',
};

describe('shouldUseEmulators', () => {
  test('only the dev server with the flag set to exactly "true"', () => {
    assert.equal(shouldUseEmulators({ DEV: true, VITE_USE_FIREBASE_EMULATORS: 'true' }), true);
  });

  test('a production build never uses the emulators, even with the flag', () => {
    assert.equal(shouldUseEmulators({ DEV: false, VITE_USE_FIREBASE_EMULATORS: 'true' }), false);
    assert.equal(shouldUseEmulators({ VITE_USE_FIREBASE_EMULATORS: 'true' }), false);
    assert.equal(shouldUseEmulators({ DEV: 'true', VITE_USE_FIREBASE_EMULATORS: 'true' }), false);
  });

  test('the dev server without the exact flag uses the real configuration', () => {
    for (const flag of [undefined, '', 'false', 'TRUE', 'True', '1', 'yes', ' true', true]) {
      assert.equal(shouldUseEmulators({ DEV: true, VITE_USE_FIREBASE_EMULATORS: flag }), false, String(flag));
    }
  });

  test('a missing environment is not emulator mode', () => {
    assert.equal(shouldUseEmulators(undefined), false);
    assert.equal(shouldUseEmulators({}), false);
  });
});

describe('emulator configuration', () => {
  test('uses the demo project and no production value', () => {
    const config = emulatorFirebaseConfig();
    assert.equal(EMULATOR_PROJECT_ID, 'demo-route2unikl');
    assert.equal(config.projectId, EMULATOR_PROJECT_ID);
    assert.ok(config.projectId.startsWith('demo-'));
    assert.notEqual(config.projectId, 'route2unikl');
    for (const value of Object.values(config)) {
      assert.ok(!Object.values(PRODUCTION_ENV).includes(value), value);
      assert.ok(!String(value).includes('route2unikl') || String(value).includes('demo-route2unikl'), value);
    }
    assert.equal(config.storageBucket, undefined);
    assert.equal(config.messagingSenderId, undefined);
  });

  test('emulator hosts are loopback and match firebase.json', () => {
    assert.equal(AUTH_EMULATOR_URL, 'http://127.0.0.1:9099');
    assert.equal(FIRESTORE_EMULATOR_HOST, '127.0.0.1');
    assert.equal(FIRESTORE_EMULATOR_PORT, 8080);
  });
});

describe('firebaseSetup', () => {
  test('emulator mode ignores every production value', () => {
    const { useEmulators, config } = firebaseSetup({ DEV: true, VITE_USE_FIREBASE_EMULATORS: 'true', ...PRODUCTION_ENV });
    assert.equal(useEmulators, true);
    assert.deepEqual(config, emulatorFirebaseConfig());
  });

  test('otherwise the production configuration passes through unchanged', () => {
    for (const env of [{ DEV: false, ...PRODUCTION_ENV }, { DEV: true, ...PRODUCTION_ENV },
      { DEV: false, VITE_USE_FIREBASE_EMULATORS: 'true', ...PRODUCTION_ENV }]) {
      const { useEmulators, config } = firebaseSetup(env);
      assert.equal(useEmulators, false);
      assert.deepEqual(config, {
        apiKey: PRODUCTION_ENV.VITE_FIREBASE_API_KEY,
        authDomain: PRODUCTION_ENV.VITE_FIREBASE_AUTH_DOMAIN,
        projectId: PRODUCTION_ENV.VITE_FIREBASE_PROJECT_ID,
        storageBucket: PRODUCTION_ENV.VITE_FIREBASE_STORAGE_BUCKET,
        messagingSenderId: PRODUCTION_ENV.VITE_FIREBASE_MESSAGING_SENDER_ID,
        appId: PRODUCTION_ENV.VITE_FIREBASE_APP_ID,
      });
      assert.deepEqual(config, productionFirebaseConfig(env));
    }
  });
});
