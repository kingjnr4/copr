from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.update_android_studio import (
    CHANNELS,
    Release,
    extract_release,
    render_updated_spec,
    write_atomic,
)


PREVIEW_HTML = """
<a data-category="canary_linux_bundle_download"
   href="https://edgedl.me.gvt1.com/android/studio/ide-zips/2026.2.2.1/android-studio-rabbit2-canary1-linux.tar.gz">
  Canary
</a>
<a data-category="beta_linux_bundle_download"
   href="https://edgedl.me.gvt1.com/android/studio/ide-zips/2026.2.1.6/android-studio-rabbit1-rc1-linux.tar.gz">
  Beta
</a>
"""

STABLE_HTML = """
<a data-category="studio_linux_bundle_download"
   href="https://edgedl.me.gvt1.com/android/studio/ide-zips/2026.1.4.8/android-studio-quail4-patch1-linux.tar.gz">
  Stable
</a>
"""


class ExtractReleaseTests(unittest.TestCase):
    def test_extracts_each_channel_by_category(self) -> None:
        stable, beta, canary = CHANNELS

        self.assertEqual(
            extract_release(STABLE_HTML, stable),
            Release(
                "2026.1.4.8",
                "quail4-patch1",
                "https://edgedl.me.gvt1.com/android/studio/ide-zips/2026.1.4.8/android-studio-quail4-patch1-linux.tar.gz",
            ),
        )
        self.assertEqual(extract_release(PREVIEW_HTML, beta).archive_id, "rabbit1-rc1")
        self.assertEqual(
            extract_release(PREVIEW_HTML, canary).archive_id, "rabbit2-canary1"
        )

    def test_rejects_ambiguous_category(self) -> None:
        html = PREVIEW_HTML + PREVIEW_HTML.replace("2026.2.1.6", "2026.2.1.7")
        with self.assertRaisesRegex(ValueError, "expected one beta"):
            extract_release(html, CHANNELS[1])

    def test_rejects_wrong_channel_suffix(self) -> None:
        html = PREVIEW_HTML.replace("rabbit1-rc1", "rabbit1-canary5")
        with self.assertRaisesRegex(ValueError, "beta download"):
            extract_release(html, CHANNELS[1])


class RenderSpecTests(unittest.TestCase):
    SPEC = """Name: example
%global archive_id old-canary1
Version:        2026.1.1.1
Release:        4%{?dist}
"""

    def test_updates_version_archive_and_release(self) -> None:
        updated, changed = render_updated_spec(
            self.SPEC,
            Release("2026.2.2.1", "rabbit2-canary1", "https://example.invalid"),
        )

        self.assertTrue(changed)
        self.assertIn("Version:        2026.2.2.1", updated)
        self.assertIn("%global archive_id rabbit2-canary1", updated)
        self.assertIn("Release:        1%{?dist}", updated)

    def test_leaves_current_spec_unchanged(self) -> None:
        release = Release("2026.1.1.1", "old-canary1", "https://example.invalid")
        updated, changed = render_updated_spec(self.SPEC, release)
        self.assertFalse(changed)
        self.assertEqual(updated, self.SPEC)

    def test_rejects_downgrade(self) -> None:
        with self.assertRaisesRegex(ValueError, "refusing version downgrade"):
            render_updated_spec(
                self.SPEC,
                Release("2025.3.1.1", "panda-canary1", "https://example.invalid"),
            )

    def test_atomic_write_replaces_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "package.spec"
            path.write_text("old\n", encoding="utf-8")
            write_atomic(path, "new\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")


if __name__ == "__main__":
    unittest.main()
