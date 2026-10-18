from __future__ import annotations

import configparser
import hashlib
import io
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parent.parent / "packages/eclipse-installer"


class EclipseDesktopTests(unittest.TestCase):
    def test_startup_class_matches_swt_wayland_app_id(self) -> None:
        desktop = configparser.ConfigParser(interpolation=None)
        desktop.read(PACKAGE / "org.eclipse.Installer.desktop", encoding="utf-8")
        entry = desktop["Desktop Entry"]
        # This is U+00A0, not the ordinary space used in the visible menu label.
        self.assertEqual(entry["StartupWMClass"], "Eclipse\u00a0Installer")
        self.assertEqual(entry["Name"], "Eclipse Installer")
        self.assertEqual(entry["Icon"], "org.eclipse.Installer")


@unittest.skipUnless(shutil.which("rpmbuild"), "rpmbuild is required")
class EclipseSpecPrepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "SOURCES"
        self.sources.mkdir()
        self.spec = (PACKAGE / "eclipse-installer.spec").read_text(encoding="utf-8")
        self.release = re.search(r"^%global eclipse_release (\S+)", self.spec, re.MULTILINE)[1]
        for path in PACKAGE.glob("org.eclipse.*"):
            shutil.copyfile(path, self.sources / path.name)

    def archive(self, arch: str, machine: int, *, runtime_machine: int | None = None,
                product: str = "org.eclipse.oomph.setup.installer.product",
                release: str | None = None) -> Path:
        suffix = "-aarch64" if arch == "aarch64" else "64"
        path = self.sources / f"eclipse-inst-jre-linux{suffix}.tar.gz"
        header = lambda machine: b"\x7fELF\x02\x01" + bytes(12) + struct.pack("<H", machine)
        runtime = f"plugins/org.eclipse.justj.openjdk.hotspot.jre.minimal.stripped.linux.{arch}_21/jre/bin/java"
        config = (f"eclipse.product={product}\n"
                  f"oomph.setup.product.version.filter=.*\\\\.{release or self.release}\n")
        with tarfile.open(path, "w:gz") as archive:
            for name, content in (
                ("eclipse-inst", header(machine)),
                (runtime, header(runtime_machine or machine)),
                ("eclipse-inst.ini", f"-vm\n{runtime}\n-vmargs\n".encode()),
                ("configuration/config.ini", config.encode()),
                ("selected-architecture", arch.encode()),
            ):
                info = tarfile.TarInfo(f"eclipse-installer/{name}")
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        digest = hashlib.sha512(path.read_bytes()).hexdigest()
        self.spec = re.sub(
            rf"^%global sha512_{arch} \S+", f"%global sha512_{arch} {digest}",
            self.spec, flags=re.MULTILINE,
        )
        return path

    def prep(self, arch: str) -> subprocess.CompletedProcess:
        path = self.root / "eclipse-installer.spec"
        path.write_text(self.spec, encoding="utf-8")
        return subprocess.run(
            ["rpmbuild", "-bp", "--nodeps", "--target", arch,
             "--define", f"_topdir {self.root}", str(path)],
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

    def test_wrong_launcher_and_runtime_architectures_are_rejected(self) -> None:
        self.archive("x86_64", 62)
        for launcher, runtime in ((62, 183), (183, 62)):
            with self.subTest(launcher=launcher, runtime=runtime):
                self.archive("aarch64", launcher, runtime_machine=runtime)
                result = self.prep("aarch64")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("wrong native architecture", result.stderr)

    def test_both_archives_are_verified_even_on_x86(self) -> None:
        self.archive("x86_64", 62)
        arm = self.archive("aarch64", 183)
        with arm.open("ab") as output:
            output.write(b"corruption")
        result = self.prep("x86_64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)

    def test_wrong_product_is_rejected(self) -> None:
        self.archive("x86_64", 62, product="org.eclipse.platform.ide")
        self.archive("aarch64", 183)
        result = self.prep("x86_64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wrong Eclipse product", result.stderr)

    def test_wrong_release_is_rejected(self) -> None:
        self.archive("x86_64", 62, release="2000-03")
        self.archive("aarch64", 183)
        result = self.prep("x86_64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wrong Eclipse release", result.stderr)


if __name__ == "__main__":
    unittest.main()
