// frontend/src/utils/gradeEntry.test.js
//
// Tests for the shared grade-entry rules used by UploadResults.jsx (SPM leavers)
// and ManualGradeEntry.jsx (Form 4/5). Synthetic data only: no browser, no Firebase,
// no network. Uses Node's built-in test runner (no extra dependencies).
//
// Run from the frontend folder:
//   node --test src/utils/gradeEntry.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MIN_REQUIREMENTS,
  MAX_SUBJECTS,
  VALID_GRADES,
  createBaseRows,
  validateGradeRows,
} from './gradeEntry.js';

const ALL_VALID_GRADES = ['A+', 'A', 'A-', 'B+', 'B', 'C+', 'C', 'D', 'E', 'G'];

// The four compulsory rows with valid grades.
const compulsory = (bm = 'A', bi = 'B+', math = 'A-', sejarah = 'C') => [
  { subject: 'BAHASA MELAYU', grade: bm },
  { subject: 'BAHASA INGGERIS', grade: bi },
  { subject: 'MATEMATIK', grade: math },
  { subject: 'SEJARAH', grade: sejarah },
];

const electives = (count) =>
  Array.from({ length: count }, (_, i) => ({ subject: `ELECTIVE ${i + 1}`, grade: 'B' }));

describe('shared constants', () => {
  test('accepted grades are exactly the 10 SPM grades', () => {
    assert.deepEqual([...VALID_GRADES], ALL_VALID_GRADES);
    assert.ok(Object.isFrozen(VALID_GRADES));
  });

  test('maximum matches the firestore.rules limit of 20 results', () => {
    assert.equal(MAX_SUBJECTS, 20);
  });

  test('compulsory template rows are BM, BI, Matematik and Sejarah with empty grades', () => {
    assert.deepEqual(
      MIN_REQUIREMENTS.map((r) => r.subject),
      ['BAHASA MELAYU', 'BAHASA INGGERIS', 'MATEMATIK', 'SEJARAH']
    );
    assert.ok(MIN_REQUIREMENTS.every((r) => r.grade === ''));
  });
});

describe('createBaseRows', () => {
  test('returns fresh, independent objects on every call', () => {
    const first = createBaseRows();
    const second = createBaseRows();
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    first.forEach((row, i) => assert.notEqual(row, second[i]));
    first.forEach((row, i) => assert.notEqual(row, MIN_REQUIREMENTS[i]));
  });

  test('editing returned rows never changes the shared template', () => {
    const rows = createBaseRows();
    rows[0].grade = 'A';
    rows.push({ subject: 'FIZIK', grade: 'B' });
    assert.equal(MIN_REQUIREMENTS[0].grade, '');
    assert.equal(MIN_REQUIREMENTS.length, 4);
    assert.equal(createBaseRows()[0].grade, '');
  });

  test('the shared template itself cannot be modified', () => {
    assert.ok(Object.isFrozen(MIN_REQUIREMENTS));
    assert.ok(MIN_REQUIREMENTS.every((row) => Object.isFrozen(row)));
    assert.throws(() => { MIN_REQUIREMENTS[0].grade = 'A'; }, TypeError);
  });
});

