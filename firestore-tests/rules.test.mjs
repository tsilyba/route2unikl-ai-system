// firestore-tests/rules.test.mjs
//
// Route2UniKL - Firestore Security Rules tests: PRODUCTION rules baseline.
//
// Runs the original 44 regression tests (Milestone 1.5B, sections 1-12 in
// shared-rules-suite.mjs) against ../firestore.rules, the rules file that
// firebase.json deploys. Runs ONLY against the local Firestore emulator under
// the `demo-route2unikl` project ID (a "demo-" project can never reach production).
//
// Run from this folder:   npm test
// (requires the Firebase CLI and Java; see package.json)
//
// The experimental account-access guard (M3B-1B-P0) is NOT tested here: see
// account-access.experimental.suite.mjs, which loads a test-only rules file.

import { defineRegressionTests, setupRulesEnvironment } from './shared-rules-suite.mjs';

setupRulesEnvironment({ rulesFile: new URL('../firestore.rules', import.meta.url) });
defineRegressionTests();
