#!/usr/bin/env python3
"""Update Android Studio RPM specs from Google's download pages."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


STABLE_URL = "https://developer.android.com/studio"
PREVIEW_URL = "https://developer.android.com/studio/preview"
USER_AGENT = "copr-android-studio-updater/1.0"


@dataclass(frozen=True)
class Channel:
    name: str
    category: str
    spec_path: str


@dataclass(frozen=True)
class Release:
    version: str
    archive_id: str
    url: str


CHANNELS = (
    Channel(
        "stable",
        "studio_linux_bundle_download",
        "packages/android-studio/android-studio.spec",
    ),
    Channel(
        "beta",
        "beta_linux_bundle_download",
        "packages/android-studio-beta/android-studio-beta.spec",
    ),
    Channel(
        "canary",
        "canary_linux_bundle_download",
        "packages/android-studio-canary/android-studio-canary.spec",
    ),
)

DOWNLOAD_RE = re.compile(
    r"^/android/studio/ide-zips/(?P<version>[0-9]+(?:\.[0-9]+)+)/"
    r"android-studio-(?P<archive>[a-z0-9-]+)-linux\.tar\.gz$"
)
VERSION_RE = re.compile(r"^Version:\s+(?P<value>\S+)\s*$", re.MULTILINE)
ARCHIVE_RE = re.compile(
    r"^%global\s+archive_id\s+(?P<value>\S+)\s*$", re.MULTILINE
)
RELEASE_RE = re.compile(r"^Release:\s+\S+\s*$", re.MULTILINE)


class DownloadLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: dict[str, set[str]] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "a":
            return

        values = dict(attrs)
        category = values.get("data-category")
        href = values.get("href")
        if category and href:
            self.links.setdefault(category, set()).add(href)


def extract_release(html: str, channel: Channel) -> Release:
    parser = DownloadLinkParser()
    parser.feed(html)
    urls = parser.links.get(channel.category, set())

    releases: set[Release] = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not (
            parsed.hostname == "dl.google.com"
            or (parsed.hostname or "").endswith(".gvt1.com")
        ):
            continue

        match = DOWNLOAD_RE.fullmatch(parsed.path)
        if match:
            releases.add(
                Release(
                    version=match.group("version"),
                    archive_id=match.group("archive"),
                    url=url,
                )
            )

    if len(releases) != 1:
        raise ValueError(
            f"expected one {channel.name} Linux download, found {len(releases)}"
        )

    release = releases.pop()
    if channel.name == "stable" and re.search(
        r"-(?:beta|rc|canary)[0-9]+$", release.archive_id
    ):
        raise ValueError("stable download has a preview archive identifier")
    if channel.name == "beta" and not re.search(
        r"-(?:beta|rc)[0-9]+$", release.archive_id
    ):
        raise ValueError("beta download is not a beta or release candidate")
    if channel.name == "canary" and not re.search(
        r"-canary[0-9]+$", release.archive_id
    ):
        raise ValueError("canary download is not a canary build")

    return release


def fetch(url: str, attempts: int = 3) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except Exception as error:  # urllib exposes several transient exceptions.
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)

    raise RuntimeError(f"failed to fetch {url} after {attempts} attempts") from last_error


def discover_releases() -> dict[str, Release]:
    stable_html = fetch(STABLE_URL)
    preview_html = fetch(PREVIEW_URL)
    pages = {"stable": stable_html, "beta": preview_html, "canary": preview_html}
    return {
        channel.name: extract_release(pages[channel.name], channel)
        for channel in CHANNELS
    }


def version_key(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", version):
        raise ValueError(f"invalid numeric version: {version}")
    return tuple(int(part) for part in version.split("."))


def read_spec_version(spec: str) -> tuple[str, str]:
    version_match = VERSION_RE.search(spec)
    archive_match = ARCHIVE_RE.search(spec)
    if not version_match or not archive_match:
        raise ValueError("spec is missing Version or %global archive_id")
    return version_match.group("value"), archive_match.group("value")


def render_updated_spec(spec: str, release: Release) -> tuple[str, bool]:
    current_version, current_archive = read_spec_version(spec)
    if version_key(release.version) < version_key(current_version):
        raise ValueError(
            f"refusing version downgrade from {current_version} to {release.version}"
        )

    if (
        current_version == release.version
        and current_archive == release.archive_id
    ):
        return spec, False

    updated, count = VERSION_RE.subn(
        f"Version:        {release.version}", spec, count=1
    )
    if count != 1:
        raise ValueError("could not update Version")
    updated, count = ARCHIVE_RE.subn(
        f"%global archive_id {release.archive_id}", updated, count=1
    )
    if count != 1:
        raise ValueError("could not update archive_id")
    updated, count = RELEASE_RE.subn("Release:        1%{?dist}", updated, count=1)
    if count != 1:
        raise ValueError("could not reset Release")
    return updated, True


def write_atomic(path: Path, content: str) -> None:
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.chmod(mode)
    os.replace(temporary_path, path)


def update_specs(repo_root: Path, check: bool = False) -> bool:
    releases = discover_releases()
    outdated = False

    for channel in CHANNELS:
        path = repo_root / channel.spec_path
        original = path.read_text(encoding="utf-8")
        updated, changed = render_updated_spec(original, releases[channel.name])
        release = releases[channel.name]

        if changed:
            outdated = True
            if check:
                print(
                    f"{channel.name}: update available "
                    f"({release.version}, {release.archive_id})"
                )
            else:
                write_atomic(path, updated)
                print(
                    f"{channel.name}: updated to "
                    f"{release.version} ({release.archive_id})"
                )
        else:
            print(f"{channel.name}: current at {release.version} ({release.archive_id})")

    return outdated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report outdated specs without modifying them",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (defaults to the script's parent repository)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        outdated = update_specs(args.repo_root.resolve(), check=args.check)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if args.check and outdated else 0


if __name__ == "__main__":
    raise SystemExit(main())
