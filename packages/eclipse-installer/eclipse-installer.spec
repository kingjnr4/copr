%undefine __brp_add_determinism
%global debug_package %{nil}
%global _build_id_links none
%global __strip /bin/true
%global __jar_repack %{nil}
%define __brp_check_rpaths %{nil}

%global eclipse_release 2026-09
%global sha512_x86_64 4eb8e08c76c4ceced064d2c39f2f6a3648948ac471a6f6b05ccd05b5a3762d933efd576b33ac58a3ae494d7d740b2c006ab36d4cc6cd992a69eb2a04b4a55973
%global sha512_aarch64 b0d6fbb638d1338bd317f6d2072ff7574f3f4ab922c874689fe2a6493f5029f3dbc5dc2a05e31299894d23bcefeada40a8c58f76f9f09430cf0ff1bbfcb8ec80
%global app_id org.eclipse.Installer
%global __requires_exclude_from ^%{_libexecdir}/%{name}/.*$
%global __provides_exclude_from ^%{_libexecdir}/%{name}/.*$

Name:           eclipse-installer
Version:        2026.09
Release:        2%{?dist}
Summary:        Install Eclipse IDE packages using the official Eclipse Installer
License:        EPL-2.0 AND GPL-2.0-only WITH Classpath-exception-2.0
URL:            https://www.eclipse.org/downloads/
ExclusiveArch:  x86_64 aarch64

# Include both architectures in the shared source RPM, then extract only the target.
Source0:        https://download.eclipse.org/oomph/epp/%{eclipse_release}/R/eclipse-inst-jre-linux64.tar.gz
Source1:        https://download.eclipse.org/oomph/epp/%{eclipse_release}/R/eclipse-inst-jre-linux-aarch64.tar.gz
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
Requires:       libstdc++
Requires:       webkit2gtk4.1
Requires:       xdg-utils
Requires:       zlib

%description
The official Eclipse Installer (Oomph) lets you choose and install Eclipse IDE
packages in your home directory. This package includes Eclipse's bundled Java
runtime. IDE installations, workspaces, and the user's shared bundle pool are
managed separately from this RPM. Run the installer as a normal user, not root.

%prep
printf '%%s  %%s\n' '%{sha512_x86_64}' '%{SOURCE0}' \
    '%{sha512_aarch64}' '%{SOURCE1}' | sha512sum --check --strict
%setup -q -c -T
%ifarch aarch64
tar -xzf %{SOURCE1} --strip-components=1
%else
tar -xzf %{SOURCE0} --strip-components=1
%endif

# Verify the native launcher, bundled runtime, product, and release before packaging.
python3 - <<'PY'
import struct
from pathlib import Path

arch = "%{_target_cpu}"
expected_machine = {"x86_64": 62, "aarch64": 183}[arch]
ini = Path("eclipse-inst.ini").read_text().splitlines()
runtime = Path(ini[ini.index("-vm") + 1])
assert runtime.match(f"plugins/org.eclipse.justj.*.linux.{arch}_*/jre/bin/java"), "unexpected bundled runtime"
for binary in (Path("eclipse-inst"), runtime):
    with binary.open("rb") as source:
        header = source.read(20)
    assert header[:6] == b"\x7fELF\x02\x01", "expected a little-endian ELF64 binary"
    assert struct.unpack_from("<H", header, 18)[0] == expected_machine, "wrong native architecture"
config = Path("configuration/config.ini").read_text().splitlines()
assert "eclipse.product=org.eclipse.oomph.setup.installer.product" in config, "wrong Eclipse product"
assert "oomph.setup.product.version.filter=.*\\\\.%{eclipse_release}" in config, "wrong Eclipse release"
PY

%build
# Preserve Eclipse's prebuilt distribution and all bundled license notices.

%install
install -d %{buildroot}%{_libexecdir}/%{name}
cp -a -- * %{buildroot}%{_libexecdir}/%{name}/
install -d %{buildroot}%{_bindir}
ln -s %{_libexecdir}/%{name}/eclipse-inst %{buildroot}%{_bindir}/%{name}
install -Dm0644 icon.xpm \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/%{app_id}.xpm
install -Dm0644 %{SOURCE2} \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -Dm0644 %{SOURCE3} \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml
install -d %{buildroot}%{_licensedir}/%{name}
cp -a features/org.eclipse.oomph.setup.installer_*/license.html \
    %{buildroot}%{_licensedir}/%{name}/

%check
test -x %{buildroot}%{_libexecdir}/%{name}/eclipse-inst
%{buildroot}%{_libexecdir}/%{name}/plugins/org.eclipse.justj.*.linux.%{_target_cpu}_*/jre/bin/java -version
desktop-file-validate \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
appstreamcli validate --no-net \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml

%files
%license %{_licensedir}/%{name}
%{_bindir}/%{name}
%{_libexecdir}/%{name}
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/256x256/apps/%{app_id}.xpm
%{_metainfodir}/%{app_id}.metainfo.xml

%changelog
* Mon Oct 19 2026 licha <licha@users.noreply.github.com> - 2026.09-2
- Match the SWT Wayland app ID so Plasma uses the installer icon

* Mon Oct 19 2026 licha <licha@users.noreply.github.com> - 2026.09-1
- Package the official Eclipse Installer for x86_64 and aarch64
