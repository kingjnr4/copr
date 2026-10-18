# Fedora COPR packages

## Installation

Enable the repository:

```bash
sudo dnf copr enable licha/copr
```

Install whichever packages you need:

| Package | Architecture | Install command |
| --- | --- | --- |
| Android Studio Stable | x86_64 | `sudo dnf install android-studio` |
| Android Studio Beta / RC | x86_64 | `sudo dnf install android-studio-beta` |
| Android Studio Canary | x86_64 | `sudo dnf install android-studio-canary` |
| IntelliJ IDEA (open source) | x86_64, aarch64 | `sudo dnf install intellij-idea` |
| Eclipse Installer | x86_64, aarch64 | `sudo dnf install eclipse-installer` |

Launch from your application menu or run the package name in a terminal.

### Eclipse Installer

This is the official [Eclipse Installer](https://www.eclipse.org/downloads/),
including its Java runtime. Run `eclipse-installer` **without sudo**, choose an
Eclipse IDE edition, and select an installation folder in your home directory.
The IDEs it installs are managed by Eclipse, separately from the installer RPM.

### IntelliJ IDEA

This is JetBrains' official open-source build, without proprietary Ultimate
features or student-license activation. It includes a runtime for the IDE;
install a development JDK matching your project's requirements separately:

```bash
sudo dnf install java-21-openjdk-devel
```

### Updates and removal

Update RPM packages with `sudo dnf upgrade`. Do not run applications as root
to update their RPM-owned files.

Remove a package with `sudo dnf remove PACKAGE`. Projects, user settings,
plugins, Android SDKs, and Eclipse IDEs installed in your home directory are
not removed.
