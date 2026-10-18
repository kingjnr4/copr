from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_eclipse_installer import (
    ARCHIVES, DOWNLOAD_BASE, DOWNLOADS_URL, SPEC_PATH, SUMS_URL,
    Release, discover_release, extract_checksum, extract_version,
    render_updated_spec, update_spec,
)


def downloads(version: str = "2026-09", stage: str = "R") -> str:
    # eclipse.org may show Windows links regardless of the updater's platform.
    return (f'<a href="https://www.eclipse.org/downloads/download.php?'
            f'file=/oomph/epp/{version}/{stage}/eclipse-inst-jre-win64.exe">Download</a>')


def directory(version: str = "2026-09") -> str:
    return "".join(
        f'<a href="https://www.eclipse.org/downloads/download.php?file=/oomph/epp/{version}/R/{name}">Linux</a>'
        for name in ARCHIVES.values()
    )


class DiscoverReleaseTests(unittest.TestCase):
    def test_discovers_stable_release_from_platform_independent_links(self) -> None:
        self.assertEqual(extract_version(downloads()), "2026-09")
        self.assertEqual(extract_version(downloads() * 2), "2026-09")

    def test_ignores_milestones_and_release_candidates(self) -> None:
        self.assertEqual(extract_version(downloads() + downloads("2026-12", "M1")), "2026-09")
        for stage in ("M1", "RC1", "latest"):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "no stable"):
                extract_version(downloads(stage=stage))

    def test_rejects_missing_or_ambiguous_releases(self) -> None:
        for html in ("", downloads() + downloads("2026-12")):
            with self.subTest(html=html), self.assertRaises(ValueError):
                extract_version(html)

    def test_ignores_untrusted_origins_and_malformed_versions(self) -> None:
        for html in (
            downloads().replace("www.eclipse.org", "example.invalid"),
            downloads().replace("https:", "http:"),
            downloads("2026-13"), downloads("2026-9"),
            downloads().replace("?file=", "?file=/other&file="),
        ):
            with self.subTest(html=html), self.assertRaisesRegex(ValueError, "no stable"):
                extract_version(html)

    def test_validates_sha512_and_exact_filename(self) -> None:
        name = ARCHIVES["x86_64"]
        self.assertEqual(extract_checksum(f"{'a' * 128}  {name}\n", name), "a" * 128)
        for text in ("<html>not found</html>", f"{'a' * 64}  {name}",
                     f"{'a' * 128}  other.tar.gz", f"{'g' * 128}  {name}"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "SHA-512"):
                extract_checksum(text, name)

    @patch("scripts.update_eclipse_installer.fetch_text")
    def test_requires_both_archives_and_checksums(self, fetch) -> None:
        names = list(ARCHIVES.values())
        fetch.side_effect = [downloads(), directory(),
                             f"{'a' * 128}  {names[0]}", f"{'b' * 128}  {names[1]}"]
        self.assertEqual(discover_release(), Release("2026-09", {"x86_64": "a" * 128, "aarch64": "b" * 128}))
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [
            DOWNLOADS_URL, DOWNLOAD_BASE + "/oomph/epp/2026-09/R/",
            *[SUMS_URL + "/oomph/epp/2026-09/R/" + name for name in names],
        ])

    @patch("scripts.update_eclipse_installer.fetch_text")
    def test_missing_arm_archive_fails_instead_of_falling_back(self, fetch) -> None:
        fetch.side_effect = [downloads(), directory().replace(ARCHIVES["aarch64"], "missing"),
                             f"{'a' * 128}  {ARCHIVES['x86_64']}"]
        with self.assertRaisesRegex(ValueError, "aarch64"):
            discover_release()


class RenderSpecTests(unittest.TestCase):
    SPEC = f"""%global eclipse_release 2026-06
%global sha512_x86_64 {'c' * 128}
%global sha512_aarch64 {'d' * 128}
Name: eclipse-installer
Version:        2026.06
Release:        4%{{?dist}}
"""

    def setUp(self) -> None:
        self.release = Release("2026-09", {"x86_64": "a" * 128, "aarch64": "b" * 128})

    def test_updates_version_release_path_and_both_checksums(self) -> None:
        updated, changed = render_updated_spec(self.SPEC, self.release)
        self.assertTrue(changed)
        for value in ("Version:        2026.09", "Release:        1%{?dist}",
                      "%global eclipse_release 2026-09", f"%global sha512_x86_64 {'a' * 128}",
                      f"%global sha512_aarch64 {'b' * 128}"):
            self.assertIn(value, updated)

    def test_preserves_unchanged_spec(self) -> None:
        current, _ = render_updated_spec(self.SPEC, self.release)
        self.assertEqual(render_updated_spec(current, self.release), (current, False))

    def test_rejects_downgrade(self) -> None:
        with self.assertRaisesRegex(ValueError, "downgrade"):
            render_updated_spec(self.SPEC, Release("2026-03", self.release.checksums))

    def test_rejects_republished_archive(self) -> None:
        current, _ = render_updated_spec(self.SPEC, self.release)
        release = Release("2026-09", {**self.release.checksums, "aarch64": "e" * 128})
        with self.assertRaisesRegex(ValueError, "manual review"):
            render_updated_spec(current, release)

    def test_rejects_malformed_spec_fields(self) -> None:
        for spec in (
            self.SPEC + "Version: 2026.06\n", self.SPEC.replace("Release:", "Other:"),
            self.SPEC.replace("%global sha512_aarch64", "%global other"),
            self.SPEC.replace("2026.06", "2026.03"),
            self.SPEC.replace("2026-06", "2026-13"),
            self.SPEC + f"%global sha512_x86_64 {'c' * 128}\n",
            self.SPEC.replace("d" * 128, "not-a-checksum"),
        ):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                render_updated_spec(spec, self.release)

    def test_rejects_incomplete_or_invalid_release(self) -> None:
        for release in (Release("2026-13", self.release.checksums),
                        Release("2026-09", {"x86_64": "a" * 128}),
                        Release("2026-09", {"x86_64": "a" * 64, "aarch64": "b" * 128})):
            with self.subTest(release=release), self.assertRaises(ValueError):
                render_updated_spec(self.SPEC, release)

    @patch("scripts.update_eclipse_installer.discover_release")
    def test_check_mode_and_atomic_write(self, discover) -> None:
        discover.return_value = self.release
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / SPEC_PATH
            path.parent.mkdir(parents=True)
            path.write_text(self.SPEC, encoding="utf-8")
            path.chmod(0o640)
            self.assertTrue(update_spec(root, check=True))
            self.assertEqual(path.read_text(encoding="utf-8"), self.SPEC)
            self.assertTrue(update_spec(root))
            self.assertIn("2026.09", path.read_text(encoding="utf-8"))
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)


if __name__ == "__main__":
    unittest.main()
