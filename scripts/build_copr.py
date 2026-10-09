#!/usr/bin/env python3
"""Submit package builds only to compatible, enabled COPR chroots."""

from __future__ import annotations

import argparse
import subprocess
import sys


PACKAGE_ARCHITECTURES = {
    "android-studio": ("x86_64",),
    "android-studio-beta": ("x86_64",),
    "android-studio-canary": ("x86_64",),
    "intellij-idea": ("x86_64", "aarch64"),
}


def select_chroots(package: str, chroots: list[str]) -> list[str]:
    architectures = PACKAGE_ARCHITECTURES[package]
    selected = sorted({
        chroot for chroot in chroots
        if any(chroot.endswith(f"-{arch}") for arch in architectures)
    })
    for arch in architectures:
        if not any(chroot.endswith(f"-{arch}") for chroot in selected):
            raise ValueError(
                f"{package} requires an enabled {arch} chroot; "
                "run scripts/configure_copr.sh"
            )
    return selected


def main() -> int:
    from copr.v3 import Client

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=PACKAGE_ARCHITECTURES)
    parser.add_argument("--project", default="licha/copr")
    args = parser.parse_args()
    if args.project.count("/") != 1:
        parser.error("project must be OWNER/PROJECT")
    owner, project = args.project.split("/")
    try:
        info = Client.create_from_config_file().project_proxy.get(owner, project)
        chroots = select_chroots(args.package, list(info.chroot_repos))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    command = ["copr-cli", "build-package", "--name", args.package]
    for chroot in chroots:
        command.extend(["--chroot", chroot])
    command.append(args.project)
    print(f"Building {args.package} in: {', '.join(chroots)}", flush=True)
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
