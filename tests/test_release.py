"""Reject incorrectly labelled or unverified artifacts before public release."""
import unittest

from scripts.ci_release import validate_package, validate_tag


class ReleaseGateTests(unittest.TestCase):
    def test_tag_must_match_application_version(self):
        validate_tag("v0.1.9", "0.1.9")
        for tag in ("v0.1.8", "0.1.9", "v0.1.9-rc1", "v0.1.9/extra", "v0.1.9\n"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate_tag(tag, "0.1.9")

    def test_clean_tested_package_is_accepted(self):
        validate_package({"source_commit": "abc", "source_dirty": False},
                         {"camera_opened": False, "passed": 14, "checks": list(range(14))}, "abc")

    def test_dirty_or_wrong_commit_is_rejected(self):
        verification = {"camera_opened": False, "passed": 14, "checks": list(range(14))}
        for manifest in ({"source_commit": "other", "source_dirty": False},
                         {"source_commit": "abc", "source_dirty": True},
                         {"source_commit": "abc"}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                validate_package(manifest, verification, "abc")

    def test_missing_camera_or_incomplete_checks_are_rejected(self):
        manifest = {"source_commit": "abc", "source_dirty": False}
        for verification in ({"passed": 14, "checks": list(range(14))},
                             {"camera_opened": True, "passed": 14, "checks": list(range(14))},
                             {"camera_opened": False, "passed": 13, "checks": list(range(13))},
                             {"camera_opened": False, "passed": 14, "checks": []}):
            with self.subTest(verification=verification), self.assertRaises(ValueError):
                validate_package(manifest, verification, "abc")
