# backend/tests/test_admin_users.py
"""
Milestone M3A: read-only Admin "Manage Users" endpoints.

Run from the backend directory:
    python -m unittest discover -s tests -t . -v

Safety: Firebase ID-token verification, Firebase Authentication (list_users /
get_user) and Firestore are replaced with in-memory fakes. No network, no
credentials and no real accounts are used. The fake Firestore has no write
methods, and every mutating Firebase Auth function is patched and asserted
unused, so any attempted write fails the tests.
"""
import contextlib
import importlib
import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

from routes import admin_users as admin_users_routes  # noqa: E402
from services import user_admin_service  # noqa: E402
from tests.test_auth import bearer, fake_verify_id_token  # noqa: E402

LIST_URL = "/api/admin/users"
ADMIN = bearer("admin-token")

SECRET_HASH = "SECRET-PASSWORD-HASH-VALUE"
SECRET_SALT = "SECRET-PASSWORD-SALT-VALUE"
SECRET_PHONE = "+60100000000"
SECRET_GRADE_SUBJECT = "SECRET-SUBJECT-NAME"
SECRET_GRADE = "SECRET-GRADE-VALUE"
SECRET_ANSWER = "SECRET-ASSESSMENT-ANSWER"
SECRET_SCORE_KEY = "SECRET-PATHWAY-SCORE"
SECRET_SNAPSHOT = "SECRET-ACADEMIC-SNAPSHOT"

LIST_ITEM_KEYS = {
    "uid", "email", "name", "student_type", "is_admin", "disabled", "email_verified",
    "created_at", "last_sign_in_at", "profile_status", "current_step",
}
LIST_RESPONSE_KEYS = {
    "items", "page", "page_size", "total", "total_pages", "complete", "account_limit", "scanned_accounts",
}
DETAIL_KEYS = {
    "uid", "email", "is_admin", "disabled", "email_verified", "created_at", "last_sign_in_at",
    "sign_in_providers", "profile", "records",
}


def millis(year, month, day):
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def make_account(uid, email, created, *, last_sign_in=None, disabled=False, verified=True, claims=None):
    """Stand-in for firebase_admin's ExportedUserRecord, including fields that must never leak."""
    return SimpleNamespace(
        uid=uid,
        email=email,
        email_verified=verified,
        disabled=disabled,
        custom_claims=claims,
        display_name="Display Name Not Used",
        phone_number=SECRET_PHONE,
        password_hash=SECRET_HASH,
        password_salt=SECRET_SALT,
        tokens_valid_after_timestamp=millis(2026, 1, 1),
        user_metadata=SimpleNamespace(creation_timestamp=created, last_sign_in_timestamp=last_sign_in),
        provider_data=[SimpleNamespace(provider_id="password", uid=f"provider-uid-{uid}", email=email)],
    )


def default_accounts():
    return [
        make_account("admin1", "admin@example.test", millis(2026, 1, 1), claims={"admin": True},
                     last_sign_in=millis(2026, 11, 20)),
        make_account("s_spm", "Aisyah@Example.test", millis(2026, 3, 1), last_sign_in=millis(2026, 11, 1)),
        make_account("s_form", "ben@example.test", millis(2026, 2, 1), disabled=True),
        make_account("s_legacy", "chong@example.test", millis(2025, 6, 1)),
        make_account("s_unknown", "dina@example.test", millis(2025, 5, 1)),
        make_account("s_missing", "evan@example.test", millis(2026, 4, 1), verified=False),
        make_account("s_stringclaim", "fatin@example.test", millis(2025, 4, 1), claims={"admin": "true"}),
    ]


