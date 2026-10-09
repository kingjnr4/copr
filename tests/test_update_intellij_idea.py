from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_intellij_idea import (
    DOWNLOAD_BASE,
    Release,
    discover_release,
    extract_release,
    render_updated_spec,
    update_spec,
)


def release_data(version: str = "2026.2.3") -> dict:
    return {
        "tag_name": f"idea/{version}",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": f"idea-{version}{suffix}.tar.gz",
                "browser_download_url": f"{DOWNLOAD_BASE}idea/{version}/idea-{version}{suffix}.tar.gz",
                "digest": f"sha256:{digest * 64}",
                "size": 100,
            }
            for suffix, digest in (("", "a"), ("-aarch64", "b"))
        ],
    }


class ExtractReleaseTests(unittest.TestCase):
    def test_extracts_both_architectures(self) -> None:
        self.assertEqual(
            extract_release([release_data()]),
            Release("2026.2.3", {"x86_64": "a" * 64, "aarch64": "b" * 64}),
        )

    def test_ignores_pycharm_drafts_and_previews(self) -> None:
        candidates = [
            {"tag_name": "pycharm/2027.1"},
            {**release_data("2027.1"), "draft": True},
            {**release_data("2027.1"), "prerelease": True},
            {"tag_name": "idea/2027.1-eap"},
            release_data(),
        ]
        self.assertEqual(extract_release(candidates).version, "2026.2.3")

    def test_selects_latest_numeric_version(self) -> None:
        self.assertEqual(
            extract_release([release_data("2026.2.9"), release_data("2026.2.10")]).version,
            "2026.2.10",
        )

    def test_returns_none_when_no_idea_release(self) -> None:
        self.assertIsNone(extract_release([{"tag_name": "pycharm/2026.2.3"}]))

    def test_rejects_ambiguous_release(self) -> None:
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            extract_release([release_data(), release_data()])

    def test_rejects_missing_or_duplicate_architecture(self) -> None:
        for assets in (release_data()["assets"][:1], release_data()["assets"] * 2):
            with self.subTest(assets=assets), self.assertRaisesRegex(ValueError, "expected one"):
                extract_release([{**release_data(), "assets": assets}])

    def test_does_not_fall_back_if_latest_release_is_incomplete(self) -> None:
        newer = release_data("2026.2.4")
        newer["assets"].pop()
        with self.assertRaisesRegex(ValueError, "aarch64"):
            extract_release([newer, release_data()])

    def test_rejects_missing_invalid_or_non_sha256_digest(self) -> None:
        for digest in (None, "", "sha256:abc", "sha512:" + "a" * 64):
            data = release_data()
            data["assets"][1]["digest"] = digest
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "SHA-256"):
                extract_release([data])

    def test_rejects_unexpected_download_origin_or_version(self) -> None:
        for url in (
            "https://download.jetbrains.com/idea/idea-2026.2.3.tar.gz",
            "https://example.invalid/idea-2026.2.3.tar.gz",
            release_data("2026.2.2")["assets"][0]["browser_download_url"],
        ):
            data = release_data()
            data["assets"][0]["browser_download_url"] = url
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "download URL"):
                extract_release([data])

    def test_rejects_empty_archives(self) -> None:
        data = release_data()
        data["assets"][0]["size"] = 0
        with self.assertRaisesRegex(ValueError, "empty"):
            extract_release([data])

    @patch("scripts.update_intellij_idea.fetch_releases")
    def test_paginates_past_pycharm(self, fetch) -> None:
        fetch.side_effect = [[{"tag_name": "pycharm/2026.2.3"}] * 100, [release_data()]]
        self.assertEqual(discover_release().version, "2026.2.3")
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [1, 2])

    @patch("scripts.update_intellij_idea.fetch_releases", return_value=[])
    def test_rejects_absent_releases(self, fetch) -> None:
        with self.assertRaisesRegex(ValueError, "no stable"):
            discover_release()


class RenderSpecTests(unittest.TestCase):
    SPEC = f"""%global sha256_x86_64 {'c' * 64}
%global sha256_aarch64 {'d' * 64}
Name: intellij-idea
Version:        2026.2.2
Release:        4%{{?dist}}
"""

    def setUp(self) -> None:
        self.release = extract_release([release_data()])

    def test_updates_version_and_both_checksums(self) -> None:
        updated, changed = render_updated_spec(self.SPEC, self.release)
        self.assertTrue(changed)
        self.assertIn("Version:        2026.2.3", updated)
        self.assertIn("Release:        1%{?dist}", updated)
        self.assertIn(f"%global sha256_x86_64 {'a' * 64}", updated)
        self.assertIn(f"%global sha256_aarch64 {'b' * 64}", updated)

    def test_preserves_unchanged_spec(self) -> None:
        current, _ = render_updated_spec(self.SPEC, self.release)
        self.assertEqual(render_updated_spec(current, self.release), (current, False))

    def test_rejects_downgrade(self) -> None:
        with self.assertRaisesRegex(ValueError, "downgrade"):
            render_updated_spec(self.SPEC, Release("2026.1.9", self.release.checksums))

    def test_rejects_changed_checksum_for_same_version(self) -> None:
        current, _ = render_updated_spec(self.SPEC, self.release)
        checksums = {**self.release.checksums, "aarch64": "e" * 64}
        with self.assertRaisesRegex(ValueError, "manual review"):
            render_updated_spec(current, Release(self.release.version, checksums))

    def test_rejects_missing_or_duplicate_fields(self) -> None:
        for spec in (
            self.SPEC.replace("%global sha256_aarch64", "%global other"),
            self.SPEC + "Version: 2026.2.2\n",
            self.SPEC.replace("Release:", "Other:"),
            self.SPEC + f"%global sha256_x86_64 {'c' * 64}\n",
        ):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                render_updated_spec(spec, self.release)

    def test_rejects_incomplete_release_before_writing(self) -> None:
        with self.assertRaisesRegex(ValueError, "aarch64"):
            render_updated_spec(self.SPEC, Release("2026.2.3", {"x86_64": "a" * 64}))

    @patch("scripts.update_intellij_idea.discover_release")
    def test_check_mode_does_not_write(self, discover) -> None:
        discover.return_value = self.release
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "packages/intellij-idea/intellij-idea.spec"
            path.parent.mkdir(parents=True)
            path.write_text(self.SPEC, encoding="utf-8")
            path.chmod(0o640)
            self.assertTrue(update_spec(root, check=True))
            self.assertEqual(path.read_text(encoding="utf-8"), self.SPEC)
            self.assertTrue(update_spec(root))
            self.assertIn("2026.2.3", path.read_text(encoding="utf-8"))
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)


if __name__ == "__main__":
    unittest.main()
