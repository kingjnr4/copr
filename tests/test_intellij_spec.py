from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parent.parent / "packages/intellij-idea"


@unittest.skipUnless(shutil.which("rpmbuild"), "rpmbuild is required")
class SpecPrepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "SOURCES"
        self.sources.mkdir()
        self.spec = (PACKAGE / "intellij-idea.spec").read_text(encoding="utf-8")
        self.version = re.search(r"^Version:\s+(\S+)", self.spec, re.MULTILINE)[1]
        for path in PACKAGE.glob("com.jetbrains.*"):
            shutil.copyfile(path, self.sources / path.name)

    def archive(self, arch: str, machine: int, product: str = "IC") -> Path:
        suffix = "-aarch64" if arch == "aarch64" else ""
        path = self.sources / f"idea-{self.version}{suffix}.tar.gz"
        header = b"\x7fELF\x02\x01" + bytes(12) + struct.pack("<H", machine)
        info = json.dumps({
            "version": self.version,
            "productCode": product,
            "launch": [{"os": "Linux", "arch": "aarch64" if arch == "aarch64" else "amd64"}],
        }).encode()
        with tarfile.open(path, "w:gz") as archive:
            for name, content in (
                ("jbr/bin/java", header), ("bin/idea", header),
                ("product-info.json", info), ("selected-architecture", arch.encode()),
            ):
                info = tarfile.TarInfo(f"idea-test/{name}")
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.spec = re.sub(
            rf"^%global sha256_{arch} \S+",
            f"%global sha256_{arch} {digest}",
            self.spec,
            flags=re.MULTILINE,
        )
        return path

    def prep(self, arch: str) -> subprocess.CompletedProcess:
        spec_path = self.root / "intellij-idea.spec"
        spec_path.write_text(self.spec, encoding="utf-8")
        return subprocess.run(
            ["rpmbuild", "-bp", "--nodeps", "--target", arch,
             "--define", f"_topdir {self.root}", str(spec_path)],
            text=True, capture_output=True,
        )

    def test_each_architecture_extracts_its_own_payload(self) -> None:
        self.archive("x86_64", 62)
        self.archive("aarch64", 183)
        for arch in ("x86_64", "aarch64"):
            with self.subTest(arch=arch):
                result = self.prep(arch)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                markers = list((self.root / "BUILD").rglob("selected-architecture"))
                self.assertEqual(len(markers), 1)
                self.assertEqual(markers[0].read_text(), arch)

    def test_wrong_runtime_architecture_is_rejected(self) -> None:
        self.archive("x86_64", 62)
        self.archive("aarch64", 62)
        result = self.prep("aarch64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wrong runtime architecture", result.stderr)

    def test_both_archives_are_verified_even_on_x86(self) -> None:
        self.archive("x86_64", 62)
        arm = self.archive("aarch64", 183)
        with arm.open("ab") as output:
            output.write(b"corruption")
        result = self.prep("x86_64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)

    def test_proprietary_edition_is_rejected(self) -> None:
        self.archive("x86_64", 62, product="IU")
        self.archive("aarch64", 183)
        result = self.prep("x86_64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected the open-source IDEA edition", result.stderr)


if __name__ == "__main__":
    unittest.main()
