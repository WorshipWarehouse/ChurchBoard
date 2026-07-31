# Development and release builds

## Development environment

Requires Python 3.11 or newer:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Useful startup options:

```bash
python run.py --background
python run.py --page /display/main
```

Run the test suite:

```bash
python -m unittest discover -s tests
```

## Local release builds

Install build requirements in the active environment:

```bash
pip install -r build-requirements.txt
```

### macOS

Double-click `installers/macos/Build-macOS.command`, or run:

```bash
./installers/macos/build.sh
```

Output is written to `dist` as an architecture-specific drag-to-Applications `.dmg`.

### Windows

Install Python 3.11+ and Inno Setup 6, then run:

```powershell
.\installers\windows\Build-Windows.ps1
```

The versioned Setup executable is written to `dist\installers`.

### Linux

Run:

```bash
./installers/linux/build.sh
```

This produces a portable `.tar.gz` and a `.deb` for the current architecture.

## Automated releases

GitHub Actions runs tests on pushes and pull requests. The release workflow can be started manually for test artifacts. Pushing a tag such as `v0.1.4` builds macOS Intel, macOS Apple-silicon, Windows x64, and Linux packages and attaches them to a GitHub Release.

Before creating a release:

1. Update `app/version.py`.
2. Run tests and platform builds where available.
3. Commit the version change.
4. Tag the exact commit:

   ```bash
   git tag v0.1.4
   git push origin v0.1.4
   ```

Production macOS distribution should add Developer ID signing and Apple notarization secrets to the workflow. Production Windows distribution should similarly add an Authenticode signing certificate.

## Repository safety

`data/churchboard.json` is intentionally ignored because it can contain live Planning Center credentials and local integration addresses. Never force-add that file, copied browser profiles, screenshots containing secrets, or private keys.
