# Android Studio COPR packages

This repository contains narrowly scoped Fedora packages for the three public
Android Studio release channels. It is intended to avoid enabling a broad
third-party repository that replaces or conflicts with Fedora packages.

| RPM package             | Channel                     | Command                 |
| ----------------------- | --------------------------- | ----------------------- |
| `android-studio`        | Stable                      | `android-studio`        |
| `android-studio-beta`   | Beta and release candidates | `android-studio-beta`   |
| `android-studio-canary` | Canary                      | `android-studio-canary` |

All three packages are x86_64-only and can be installed at the same time. Each
uses a separate application directory, launcher, icon, desktop entry, and
AppStream component.

## Installation

Enable the repository and install one or more channels:

```bash
sudo dnf copr enable licha/copr
sudo dnf install android-studio
sudo dnf install android-studio-beta
sudo dnf install android-studio-canary
```

Remove a channel normally with `dnf remove`. User configuration and Android
SDK files in the home directory are not owned by these RPMs and are therefore
not removed.

## Repository layout

Each directory under `packages/` is an independent COPR SCM package. COPR's
`rpkg` source builder downloads the pinned Google archive from `Source0`,
creates the source RPM, and builds it in the project's Fedora chroots.

The packages contain Google's binary distribution and bundled JetBrains
Runtime without rebuilding or replacing its components. Downloading and using
Android Studio is subject to the terms presented by Google on the
[Android Studio download page](https://developer.android.com/studio).

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

## Local validation

The checks require Python 3, RPM tools, `desktop-file-utils`, and AppStream:

```bash
python3 -m unittest discover -v

for spec in packages/*/*.spec; do
    rpmspec -P "$spec" >/dev/null
done

desktop-file-validate packages/*/*.desktop
appstreamcli validate --no-net packages/*/*.metainfo.xml
```

Full local builds are intentionally not part of routine validation because
each upstream archive is approximately 1.5 GB. COPR performs the source and
binary builds.

## Maintainer setup

1. Create a Fedora account and sign in to [COPR](https://copr.fedorainfracloud.org/).
2. Download the API configuration from the COPR API page and save it as
   `~/.config/copr` with mode `0600`.
3. Install `copr-cli` and configure the project and SCM packages:

```bash
sudo dnf install copr-cli
scripts/configure_copr.sh
```

The helper defaults to `licha/copr`, this GitHub repository, and current
Fedora x86_64 chroots. Alternative chroots can be supplied after the project
and clone URL:

```bash
scripts/configure_copr.sh licha/copr \
    https://github.com/kingjnr4/copr.git \
    fedora-44-x86_64 fedora-rawhide-x86_64
```

4. Add the complete contents of `~/.config/copr` as a GitHub Actions secret
   named `COPR_CONFIG`.
5. Run the `Build packages in COPR` workflow with `package=all` for the first
   build.

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