def default_documents():
    created = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
    return {
        "users": {
            # The admin registered through the app, so the profile holds a STUDENT role.
            "admin1": {"name": "Site Admin", "email": "admin@example.test", "role": "spm_leaver", "createdAt": created},
            "s_spm": {
                "name": "Aisyah  Rahman", "email": "Aisyah@Example.test", "role": "spm_leaver", "createdAt": created,
                "updatedAt": datetime(2026, 3, 2, 9, 30, tzinfo=timezone.utc), "currentStep": 3,
                "chosenInterests": ["Computing & Digital Technology", "Engineering", "Extra ignored"],
                "hasCompletedProfile": True, "hasUploadedResults": True,
                "hasViewedRecommendations": False, "hasCompletedPreparationPlan": "yes",
            },
            "s_form": {"name": "Ben Lee", "email": "ben@example.test", "role": "form_4_5", "createdAt": created,
                       "currentStep": 9},
            "s_legacy": {"name": "Chong Wei", "email": "chong@example.test", "role": "upper_secondary",
                         "createdAt": created, "legacyNote": "older field"},
            # A user-editable role value must never grant Admin.
            "s_unknown": {"name": "Dina", "email": "dina@example.test", "role": "admin", "createdAt": created},
            "s_stringclaim": {"name": "Fatin", "email": "fatin@example.test", "role": "form_4_5", "createdAt": created},
        },
        "results": {
            "s_spm": {
                "userId": "s_spm", "email": "Aisyah@Example.test",
                "results": [{"subject": SECRET_GRADE_SUBJECT, "grade": SECRET_GRADE}, {"subject": "SEJARAH", "grade": "A"}],
                "updatedAt": datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
                "status": "manual_entry", "recordType": "PREDICTED_GRADES", "verificationMethod": "MANUAL_ENTRY",
            },
        },
        "ai_assessments": {
            "s_spm": {
                "userId": "s_spm", "userRole": "spm_leaver",
                "academicSnapshot": [{"subject": SECRET_SNAPSHOT, "grade": "A"}],
                "answers": [{"question": "Q1", "selectedOption": SECRET_ANSWER, "isCorrect": True}] * 10,
                "scoresByPathway": {SECRET_SCORE_KEY: 1},
                "completedAt": datetime(2026, 3, 6, 11, 0, tzinfo=timezone.utc),
                "isDemoMode": True,
            },
        },
    }


class FakeListPage:
    def __init__(self, pages, index=0):
        self._pages = pages
        self._index = index
        self.users = pages[index]

    def get_next_page(self):
        if self._index + 1 < len(self._pages):
            return FakeListPage(self._pages, self._index + 1)
        return None


class FakeSnapshot:
    def __init__(self, doc_id, data, field_paths):
        self.id = doc_id
        self.exists = data is not None
        self._data = data
        self._field_paths = field_paths

    def to_dict(self):
        if self._data is None:
            return None
        return {k: v for k, v in self._data.items() if self._field_paths is None or k in self._field_paths}


class FakeDocumentRef:
    def __init__(self, store, collection, doc_id):
        self._store = store
        self._collection = collection
        self.id = doc_id

    def get(self, field_paths=None):
        self._store.reads.append((self._collection, self.id, tuple(field_paths) if field_paths else None))
        data = self._store.data.get(self._collection, {}).get(self.id)
        return FakeSnapshot(self.id, data, field_paths)


class FakeCollection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id):
        return FakeDocumentRef(self._store, self._name, doc_id)


class FakeFirestore:
    """Read-only in-memory Firestore: there are no set/update/delete/batch methods."""

    def __init__(self, data):
        self.data = data
        self.reads = []
        self.get_all_calls = []

    def collection(self, name):
        return FakeCollection(self, name)

    def get_all(self, refs, field_paths=None):
        refs = list(refs)
        self.get_all_calls.append((len(refs), tuple(field_paths) if field_paths else None))
        for ref in refs:
            yield ref.get(field_paths)


class AdminUsersTestBase(unittest.TestCase):
    """Test app with the real router; Firebase Auth and Firestore replaced by fakes."""

    def setUp(self):
        app = FastAPI()
        app.include_router(admin_users_routes.router, prefix="/api/admin/users")
        self.client = TestClient(app)

        self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_verify_id_token)
        self.patch("core.auth._ensure_firebase_app")  # never load the service account

        self.accounts = default_accounts()
        self.auth_pages = None  # set to a list of pages to simulate multi-page listings
        self.firestore = FakeFirestore(default_documents())
        self.get_db = self.patch("services.user_admin_service._get_db", return_value=self.firestore)
        self.list_users = self.patch("services.user_admin_service.firebase_auth.list_users",
                                     side_effect=self._list_users)
        self.get_user = self.patch("services.user_admin_service.firebase_auth.get_user",
                                   side_effect=self._get_user)
        # Mutating Admin SDK functions must never be used by M3A.
        self.mutations = {
            name: self.patch(f"services.user_admin_service.firebase_auth.{name}")
            for name in ("update_user", "delete_user", "delete_users", "set_custom_user_claims",
                         "revoke_refresh_tokens", "create_user")
        }

    def tearDown(self):
        for name, mocked in self.mutations.items():
            self.assertFalse(mocked.called, f"M3A must not call firebase_admin.auth.{name}")

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def _list_users(self, **_kwargs):
        return FakeListPage(self.auth_pages or [self.accounts])

    def _get_user(self, uid, **_kwargs):
        for account in self.accounts:
            if account.uid == uid:
                return account
        raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")

    def list(self, headers=ADMIN, **params):
        return self.client.get(LIST_URL, params=params, headers=headers)

    def detail(self, uid, headers=ADMIN):
        return self.client.get(f"{LIST_URL}/{uid}", headers=headers)

    def assert_no_sdk_access(self):
        self.get_db.assert_not_called()
        self.list_users.assert_not_called()
        self.get_user.assert_not_called()
        self.assertEqual(self.firestore.reads, [])

    def uids(self, response):
        return [item["uid"] for item in response.json()["items"]]


