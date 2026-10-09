# Focused IDE COPR packages

This repository contains narrowly scoped Fedora packages for the three public
Android Studio release channels and official IntelliJ IDEA open-source builds.
It is intended to avoid enabling a broad third-party repository that replaces
or conflicts with Fedora packages.

| RPM package            | Channel                     | Command                |
| ---------------------- | --------------------------- | ---------------------- |
| `android-studio`        | Stable                      | `android-studio`        |
| `android-studio-beta`   | Beta and release candidates | `android-studio-beta`   |
| `android-studio-canary` | Canary                      | `android-studio-canary` |
| `intellij-idea`         | Stable open-source build    | `intellij-idea`         |

Android Studio packages are x86_64-only. IntelliJ IDEA supports x86_64 and
aarch64 (ARM64), matching JetBrains' official Linux open-source archives.
All packages can be installed at the same time. Each uses a separate application
directory, launcher, icon, desktop entry, and AppStream component.

## Installation

Enable the repository and install one or more IDE packages:

```bash
sudo dnf copr enable licha/copr
sudo dnf install android-studio
sudo dnf install android-studio-beta
sudo dnf install android-studio-canary
sudo dnf install intellij-idea
```

Remove a package normally with `dnf remove`. Projects, user configuration,
user-installed plugins, and Android SDK files in the home directory are not
owned by these RPMs and are therefore not removed.

### IntelliJ IDEA for coursework

This package uses [JetBrains' official open-source GitHub releases](https://github.com/JetBrains/intellij-community/releases),
not the proprietary unified distribution from the JetBrains download site.
The open-source build provides core Java and Kotlin development functionality,
but does not include proprietary Ultimate features or student-license activation
of those features. Use JetBrains' official installer or Toolbox separately if
your class requires Ultimate functionality.

The bundled JetBrains Runtime runs the IDE. Install a separate development JDK
matching your class requirements, then select it as the project SDK in IntelliJ.
For example, if your class requires Java 21:

```bash
sudo dnf install java-21-openjdk-devel
```

IDE updates are delivered through `dnf upgrade`; do not run the IDE as root to
apply its built-in updater to the RPM-owned installation.

## Repository layout

Each directory under `packages/` is an independent COPR SCM package. COPR's
`rpkg` source builder downloads the pinned upstream archives from the spec,
creates the source RPM, and builds it in the project's Fedora chroots.

The Android Studio packages contain Google's binary distribution and bundled
JetBrains Runtime without rebuilding or replacing its components. Downloading and using
Android Studio is subject to the terms presented by Google on the
[Android Studio download page](https://developer.android.com/studio).

IntelliJ IDEA contains JetBrains' official open-source binary distribution,
including its unmodified bundled runtime and third-party license notices.
Both Linux archives are included in a single source RPM: checksums are pinned
in the spec and checked before extraction, and each binary build selects only
the archive for its target architecture. Preparation also verifies the edition,
version, launch metadata, and native launcher/runtime architecture.
The IDE's primary license is Apache-2.0;
the bundled runtime and libraries retain their respective licenses.

## Updating releases

`scripts/update_android_studio.py` reads Google's stable and preview download
pages. It identifies releases using Google's explicit stable, beta, and canary
download categories, then updates the matching spec's numeric version and
archive identifier. It refuses ambiguous results, mislabeled preview builds,
and version downgrades.

Run it locally with:

```bash
python3 scripts/update_android_studio.py --check
python3 scripts/update_android_studio.py
```

The scheduled `update.yml` workflow runs daily. After tests and RPM parsing
pass, it commits changed specs directly to `main` and dispatches a COPR build
for only the changed channels. Explicit dispatch is needed because GitHub does
not trigger new workflow runs from commits pushed with `GITHUB_TOKEN`.

`scripts/update_intellij_idea.py` uses GitHub's release API to discover stable
`idea/*` open-source releases, excluding PyCharm, drafts, and prereleases. It
requires both Linux archives and SHA-256 asset digests, rejects version
downgrades, and refuses checksum changes for an already-pinned version pending
manual review. It updates the version and both checksums together.

```bash
python3 scripts/update_intellij_idea.py --check
python3 scripts/update_intellij_idea.py
```

The independent `update-intellij.yml` workflow checks daily at 06:43 UTC,
validates both architecture variants, commits updates, and explicitly requests
an IntelliJ COPR build only when the spec changes. Both updater workflows
share a concurrency group so their pushes to `main` cannot race. The GitHub
API is authenticated in Actions; locally, `GH_TOKEN` is optional.

## Local validation

The checks require Python 3, RPM tools, `desktop-file-utils`, and AppStream:

```bash
python3 -m unittest discover -v

for spec in packages/*/*.spec; do
    rpmspec -P "$spec" >/dev/null
done
rpmspec --target aarch64 -P packages/intellij-idea/intellij-idea.spec >/dev/null

desktop-file-validate packages/*/*.desktop
appstreamcli validate --no-net packages/*/*.metainfo.xml
```

Full local builds are intentionally not part of routine validation because
upstream archives are large (approximately 0.9 GB per IntelliJ architecture,
and 1.5 GB per Android Studio channel). COPR performs the source and binary builds.

## Maintainer setup

1. Create a Fedora account and sign in to [COPR](https://copr.fedorainfracloud.org/).
2. Download the API configuration from the COPR API page and save it as
   `~/.config/copr` with mode `0600`.
3. Install `copr-cli` and configure the project and SCM packages:

```bash
sudo dnf install copr-cli
scripts/configure_copr.sh
```

The helper defaults to `licha/copr`, this GitHub repository, and Fedora
43, 44, 45, and Rawhide chroots for both x86_64 and aarch64. Alternative chroots
can be supplied after the project and clone URL:

```bash
scripts/configure_copr.sh licha/copr \
    https://github.com/kingjnr4/copr.git \
    fedora-44-x86_64 fedora-44-aarch64 \
    fedora-rawhide-x86_64 fedora-rawhide-aarch64
```

4. Add the complete contents of `~/.config/copr` as a GitHub Actions secret
   named `COPR_CONFIG`.
5. Run the `Build packages in COPR` workflow with `package=all` for the first
build.

For an existing installation, run the setup helper after the new package is
pushed to `main`, then select `package=intellij-idea` for its first build.
The build workflow uses `scripts/build_copr.py` to select compatible enabled
chroots dynamically: Android Studio builds only on x86_64, while IntelliJ
builds on x86_64 and aarch64. It fails early if a required architecture has
no enabled chroot. To submit the same build locally:

```bash
python3 scripts/build_copr.py intellij-idea
```

The project setup disables network access during binary builds, enables
AppStream metadata and Fedora branching, and keeps three builds per package to
limit storage use. Source downloads still occur in COPR's separate SCM source
builder.

## Why not Packit?

Packit is useful when an upstream source repository needs release and Fedora
dist-git automation. Here the repository packages large, externally published
binary archives. COPR's SCM source builder handles that directly, while the
small channel-aware updater supplies the missing release discovery. This
avoids Packit's archive-generation layer and additional service permissions.
