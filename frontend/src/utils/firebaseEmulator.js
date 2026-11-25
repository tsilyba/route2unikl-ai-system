// frontend/src/utils/firebaseEmulator.js
//
// Local Firebase emulator settings (M3B-1B-P1-B2B/C). The browser uses the emulators ONLY in the Vite
// dev server (DEV) and ONLY when VITE_USE_FIREBASE_EMULATORS is exactly "true". A production build
// never does. In emulator mode the app uses the demo project and no production configuration value,
// so no request can reach the real Firebase project. Hosts match firebase.json (loopback only).
//
// Pass the individual variables (see firebase.js), never the whole import.meta.env object: a build
// inlines every VITE_* variable when the whole object is referenced.

export const EMULATOR_PROJECT_ID = 'demo-route2unikl';
export const AUTH_EMULATOR_URL = 'http://127.0.0.1:9099';
export const FIRESTORE_EMULATOR_HOST = '127.0.0.1';
export const FIRESTORE_EMULATOR_PORT = 8080;

export const shouldUseEmulators = (env) =>
  env?.DEV === true && env?.VITE_USE_FIREBASE_EMULATORS === 'true';

// The emulators accept any API key; nothing here identifies the production project.
export const emulatorFirebaseConfig = () => ({
  apiKey: 'demo-api-key',
  authDomain: `${EMULATOR_PROJECT_ID}.firebaseapp.com`,
  projectId: EMULATOR_PROJECT_ID,
  appId: 'demo-app-id',
});

export const productionFirebaseConfig = (env) => ({
  apiKey: env.VITE_FIREBASE_API_KEY,
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: env.VITE_FIREBASE_APP_ID,
});

export const firebaseSetup = (env) => {
  const useEmulators = shouldUseEmulators(env);
  return { useEmulators, config: useEmulators ? emulatorFirebaseConfig() : productionFirebaseConfig(env) };
};
