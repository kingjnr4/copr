#!/usr/bin/env bash
set -euo pipefail

project=${1:-licha/copr}
clone_url=${2:-https://github.com/kingjnr4/copr.git}
shift "$(( $# > 0 ? 1 : 0 ))"
shift "$(( $# > 0 ? 1 : 0 ))"

if [ "$#" -gt 0 ]; then
    chroots=("$@")
else
    chroots=(
        fedora-43-x86_64
        fedora-44-x86_64
        fedora-45-x86_64
        fedora-rawhide-x86_64
    )
fi

if ! command -v copr-cli >/dev/null 2>&1; then
    printf 'error: copr-cli is required\n' >&2
    exit 1
fi

project_name=${project#*/}
project_args=(
    --enable-net off
    --appstream on
    --follow-fedora-branching on
)
for chroot in "${chroots[@]}"; do
    project_args+=(--chroot "$chroot")
done

description='Focused Fedora packages for Android Studio stable, beta, and canary.'
instructions="Enable with: sudo dnf copr enable $project"

if copr-cli get "$project" >/dev/null 2>&1; then
    copr-cli modify "$project" \
        "${project_args[@]}" \
        --description "$description" \
        --instructions "$instructions"
else
    copr-cli create "$project_name" \
        "${project_args[@]}" \
        --description "$description" \
        --instructions "$instructions"
fi

packages=(android-studio android-studio-beta android-studio-canary)
for package in "${packages[@]}"; do
    package_args=(
        "$project"
        --name "$package"
        --clone-url "$clone_url"
        --commit main
        --subdir "packages/$package"
        --spec "$package.spec"
        --type git
        --method rpkg
        --webhook-rebuild off
        --max-builds 3
        --timeout 10800
    )

    if copr-cli get-package "$project" --name "$package" >/dev/null 2>&1; then
        copr-cli edit-package-scm "${package_args[@]}"
    else
        copr-cli add-package-scm "${package_args[@]}"
    fi
done

printf 'Configured %s with packages: %s\n' "$project" "${packages[*]}"
