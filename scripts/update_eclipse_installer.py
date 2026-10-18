#!/usr/bin/env python3
"""Pin stable Eclipse Installer releases and official Linux SHA-512 checksums."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

if __package__:
    from .update_android_studio import write_atomic
else:
    from update_android_studio import write_atomic


DOWNLOADS_URL = "https://www.eclipse.org/downloads/"
DOWNLOAD_BASE = "https://download.eclipse.org"
SUMS_URL = "https://www.eclipse.org/downloads/sums.php?file="
SPEC_PATH = "packages/eclipse-installer/eclipse-installer.spec"
ARCHIVES = {
    "x86_64": "eclipse-inst-jre-linux64.tar.gz",
    "aarch64": "eclipse-inst-jre-linux-aarch64.tar.gz",
}
STABLE_PATH_RE = re.compile(
    r"^/oomph/epp/([0-9]{4}-(?:03|06|09|12))/R/eclipse-inst-jre-"
    r"(?:linux64\.tar\.gz|linux-aarch64\.tar\.gz|win64\.exe|win-aarch64\.exe|"
    r"mac64\.dmg|mac-aarch64\.dmg)$"
)


class Links(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.hrefs: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href" and value)


@dataclass(frozen=True)
class Release:
    version: str
    checksums: dict[str, str]


def download_paths(html: str, base: str) -> set[str]:
    paths = set()
    for href in Links(html).hrefs:
        url = urlparse(urljoin(base, href))
        if url.scheme != "https" or url.netloc not in ("www.eclipse.org", "download.eclipse.org"):
            continue
        if url.netloc == "www.eclipse.org" and url.path == "/downloads/download.php":
            files = parse_qs(url.query).get("file", [])
            if len(files) == 1:
                paths.add(files[0])
        elif url.netloc == "download.eclipse.org":
            paths.add(url.path)
    return paths


def extract_version(html: str) -> str:
    versions = {
        match[1] for path in download_paths(html, DOWNLOADS_URL)
        if (match := STABLE_PATH_RE.fullmatch(path))
    }
    if not versions:
        raise ValueError("no stable Eclipse Installer release found")
    if len(versions) != 1:
        raise ValueError("ambiguous stable Eclipse Installer release")
    return versions.pop()


def extract_checksum(text: str, filename: str) -> str:
    match = re.fullmatch(r"\s*([0-9a-f]{128})\s+\*?" + re.escape(filename) + r"\s*", text)
    if not match:
        raise ValueError(f"missing or invalid SHA-512 checksum for {filename}")
    return match[1]


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "copr-eclipse-installer-updater/1.0"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def discover_release() -> Release:
    version = extract_version(fetch_text(DOWNLOADS_URL))
    directory = f"/oomph/epp/{version}/R/"
    url = DOWNLOAD_BASE + directory
    paths = download_paths(fetch_text(url), url)
    checksums = {}
    for arch, filename in ARCHIVES.items():
        path = directory + filename
        if path not in paths:
            raise ValueError(f"stable release is missing the {arch} archive")
        checksums[arch] = extract_checksum(fetch_text(SUMS_URL + path), filename)
    return Release(version, checksums)


def render_updated_spec(spec: str, release: Release) -> tuple[str, bool]:
    if not re.fullmatch(r"[0-9]{4}-(?:03|06|09|12)", release.version):
        raise ValueError("invalid stable Eclipse release version")
    patterns = {
        "version": r"^Version:\s+(\S+)\s*$",
        "release": r"^Release:\s+(\S+)\s*$",
        "eclipse_release": r"^%global\s+eclipse_release\s+(\S+)\s*$",
        **{f"sha512_{arch}": rf"^%global\s+sha512_{arch}\s+(\S+)\s*$" for arch in ARCHIVES},
    }
    current = {}
    for name, pattern in patterns.items():
        values = re.findall(pattern, spec, re.MULTILINE)
        if len(values) != 1:
            raise ValueError(f"spec must contain one {name}")
        current[name] = values[0]
    if not re.fullmatch(r"[0-9]{4}-(?:03|06|09|12)", current["eclipse_release"]):
        raise ValueError("spec has an invalid Eclipse release")
    if current["version"] != current["eclipse_release"].replace("-", "."):
        raise ValueError("spec version does not match its Eclipse release")
    if release.version < current["eclipse_release"]:
        raise ValueError("refusing Eclipse Installer version downgrade")
    for arch in ARCHIVES:
        if not re.fullmatch(r"[0-9a-f]{128}", current[f"sha512_{arch}"]):
            raise ValueError(f"spec is missing a valid {arch} SHA-512 checksum")
        if not re.fullmatch(r"[0-9a-f]{128}", release.checksums.get(arch, "")):
            raise ValueError(f"release is missing a valid {arch} SHA-512 checksum")
    if release.version == current["eclipse_release"]:
        if any(current[f"sha512_{arch}"] != release.checksums[arch] for arch in ARCHIVES):
            raise ValueError("upstream checksums changed for the pinned version; manual review required")
        return spec, False

    replacements = {
        "version": f"Version:        {release.version.replace('-', '.')}",
        "release": "Release:        1%{?dist}",
        "eclipse_release": f"%global eclipse_release {release.version}",
        **{f"sha512_{arch}": f"%global sha512_{arch} {release.checksums[arch]}" for arch in ARCHIVES},
    }
    for name, replacement in replacements.items():
        spec = re.sub(patterns[name], replacement, spec, flags=re.MULTILINE)
    return spec, True


def update_spec(repo_root: Path, check: bool = False) -> bool:
    release = discover_release()
    path = repo_root / SPEC_PATH
    updated, changed = render_updated_spec(path.read_text(encoding="utf-8"), release)
    if changed and not check:
        write_atomic(path, updated)
    status = ("update available" if check else "updated to") if changed else "current at"
    print(f"eclipse-installer: {status} {release.version}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report updates without modifying the spec")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        changed = update_spec(args.repo_root.resolve(), check=args.check)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
