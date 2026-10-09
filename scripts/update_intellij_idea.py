#!/usr/bin/env python3
"""Pin official IntelliJ IDEA open-source releases and both Linux checksums."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

if __package__:
    from .update_android_studio import version_key, write_atomic
else:
    from update_android_studio import version_key, write_atomic


RELEASES_URL = "https://api.github.com/repos/JetBrains/intellij-community/releases"
DOWNLOAD_BASE = "https://github.com/JetBrains/intellij-community/releases/download/"
SPEC_PATH = "packages/intellij-idea/intellij-idea.spec"
VERSION_RE = re.compile(r"^Version:\s+(\S+)\s*$", re.MULTILINE)
RELEASE_RE = re.compile(r"^Release:\s+\S+\s*$", re.MULTILINE)
ARCHITECTURES = {"x86_64": "", "aarch64": "-aarch64"}


@dataclass(frozen=True)
class Release:
    version: str
    checksums: dict[str, str]


def extract_release(releases: list[dict]) -> Release | None:
    candidates = []
    for release in releases:
        tag = release.get("tag_name", "")
        if release.get("draft") or release.get("prerelease"):
            continue
        if re.fullmatch(r"idea/[0-9]+(?:\.[0-9]+)+", tag):
            candidates.append(release)
    if not candidates:
        return None

    latest_version = max(version_key(item["tag_name"][5:]) for item in candidates)
    latest = [
        item for item in candidates
        if version_key(item["tag_name"][5:]) == latest_version
    ]
    if len(latest) != 1:
        raise ValueError("ambiguous IntelliJ IDEA release")
    release = latest[0]
    version = release["tag_name"][5:]
    checksums = {}
    for arch, suffix in ARCHITECTURES.items():
        name = f"idea-{version}{suffix}.tar.gz"
        assets = [
            asset for asset in release.get("assets", [])
            if asset.get("name") == name
        ]
        if len(assets) != 1:
            raise ValueError(f"expected one {arch} archive, found {len(assets)}")
        asset = assets[0]
        expected_url = f"{DOWNLOAD_BASE}idea/{version}/{name}"
        if asset.get("browser_download_url") != expected_url:
            raise ValueError(f"unexpected {arch} download URL")
        digest = asset.get("digest") or ""
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError(f"missing or invalid {arch} SHA-256 digest")
        if not isinstance(asset.get("size"), int) or asset["size"] <= 0:
            raise ValueError(f"empty {arch} archive")
        checksums[arch] = digest.removeprefix("sha256:")
    return Release(version, checksums)


def fetch_releases(page: int) -> list[dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "copr-intellij-idea-updater/1.0",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{RELEASES_URL}?per_page=100&page={page}", headers=headers)
    with urlopen(request, timeout=60) as response:
        data = json.load(response)
    if not isinstance(data, list):
        raise ValueError("expected a GitHub release list")
    return data


def discover_release() -> Release:
    # The repository also publishes PyCharm; /releases/latest is not IDEA-specific.
    for page in range(1, 11):
        releases = fetch_releases(page)
        release = extract_release(releases)
        if release:
            return release
        if len(releases) < 100:
            break
    raise ValueError("no stable IntelliJ IDEA open-source release found")


def checksum_pattern(arch: str) -> re.Pattern:
    return re.compile(rf"^%global\s+sha256_{arch}\s+(\S+)\s*$", re.MULTILINE)


def render_updated_spec(spec: str, release: Release) -> tuple[str, bool]:
    versions = VERSION_RE.findall(spec)
    if len(versions) != 1 or len(RELEASE_RE.findall(spec)) != 1:
        raise ValueError("spec must contain one Version and Release")
    current_version = versions[0]
    if version_key(release.version) < version_key(current_version):
        raise ValueError(
            f"refusing version downgrade from {current_version} to {release.version}"
        )

    current_checksums = {}
    for arch in ARCHITECTURES:
        values = checksum_pattern(arch).findall(spec)
        if len(values) != 1 or not re.fullmatch(r"[0-9a-f]{64}", values[0]):
            raise ValueError(f"spec is missing a valid {arch} SHA-256 digest")
        if not re.fullmatch(r"[0-9a-f]{64}", release.checksums.get(arch, "")):
            raise ValueError(f"release is missing a valid {arch} SHA-256 digest")
        current_checksums[arch] = values[0]

    if current_version == release.version:
        if current_checksums != release.checksums:
            raise ValueError(
                "upstream checksums changed for the pinned version; manual review required"
            )
        return spec, False

    updated = VERSION_RE.sub(f"Version:        {release.version}", spec)
    updated = RELEASE_RE.sub("Release:        1%{?dist}", updated)
    for arch in ARCHITECTURES:
        updated = checksum_pattern(arch).sub(
            f"%global sha256_{arch} {release.checksums[arch]}", updated
        )
    return updated, True


def update_spec(repo_root: Path, check: bool = False) -> bool:
    release = discover_release()
    path = repo_root / SPEC_PATH
    updated, changed = render_updated_spec(path.read_text(encoding="utf-8"), release)
    if changed:
        if not check:
            write_atomic(path, updated)
        status = "update available" if check else "updated to"
        print(f"intellij-idea: {status} {release.version}")
    else:
        print(f"intellij-idea: current at {release.version}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report updates without modifying the spec"
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    args = parser.parse_args()
    try:
        changed = update_spec(args.repo_root.resolve(), check=args.check)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
