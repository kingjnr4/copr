%undefine __brp_add_determinism
%global debug_package %{nil}
%global _build_id_links none
%global __strip /bin/true
%global __jar_repack %{nil}
%define __brp_check_rpaths %{nil}

%global archive_id rabbit2-canary1
%global app_id com.google.AndroidStudio.Canary
%global __requires_exclude_from ^%{_libexecdir}/%{name}/.*$
%global __provides_exclude_from ^%{_libexecdir}/%{name}/.*$

Name:           android-studio-canary
Version:        2026.2.2.1
Release:        1%{?dist}
Summary:        Canary channel of the official Android development IDE
License:        LicenseRef-Proprietary
URL:            https://developer.android.com/studio/preview
ExclusiveArch:  x86_64

Source0:        https://dl.google.com/dl/android/studio/ide-zips/%{version}/android-studio-%{archive_id}-linux.tar.gz
Source1:        %{app_id}.desktop
Source2:        %{app_id}.metainfo.xml

BuildRequires:  appstream
BuildRequires:  desktop-file-utils

Requires:       alsa-lib
Requires:       fontconfig
Requires:       freetype
Requires:       glibc
Requires:       gtk3
Requires:       hicolor-icon-theme
Requires:       libX11
Requires:       libXext
Requires:       libXi
Requires:       libXrender
Requires:       libXtst
Requires:       libsecret
Requires:       which
Requires:       xdg-utils
Requires:       zlib

%description
Android Studio is the official integrated development environment for
Android application development. This package contains Google's canary
channel x86_64 Linux distribution and its bundled JetBrains Runtime.

It can be installed alongside the stable and beta channel packages.

%prep
%autosetup -n android-studio

%build
# This package installs Google's prebuilt distribution.

%install
install -d %{buildroot}%{_libexecdir}/%{name}
cp -a -- * %{buildroot}%{_libexecdir}/%{name}/

install -d %{buildroot}%{_bindir}
ln -s %{_libexecdir}/%{name}/bin/studio %{buildroot}%{_bindir}/%{name}

install -Dm0644 bin/studio.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
install -Dm0644 %{SOURCE1} \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -Dm0644 %{SOURCE2} \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml
install -Dm0644 LICENSE.txt \
    %{buildroot}%{_licensedir}/%{name}/LICENSE.txt

%check
desktop-file-validate \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
appstreamcli validate --no-net \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml

%files
%license %{_licensedir}/%{name}/LICENSE.txt
%{_bindir}/%{name}
%{_libexecdir}/%{name}
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_metainfodir}/%{app_id}.metainfo.xml

%changelog
%autochangelog