class AuthorizationTests(AdminUsersTestBase):
    def test_missing_token_returns_401_without_sdk_access(self):
        for response in (self.client.get(LIST_URL), self.client.get(f"{LIST_URL}/s_spm")):
            self.assertEqual(response.status_code, 401)
        self.assert_no_sdk_access()

    def test_invalid_expired_and_revoked_tokens_return_401(self):
        for token in ("garbage-token", "expired-token", "revoked-token", "deleted-user-token"):
            with self.subTest(token=token):
                self.assertEqual(self.list(headers=bearer(token)).status_code, 401)
                self.assertEqual(self.detail("s_spm", headers=bearer(token)).status_code, 401)
        self.assert_no_sdk_access()

    def test_student_is_denied_with_403(self):
        self.assertEqual(self.list(headers=bearer("student-token")).status_code, 403)
        self.assertEqual(self.detail("s_spm", headers=bearer("student-token")).status_code, 403)
        self.assert_no_sdk_access()

    def test_non_boolean_or_false_admin_claims_are_denied(self):
        for token in ("string-admin-token", "false-admin-token"):
            with self.subTest(token=token):
                self.assertEqual(self.list(headers=bearer(token)).status_code, 403)
                self.assertEqual(self.detail("s_spm", headers=bearer(token)).status_code, 403)
        self.assert_no_sdk_access()

    def test_sign_in_service_outage_returns_coded_503_without_sdk_access(self):
        response = self.list(headers=bearer("lookup-unavailable-token"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "AUTH_SERVICE_UNAVAILABLE")
        self.assert_no_sdk_access()

    def test_invalid_parameters_are_rejected_before_any_sdk_access(self):
        response = self.client.get(LIST_URL, params={"page": 0})
        self.assertEqual(response.status_code, 401)  # authentication is checked first
        self.assert_no_sdk_access()


class ListTests(AdminUsersTestBase):
    def test_default_listing_is_newest_first_with_page_metadata(self):
        response = self.list()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), LIST_RESPONSE_KEYS)
        self.assertEqual(self.uids(response),
                         ["s_missing", "s_spm", "s_form", "admin1", "s_legacy", "s_unknown", "s_stringclaim"])
        self.assertEqual((body["page"], body["page_size"], body["total"], body["total_pages"]), (1, 20, 7, 1))
        self.assertEqual((body["complete"], body["account_limit"], body["scanned_accounts"]), (True, 2000, 7))

    def test_admin_status_comes_from_custom_claims_not_the_profile_role(self):
        items = {item["uid"]: item for item in self.list().json()["items"]}
        self.assertTrue(items["admin1"]["is_admin"])
        self.assertEqual(items["admin1"]["student_type"], "spm_leaver")  # profile role does not matter
        self.assertFalse(items["s_unknown"]["is_admin"])  # profile role "admin" grants nothing
        self.assertFalse(items["s_stringclaim"]["is_admin"])  # claim "true" (string) is not admin
        self.assertEqual(sum(item["is_admin"] for item in items.values()), 1)

    def test_auth_accounts_without_a_profile_are_reported_as_missing(self):
        items = {item["uid"]: item for item in self.list().json()["items"]}
        missing = items["s_missing"]
        self.assertEqual(missing["profile_status"], "missing")
        self.assertIsNone(missing["student_type"])
        self.assertIsNone(missing["name"])
        self.assertIsNone(missing["current_step"])
        self.assertEqual(items["s_spm"]["profile_status"], "present")

    def test_student_types_include_legacy_and_unknown_roles(self):
        items = {item["uid"]: item for item in self.list().json()["items"]}
        self.assertEqual(items["s_spm"]["student_type"], "spm_leaver")
        self.assertEqual(items["s_form"]["student_type"], "form_4_5")
        self.assertEqual(items["s_legacy"]["student_type"], "legacy")
        self.assertEqual(items["s_unknown"]["student_type"], "unknown")

    def test_list_values_are_cleaned(self):
        items = {item["uid"]: item for item in self.list().json()["items"]}
        self.assertEqual(items["s_spm"]["name"], "Aisyah Rahman")  # whitespace collapsed
        self.assertEqual(items["s_spm"]["current_step"], 3)
        self.assertIsNone(items["s_form"]["current_step"])  # out-of-range value dropped
        self.assertEqual(items["s_spm"]["created_at"], "2026-03-01T00:00:00Z")
        self.assertIsNone(items["s_form"]["last_sign_in_at"])
        self.assertTrue(items["s_form"]["disabled"])
        self.assertFalse(items["s_missing"]["email_verified"])

    def test_search_matches_email_and_name_case_insensitively(self):
        self.assertEqual(self.uids(self.list(search="aisyah@example")), ["s_spm"])
        self.assertEqual(self.uids(self.list(search="  CHONG   wei ")), ["s_legacy"])
        self.assertEqual(self.uids(self.list(search="aisyah rahman")), ["s_spm"])
        self.assertEqual(self.uids(self.list(search="example.test")), self.uids(self.list()))

    def test_search_without_matches_returns_an_empty_page(self):
        body = self.list(search="nobody-matches-this").json()
        self.assertEqual((body["items"], body["total"], body["total_pages"]), ([], 0, 1))

    def test_student_type_status_and_profile_filters(self):
        self.assertEqual(set(self.uids(self.list(student_type="spm_leaver"))), {"s_spm", "admin1"})
        self.assertEqual(set(self.uids(self.list(student_type="form_4_5"))), {"s_form", "s_stringclaim"})
        self.assertEqual(self.uids(self.list(student_type="legacy")), ["s_legacy"])
        self.assertEqual(self.uids(self.list(student_type="unknown")), ["s_unknown"])
        self.assertEqual(self.uids(self.list(status="disabled")), ["s_form"])
        self.assertNotIn("s_form", self.uids(self.list(status="active")))
        self.assertEqual(self.uids(self.list(profile="missing")), ["s_missing"])
        self.assertNotIn("s_missing", self.uids(self.list(profile="present")))
        self.assertEqual(self.uids(self.list(student_type="form_4_5", status="active")), ["s_stringclaim"])
        self.assertEqual(self.uids(self.list(student_type="form_4_5", status="disabled", search="ben")), ["s_form"])

    def test_pagination_is_stable_and_bounded(self):
        self.accounts.append(make_account("s_tie", "tie@example.test", millis(2026, 3, 1)))  # same date as s_spm
        first = self.list(page_size=2).json()
        second = self.list(page_size=2, page=2).json()
        last = self.list(page_size=2, page=4).json()
        self.assertEqual([i["uid"] for i in first["items"]], ["s_missing", "s_spm"])
        self.assertEqual([i["uid"] for i in second["items"]], ["s_tie", "s_form"])  # tie broken by uid
        self.assertEqual([i["uid"] for i in last["items"]], ["s_unknown", "s_stringclaim"])
        self.assertEqual((first["total"], first["total_pages"]), (8, 4))
        self.assertEqual(self.list(page_size=50).json()["page_size"], 50)

    def test_page_beyond_the_last_returns_no_items(self):
        body = self.list(page=99).json()
        self.assertEqual((body["items"], body["page"], body["total"]), ([], 99, 7))

    def test_invalid_query_parameters_are_rejected_with_422(self):
        cases = [
            {"page": 0}, {"page": -1}, {"page": "x"}, {"page_size": 0}, {"page_size": 51},
            {"student_type": "admin"}, {"status": "deleted"}, {"profile": "orphaned"},
            {"search": "x" * 101},
        ]
        for params in cases:
            with self.subTest(params=params):
                self.assertEqual(self.list(**params).status_code, 422)
        self.assert_no_sdk_access()

    def test_more_accounts_than_the_limit_is_reported_not_hidden(self):
        self.patch("services.user_admin_service.ACCOUNT_LIMIT", new=3)
        self.auth_pages = [self.accounts[:4], self.accounts[4:]]
        body = self.list().json()
        self.assertFalse(body["complete"])
        self.assertEqual((body["account_limit"], body["scanned_accounts"]), (3, 3))
        self.assertLessEqual(body["total"], 3)

    def test_all_auth_pages_are_read_when_under_the_limit(self):
        self.auth_pages = [self.accounts[:2], self.accounts[2:5], self.accounts[5:]]
        body = self.list().json()
        self.assertTrue(body["complete"])
        self.assertEqual((body["scanned_accounts"], body["total"]), (7, 7))

    def test_profiles_are_read_in_batches_with_a_field_mask(self):
        self.patch("services.user_admin_service.FIRESTORE_BATCH_SIZE", new=3)
        self.list()
        self.assertEqual([size for size, _ in self.firestore.get_all_calls], [3, 3, 1])
        for _, field_paths in self.firestore.get_all_calls:
            self.assertEqual(field_paths, ("name", "role", "currentStep"))
        self.assertTrue(all(collection == "users" for collection, _, _ in self.firestore.reads))

    def test_list_items_contain_only_allow_listed_fields(self):
        for item in self.list().json()["items"]:
            self.assertEqual(set(item), LIST_ITEM_KEYS)

    def test_list_never_leaks_credentials_claims_or_provider_data(self):
        text = self.list().text
        for secret in (SECRET_HASH, SECRET_SALT, SECRET_PHONE, "provider-uid-", "custom_claims",
                       "password", "Display Name Not Used", "tokens_valid_after", "legacyNote", "older field"):
            self.assertNotIn(secret, text)

    def test_firebase_auth_failure_returns_safe_503(self):
        self.list_users.side_effect = firebase_exceptions.UnavailableError("SECRET backend detail admin@example.test")
        with self.assertLogs("user_admin_service", level="ERROR") as logs:
            response = self.list()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "USER_SERVICE_UNAVAILABLE")
        self.assertNotIn("SECRET", response.text)
        self.assertNotIn("SECRET", "\n".join(logs.output))
        self.assertNotIn("admin@example.test", "\n".join(logs.output))

    def test_firestore_failure_returns_safe_503(self):
        self.firestore.get_all = mock.Mock(side_effect=google_exceptions.ServiceUnavailable("SECRET firestore"))
        response = self.list()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "USER_SERVICE_UNAVAILABLE")
        self.assertNotIn("SECRET", response.text)

    def test_firebase_initialisation_failure_returns_safe_503(self):
        self.get_db.side_effect = FileNotFoundError("SECRET path to serviceAccountKey.json")
        response = self.list()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SECRET", response.text)
        self.assertNotIn("serviceAccountKey", response.text)


