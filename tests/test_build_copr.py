from __future__ import annotations

import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from scripts.build_copr import main, select_chroots


class SelectChrootsTests(unittest.TestCase):
    CHROOTS = [
        "fedora-43-x86_64", "fedora-44-x86_64", "fedora-rawhide-x86_64",
        "fedora-43-aarch64", "fedora-44-aarch64", "fedora-rawhide-aarch64",
        "fedora-44-ppc64le", "fedora-rawhide-riscv64",
    ]

    def test_android_studio_never_selects_arm(self) -> None:
        expected = sorted(chroot for chroot in self.CHROOTS if chroot.endswith("-x86_64"))
        for package in ("android-studio", "android-studio-beta", "android-studio-canary"):
            with self.subTest(package=package):
                self.assertEqual(select_chroots(package, self.CHROOTS), expected)

    def test_intellij_selects_both_supported_architectures(self) -> None:
        self.assertEqual(select_chroots("intellij-idea", self.CHROOTS), sorted(self.CHROOTS[:6]))

    def test_eclipse_selects_both_supported_architectures(self) -> None:
        self.assertEqual(select_chroots("eclipse-installer", self.CHROOTS), sorted(self.CHROOTS[:6]))
        for arch in ("x86_64", "aarch64"):
            with self.subTest(arch=arch), self.assertRaisesRegex(ValueError, "requires an enabled"):
                select_chroots("eclipse-installer", [f"fedora-44-{arch}"])

    def test_rejects_missing_required_architecture(self) -> None:
        with self.assertRaisesRegex(ValueError, "aarch64"):
            select_chroots("intellij-idea", ["fedora-44-x86_64"])
        with self.assertRaisesRegex(ValueError, "x86_64"):
            select_chroots("android-studio", ["fedora-44-aarch64"])

    def test_rejects_empty_chroots(self) -> None:
        with self.assertRaises(ValueError):
            select_chroots("intellij-idea", [])

    def test_sorts_and_deduplicates_enabled_chroots(self) -> None:
        self.assertEqual(
            select_chroots("android-studio", ["fedora-44-x86_64"] * 2),
            ["fedora-44-x86_64"],
        )


class SubmitBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.v3 = ModuleType("copr.v3")
        self.v3.Client = Mock()
        self.v3.Client.create_from_config_file.return_value = self.client
        copr = ModuleType("copr")
        copr.v3 = self.v3
        patcher = patch.dict("sys.modules", {"copr": copr, "copr.v3": self.v3})
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("scripts.build_copr.subprocess.call", return_value=0)
    def test_submits_only_selected_chroots(self, call) -> None:
        self.client.project_proxy.get.return_value = SimpleNamespace(chroot_repos={
            "fedora-44-aarch64": "arm", "fedora-44-x86_64": "x86",
            "fedora-44-riscv64": "unsupported",
        })
        with patch("sys.argv", ["build_copr.py", "intellij-idea", "--project", "owner/custom"]):
            self.assertEqual(main(), 0)
        self.client.project_proxy.get.assert_called_once_with("owner", "custom")
        call.assert_called_once_with([
            "copr-cli", "build-package", "--name", "intellij-idea",
            "--chroot", "fedora-44-aarch64", "--chroot", "fedora-44-x86_64",
            "owner/custom",
        ])

    @patch("scripts.build_copr.subprocess.call")
    def test_missing_arm_fails_before_submission(self, call) -> None:
        self.client.project_proxy.get.return_value = SimpleNamespace(
            chroot_repos={"fedora-44-x86_64": "x86"}
        )
        with patch("sys.argv", ["build_copr.py", "intellij-idea"]):
            self.assertEqual(main(), 2)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
