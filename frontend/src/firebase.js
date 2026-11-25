// frontend/src/firebase.js
import { initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth } from "firebase/auth";
import { connectFirestoreEmulator, getFirestore } from "firebase/firestore";
import {
  AUTH_EMULATOR_URL,
  FIRESTORE_EMULATOR_HOST,
  FIRESTORE_EMULATOR_PORT,
  firebaseSetup,
} from "./utils/firebaseEmulator";

// Production: the web app's Firebase configuration from .env (unchanged).
// Local development: the Firebase emulators, only in the dev server with VITE_USE_FIREBASE_EMULATORS=true
// (see utils/firebaseEmulator.js). Each variable is read by name so a build inlines only these.
const { useEmulators, config } = firebaseSetup({
  DEV: import.meta.env.DEV,
  VITE_USE_FIREBASE_EMULATORS: import.meta.env.VITE_USE_FIREBASE_EMULATORS,
  VITE_FIREBASE_API_KEY: import.meta.env.VITE_FIREBASE_API_KEY,
  VITE_FIREBASE_AUTH_DOMAIN: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  VITE_FIREBASE_PROJECT_ID: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  VITE_FIREBASE_STORAGE_BUCKET: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  VITE_FIREBASE_MESSAGING_SENDER_ID: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  VITE_FIREBASE_APP_ID: import.meta.env.VITE_FIREBASE_APP_ID,
});

// Initialize Firebase
const app = initializeApp(config);
const auth = getAuth(app);
const db = getFirestore(app);

// Connect to the emulators before anything uses the clients. The Firebase SDK then shows its
// "Running in emulator mode" banner, a visible sign that production is not in use.
if (useEmulators) {
  connectAuthEmulator(auth, AUTH_EMULATOR_URL);
  connectFirestoreEmulator(db, FIRESTORE_EMULATOR_HOST, FIRESTORE_EMULATOR_PORT);
}

//export
export { auth, db, useEmulators };
