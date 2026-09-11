import tempfile
import unittest
from pathlib import Path

from tools.build_orders.profiles import (
    ProfileResolutionError,
    resolve_datastore_path,
)


class BuildOrderProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.documents = Path(self.temporary.name)
        self.users = self.documents / "My Games" / "Age of Empires IV" / "Users"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_single_profile_is_selected_without_argument(self) -> None:
        (self.users / "76561198050151767").mkdir(parents=True)

        path = resolve_datastore_path(None, documents_dir=self.documents)

        self.assertEqual(
            path,
            self.users
            / "76561198050151767"
            / "datastore"
            / "macroTrainerBuildOrders.rlt",
        )

    def test_multiple_profiles_require_explicit_id_and_list_candidates(self) -> None:
        (self.users / "222").mkdir(parents=True)
        (self.users / "111").mkdir()

        with self.assertRaisesRegex(
            ProfileResolutionError, r"multiple AoE4 profiles.*111, 222.*--profile"
        ):
            resolve_datastore_path(None, documents_dir=self.documents)

    def test_no_profiles_requires_explicit_id(self) -> None:
        self.users.mkdir(parents=True)

        with self.assertRaisesRegex(
            ProfileResolutionError, r"no AoE4 profiles.*--profile"
        ):
            resolve_datastore_path(None, documents_dir=self.documents)

    def test_explicit_new_profile_resolves_without_creating_directories(self) -> None:
        path = resolve_datastore_path("999", documents_dir=self.documents)

        self.assertEqual(
            path,
            self.users / "999" / "datastore" / "macroTrainerBuildOrders.rlt",
        )
        self.assertFalse(self.users.exists())

    def test_explicit_profile_selects_one_candidate_when_multiple_exist(self) -> None:
        (self.users / "111").mkdir(parents=True)
        (self.users / "222").mkdir()

        path = resolve_datastore_path("222", documents_dir=self.documents)

        self.assertEqual(path.parent.parent.name, "222")

    def test_profile_id_cannot_escape_users_directory(self) -> None:
        invalid = ("", ".", "..", "../other", r"..\other", "/absolute", r"C:\absolute")
        for profile_id in invalid:
            with self.subTest(profile_id=profile_id):
                with self.assertRaises(ProfileResolutionError):
                    resolve_datastore_path(profile_id, documents_dir=self.documents)


if __name__ == "__main__":
    unittest.main()
