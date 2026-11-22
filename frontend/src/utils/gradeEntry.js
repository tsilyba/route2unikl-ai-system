// frontend/src/utils/gradeEntry.js
//
// Shared grade-entry rules for the SPM leaver page (pages/user/UploadResults.jsx)
// and the Form 4/5 page (pages/user/ManualGradeEntry.jsx).
//
// Plain JavaScript with no React or Firebase imports, so it can be tested with
// Node's built-in test runner (from the frontend folder):
//   node --test src/utils/gradeEntry.test.js
//
// This is browser-side data-quality validation, not a security control:
// firestore.rules checks the results document's shape and size (1-20 entries)
// but not the individual grades.

// Compulsory subjects shown as the first (fixed) rows. Frozen so that edits can
// never modify these shared template rows.
export const MIN_REQUIREMENTS = Object.freeze([
  Object.freeze({ subject: 'BAHASA MELAYU', grade: '' }),
  Object.freeze({ subject: 'BAHASA INGGERIS', grade: '' }),
  Object.freeze({ subject: 'MATEMATIK', grade: '' }),
  Object.freeze({ subject: 'SEJARAH', grade: '' }),
]);

// Fresh, independent row objects for every visit to a page.
export const createBaseRows = () => MIN_REQUIREMENTS.map((row) => ({ ...row }));

// firestore.rules accepts at most 20 entries in results/{uid}.results.
export const MAX_SUBJECTS = 20;

// SPM grades accepted on the grade-entry pages.
export const VALID_GRADES = Object.freeze(['A+', 'A', 'A-', 'B+', 'B', 'C+', 'C', 'D', 'E', 'G']);

// Checks the entered rows before saving. Returns { error } or { results }, where
// results is a new array of trimmed { subject, grade } objects. The input rows are
// not modified. Fully empty elective rows are ignored; partly filled rows are rejected.
export const validateGradeRows = (rows) => {
  const trimmed = rows.map((r) => ({ subject: r.subject.trim(), grade: r.grade.trim() }));

  if (trimmed.slice(0, MIN_REQUIREMENTS.length).some((r) => r.grade === '')) {
    return { error: "Please ensure BM, BI, Math, and Sejarah have grades." };
  }

  const incomplete = trimmed
    .map((r, i) => ({ ...r, rowNumber: i + 1 }))
    .filter((r) => r.rowNumber > MIN_REQUIREMENTS.length && (r.subject === '') !== (r.grade === ''))
    .map((r) => (r.subject ? `${r.subject} (missing grade)` : `row ${r.rowNumber} (missing subject)`));
  if (incomplete.length > 0) {
    return { error: `Each elective needs both a subject and a grade. Please complete or clear: ${incomplete.join(', ')}.` };
  }

  const filled = trimmed.filter((r) => r.subject !== '' && r.grade !== '');

  const invalid = filled.filter((r) => !VALID_GRADES.includes(r.grade));
  if (invalid.length > 0) {
    const list = invalid.map((r) => `${r.subject} (${r.grade})`).join(', ');
    return { error: `Invalid grade for ${list}. Please use one of: ${VALID_GRADES.join(', ')}.` };
  }

  if (filled.length > MAX_SUBJECTS) {
    const extra = filled.length - MAX_SUBJECTS;
    return { error: `You can save up to ${MAX_SUBJECTS} subjects. Please clear ${extra} subject row(s) and try again.` };
  }

  return { results: filled };
};
