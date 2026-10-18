from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts/configure_copr.sh"


class ConfigureCoprTests(unittest.TestCase):
    def run_helper(self, *args: str) -> list[list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "calls"
            cli = root / "copr-cli"
            cli.write_text(
                '#!/bin/sh\nprintf "%s " "$@" >> "$CALL_LOG"\n'
                'printf "\\n" >> "$CALL_LOG"\n',
                encoding="utf-8",
            )
            cli.chmod(0o755)
            env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}", "CALL_LOG": str(log)}
            subprocess.run(["bash", str(SCRIPT), *args], env=env, check=True, capture_output=True)
            return [line.split() for line in log.read_text(encoding="utf-8").splitlines()]

    def test_defaults_enable_both_architectures_and_register_packages(self) -> None:
        calls = self.run_helper()
        modify = next(call for call in calls if call[0] == "modify")
        chroots = [modify[index + 1] for index, value in enumerate(modify) if value == "--chroot"]
        self.assertEqual(set(chroots), {
            f"fedora-{version}-{arch}"
            for version in ("43", "44", "45", "rawhide")
            for arch in ("x86_64", "aarch64")
        })
        packages = [call for call in calls if call[0] == "edit-package-scm"]
        self.assertEqual(len(packages), 5)
        idea = next(call for call in packages if "intellij-idea" in call)
        self.assertIn("packages/intellij-idea", idea)
        self.assertIn("intellij-idea.spec", idea)
        self.assertEqual(idea[idea.index("--webhook-rebuild") + 1], "off")
        eclipse = next(call for call in packages if "eclipse-installer" in call)
        self.assertIn("packages/eclipse-installer", eclipse)
        self.assertIn("eclipse-installer.spec", eclipse)
        self.assertEqual(eclipse[eclipse.index("--webhook-rebuild") + 1], "off")

    def test_custom_chroots_are_preserved(self) -> None:
        calls = self.run_helper(
            "owner/custom", "https://example.invalid/project.git",
            "fedora-44-x86_64", "fedora-44-aarch64",
        )
        modify = next(call for call in calls if call[0] == "modify")
        self.assertEqual(modify[1], "owner/custom")
        chroots = [modify[index + 1] for index, value in enumerate(modify) if value == "--chroot"]
        self.assertEqual(chroots, ["fedora-44-x86_64", "fedora-44-aarch64"])


if __name__ == "__main__":
    unittest.main()
