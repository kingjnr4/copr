%undefine __brp_add_determinism
%global debug_package %{nil}
%global _build_id_links none
%global __strip /bin/true
%global __jar_repack %{nil}
%define __brp_check_rpaths %{nil}

%global sha256_x86_64 c820f8a56d192beb344cd8546b33713340130982b2fe6f90b837cb7df5979f20
%global sha256_aarch64 c771b64cc7691928f3177a018cac4833b3a014d22ff25de789076d440c7d4e4c
%global app_id com.jetbrains.IntelliJIDEA
%global __requires_exclude_from ^%{_libexecdir}/%{name}/.*$
%global __provides_exclude_from ^%{_libexecdir}/%{name}/.*$

Name:           intellij-idea
Version:        2026.2.3
Release:        1%{?dist}
Summary:        Open-source IDE for Java and Kotlin development
License:        Apache-2.0 AND GPL-2.0-only WITH Classpath-exception-2.0
URL:            https://www.jetbrains.com/idea/
ExclusiveArch:  x86_64 aarch64

# COPR creates one SRPM for all architectures. Always include both archives;
# choosing Source0 conditionally would leave ARM builds with an x86_64 payload.
Source0:        https://github.com/JetBrains/intellij-community/releases/download/idea/%{version}/idea-%{version}.tar.gz
Source1:        https://github.com/JetBrains/intellij-community/releases/download/idea/%{version}/idea-%{version}-aarch64.tar.gz
Source2:        %{app_id}.desktop
Source3:        %{app_id}.metainfo.xml

BuildRequires:  appstream
BuildRequires:  desktop-file-utils
BuildRequires:  python3

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
IntelliJ IDEA is an integrated development environment for Java and Kotlin.
This package contains JetBrains' official open-source Linux build and its
bundled JetBrains Runtime. Proprietary Ultimate features are not included.
A separate development JDK is needed to compile and run Java projects.

%prep
printf '%%s  %%s\n' '%{sha256_x86_64}' '%{SOURCE0}' \
    '%{sha256_aarch64}' '%{SOURCE1}' | sha256sum --check --strict
%setup -q -c -T
%ifarch aarch64
tar -xzf %{SOURCE1} --strip-components=1
%else
tar -xzf %{SOURCE0} --strip-components=1
%endif

# Reject a different edition, version, or native architecture in the archive.
python3 - <<'PY'
import json
import struct
from pathlib import Path

arch = "%{_target_cpu}"
expected_machine = {"x86_64": 62, "aarch64": 183}[arch]
for binary in ("jbr/bin/java", "bin/idea"):
    with Path(binary).open("rb") as source:
        header = source.read(20)
    assert header[:6] == b"\x7fELF\x02\x01", "expected a little-endian ELF64 binary"
    assert struct.unpack_from("<H", header, 18)[0] == expected_machine, "wrong runtime architecture"
info = json.loads(Path("product-info.json").read_text())
assert info["productCode"] == "IC", "expected the open-source IDEA edition"
assert info["version"] == "%{version}", "wrong upstream version"
expected_arch = {"x86_64": "amd64", "aarch64": "aarch64"}[arch]
assert any(item["os"] == "Linux" and item["arch"] == expected_arch for item in info["launch"]), "wrong launch architecture"
PY

%build
# This package installs JetBrains' prebuilt open-source distribution.

%install
install -d %{buildroot}%{_libexecdir}/%{name}
cp -a -- * %{buildroot}%{_libexecdir}/%{name}/

install -d %{buildroot}%{_bindir}
ln -s %{_libexecdir}/%{name}/bin/idea %{buildroot}%{_bindir}/%{name}

install -Dm0644 bin/idea.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
install -Dm0644 %{SOURCE2} \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -Dm0644 %{SOURCE3} \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml
install -d %{buildroot}%{_licensedir}/%{name}
cp -a LICENSE.txt NOTICE.txt license %{buildroot}%{_licensedir}/%{name}/

%check
test -x %{buildroot}%{_libexecdir}/%{name}/bin/idea
test -x %{buildroot}%{_libexecdir}/%{name}/jbr/bin/java
%{buildroot}%{_libexecdir}/%{name}/jbr/bin/java -version
desktop-file-validate \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
appstreamcli validate --no-net \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml

%files
%license %{_licensedir}/%{name}
%{_bindir}/%{name}
%{_libexecdir}/%{name}
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_metainfodir}/%{app_id}.metainfo.xml

%changelog
* Fri Oct 09 2026 licha <licha@users.noreply.github.com> - 2026.2.3-1
- Package official open-source IntelliJ IDEA builds for x86_64 and aarch64