class DetailTests(AdminUsersTestBase):
    def test_detail_returns_account_profile_and_records_summary(self):
        response = self.detail("s_spm")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), DETAIL_KEYS)
        self.assertEqual((body["uid"], body["email"], body["is_admin"], body["disabled"]),
                         ("s_spm", "Aisyah@Example.test", False, False))
        self.assertEqual(body["sign_in_providers"], ["password"])
        self.assertEqual(body["profile"], {
            "name": "Aisyah Rahman",
            "student_type": "spm_leaver",
            "registered_at": "2026-03-01T08:00:00Z",
            "updated_at": "2026-03-02T09:30:00Z",
            "current_step": 3,
            "chosen_interests": ["Computing & Digital Technology", "Engineering"],
            "progress": {
                "has_completed_profile": True,
                "has_uploaded_results": True,
                "has_viewed_recommendations": False,
                "has_completed_preparation_plan": None,  # non-boolean stored value dropped
            },
        })
        self.assertEqual(body["records"], {
            "results": {
                "exists": True, "record_type": "PREDICTED_GRADES", "status": "manual_entry",
                "verification_method": "MANUAL_ENTRY", "subject_count": 2, "updated_at": "2026-03-05T10:00:00Z",
            },
            "ai_assessment": {
                "exists": True, "question_count": 10, "completed_at": "2026-03-06T11:00:00Z", "is_demo_mode": True,
            },
        })

    def test_detail_never_returns_grades_answers_scores_or_credentials(self):
        text = self.detail("s_spm").text
        for secret in (SECRET_GRADE_SUBJECT, SECRET_GRADE, SECRET_ANSWER, SECRET_SCORE_KEY, SECRET_SNAPSHOT,
                       SECRET_HASH, SECRET_SALT, SECRET_PHONE, "provider-uid-", "custom_claims",
                       "academicSnapshot", "scoresByPathway", "selectedOption"):
            self.assertNotIn(secret, text)

    def test_detail_admin_status_comes_from_claims(self):
        self.assertTrue(self.detail("admin1").json()["is_admin"])
        self.assertFalse(self.detail("s_unknown").json()["is_admin"])
        self.assertFalse(self.detail("s_stringclaim").json()["is_admin"])

    def test_detail_for_an_account_without_profile_or_records(self):
        body = self.detail("s_missing").json()
        self.assertIsNone(body["profile"])
        self.assertEqual(body["records"], {
            "results": {"exists": False, "record_type": None, "status": None, "verification_method": None,
                        "subject_count": None, "updated_at": None},
            "ai_assessment": {"exists": False, "question_count": None, "completed_at": None, "is_demo_mode": None},
        })

    def test_detail_handles_legacy_roles(self):
        self.assertEqual(self.detail("s_legacy").json()["profile"]["student_type"], "legacy")

    def test_unknown_user_returns_coded_404(self):
        response = self.detail("no_such_user")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "USER_NOT_FOUND")

    def test_invalid_uid_is_rejected_without_sdk_access(self):
        for uid in ("bad uid", "x.y", "a" * 129, "semi;colon"):
            with self.subTest(uid=uid):
                self.assertEqual(self.detail(uid).status_code, 422)
        self.assert_no_sdk_access()

    def test_detail_reads_use_field_masks(self):
        self.detail("s_spm")
        reads = {collection: field_paths for collection, _, field_paths in self.firestore.reads}
        self.assertEqual(reads["users"], tuple(user_admin_service.DETAIL_PROFILE_FIELDS))
        self.assertEqual(reads["results"], tuple(user_admin_service.RESULTS_SUMMARY_FIELDS))
        self.assertEqual(reads["ai_assessments"], tuple(user_admin_service.ASSESSMENT_SUMMARY_FIELDS))
        self.assertNotIn("academicSnapshot", reads["ai_assessments"])
        self.assertNotIn("scoresByPathway", reads["ai_assessments"])

    def test_firebase_auth_failure_returns_safe_503(self):
        self.get_user.side_effect = firebase_exceptions.UnavailableError("SECRET lookup failure")
        response = self.detail("s_spm")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "USER_SERVICE_UNAVAILABLE")
        self.assertNotIn("SECRET", response.text)

    def test_firestore_failure_returns_safe_503(self):
        def failing_collection(_name):
            raise google_exceptions.ServiceUnavailable("SECRET firestore detail")

        self.firestore.collection = failing_collection
        response = self.detail("s_spm")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SECRET", response.text)


class MainAppWiringTests(unittest.TestCase):
    """The real `main.app` exposes the M3A routes, and they require authentication."""

    @classmethod
    def setUpClass(cls):
        sys.modules.pop("main", None)
        with mock.patch("core.firebase.initialize_firebase", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            main = importlib.import_module("main")
        cls.app = main.app
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("main", None)

    def admin_user_paths(self):
        paths = self.app.openapi()["paths"]
        return {path: set(operations) for path, operations in paths.items() if path.startswith("/api/admin/users")}

    def test_routes_are_registered_and_require_authentication(self):
        self.assertEqual(set(self.admin_user_paths()), {"/api/admin/users", "/api/admin/users/{uid}"})
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)
        self.assertEqual(self.client.get(f"{LIST_URL}/s_spm").status_code, 401)

    def test_only_read_methods_are_exposed(self):
        for path, methods in self.admin_user_paths().items():
            self.assertEqual(methods, {"get"}, path)
        for method in ("post", "put", "patch", "delete"):
            response = self.client.request(method.upper(), f"{LIST_URL}/s_spm")
            self.assertEqual(response.status_code, 405, method)


if __name__ == "__main__":
    unittest.main()