describe('validateGradeRows', () => {
  test('all 10 valid SPM grades are accepted in compulsory and elective rows', () => {
    for (const grade of ALL_VALID_GRADES) {
      const result = validateGradeRows([...compulsory(grade), { subject: 'FIZIK', grade }]);
      assert.equal(result.error, undefined, `grade ${grade}`);
      assert.equal(result.results.length, 5);
    }
  });

  test('invalid grades are rejected, including F, A++, B- and TH', () => {
    for (const bad of ['F', 'A++', 'B-', 'TH', 'C-', 'E+', 'AA', '1']) {
      const inCompulsory = validateGradeRows(compulsory(bad));
      assert.match(inCompulsory.error, /^Invalid grade for BAHASA MELAYU \(/, `compulsory ${bad}`);
      assert.equal(inCompulsory.results, undefined);

      const inElective = validateGradeRows([...compulsory(), { subject: 'KIMIA', grade: bad }]);
      assert.match(inElective.error, /^Invalid grade for KIMIA \(/, `elective ${bad}`);
      assert.match(inElective.error, /Please use one of: A\+, A, A-, B\+, B, C\+, C, D, E, G\.$/);
    }
  });

  test('a missing compulsory grade is rejected', () => {
    for (let i = 0; i < 4; i += 1) {
      const rows = compulsory();
      rows[i] = { ...rows[i], grade: '  ' };
      assert.equal(validateGradeRows(rows).error, 'Please ensure BM, BI, Math, and Sejarah have grades.');
    }
  });

  test('an elective subject without a grade is rejected, not discarded', () => {
    const result = validateGradeRows([...compulsory(), { subject: 'FIZIK', grade: '' }]);
    assert.match(result.error, /^Each elective needs both a subject and a grade\./);
    assert.match(result.error, /FIZIK \(missing grade\)/);
    assert.equal(result.results, undefined);
  });

  test('an elective grade without a subject is rejected and identifies the row', () => {
    const result = validateGradeRows([...compulsory(), { subject: '', grade: '' }, { subject: '  ', grade: 'A' }]);
    assert.match(result.error, /row 6 \(missing subject\)/);
    assert.equal(result.results, undefined);
  });

  test('completely empty elective rows are ignored', () => {
    const result = validateGradeRows([
      ...compulsory(),
      { subject: '', grade: '' },
      { subject: 'BIOLOGI', grade: 'B' },
      { subject: '   ', grade: ' ' },
    ]);
    assert.equal(result.error, undefined);
    assert.equal(result.results.length, 5);
    assert.deepEqual(result.results[4], { subject: 'BIOLOGI', grade: 'B' });
  });

  test('surrounding whitespace is trimmed from subjects and grades', () => {
    const result = validateGradeRows([...compulsory(' A ', 'B', 'A', 'A'), { subject: '  FIZIK ', grade: ' B+' }]);
    assert.equal(result.error, undefined);
    assert.deepEqual(result.results[0], { subject: 'BAHASA MELAYU', grade: 'A' });
    assert.deepEqual(result.results[4], { subject: 'FIZIK', grade: 'B+' });
  });

  test('exactly 20 subjects are accepted', () => {
    const result = validateGradeRows([...compulsory(), ...electives(16)]);
    assert.equal(result.error, undefined);
    assert.equal(result.results.length, 20);
  });

  test('a 21st subject is rejected with a clear message', () => {
    const result = validateGradeRows([...compulsory(), ...electives(17)]);
    assert.equal(result.error, 'You can save up to 20 subjects. Please clear 1 subject row(s) and try again.');
    assert.equal(result.results, undefined);
  });

  test('Matematik and Matematik Tambahan stay separate entries', () => {
    const result = validateGradeRows([...compulsory('A', 'A', 'B', 'A'), { subject: 'MATEMATIK TAMBAHAN', grade: 'C+' }]);
    assert.deepEqual(
      result.results.filter((r) => r.subject.startsWith('MATEMATIK')),
      [{ subject: 'MATEMATIK', grade: 'B' }, { subject: 'MATEMATIK TAMBAHAN', grade: 'C+' }]
    );
  });

  test('input rows are not mutated', () => {
    const rows = [...compulsory(' A '), { subject: ' FIZIK ', grade: 'B' }, { subject: '', grade: '' }];
    const snapshot = JSON.stringify(rows);
    validateGradeRows(rows);
    assert.equal(JSON.stringify(rows), snapshot);
  });

  test('results are new {subject, grade} objects ready for the results document', () => {
    const rows = [
      ...compulsory(),
      { subject: 'FIZIK', grade: 'B', extra: 'not saved' },
    ];
    const { results } = validateGradeRows(rows);
    assert.equal(results.length, 5);
    for (const entry of results) {
      assert.deepEqual(Object.keys(entry).sort(), ['grade', 'subject']);
      assert.equal(typeof entry.subject, 'string');
      assert.equal(typeof entry.grade, 'string');
    }
    results.forEach((entry, i) => assert.notEqual(entry, rows[i]));
  });
});
