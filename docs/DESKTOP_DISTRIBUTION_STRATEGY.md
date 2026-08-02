# ATANOR Desktop Distribution Strategy

ATANOR ships as a local-first desktop application with a Python FastAPI sidecar, a Tauri shell, and the Ghost Shell / Payload Vault runtime. Public distribution must use the native trust system of each operating system. Self-signed certificates are acceptable only for local developer machines.

## Distribution Matrix

| Platform | Primary public path | Secondary path | Local dev path |
| --- | --- | --- | --- |
| Windows | Microsoft Store MSIX | Trusted-signed EXE/MSI | Self-signed EXE/MSI |
| macOS | Developer ID signed + notarized DMG | Mac App Store candidate | Unsigned/ad-hoc local bundle |
| Linux | AppImage/deb/rpm | Package repositories | Local AppImage |

## Windows

### Public Store Path

Use Microsoft Partner Center and submit an MSIX package. Microsoft re-signs MSIX packages distributed through the Store, which is the cleanest path for SmartScreen and Smart App Control friction.

Public Windows release goals:

- package as Store-compatible MSIX;
- avoid self-signed certificates;
- keep all executable payloads signed;
- keep the sidecar binary bundled and versioned with the Tauri app;
- route updates through Store or a trusted updater channel, not a raw unsigned installer.

### Non-Store Path

Use Azure Trusted Signing or an OV/EV certificate from a CA in the Microsoft Trusted Root Program. New hashes can still need reputation buildup, so this path is less frictionless than Store MSIX.

Current repo status:

- `scripts/prepare_windows_signing.ps1` and `scripts/sign_windows_artifact.ps1` are developer-only self-signing tools.
- They are not a public distribution solution.

## macOS

ATANOR supports two macOS release tracks.

### Track A: Developer ID DMG

This is the preferred power-user path for ATANOR because it allows the local sidecar, local networking, file watching, and Payload Vault behavior with fewer App Sandbox constraints than the Mac App Store.

Required Apple account assets:

- Apple Developer Program membership;
- `Developer ID Application` certificate;
- Apple ID app-specific password or App Store Connect API credentials for notarization;
- Team ID / provider short name when needed.

Repo files:

- `src-tauri/tauri.macos.conf.json`
- `src-tauri/Entitlements.plist`
- `src-tauri/Info.macos.plist`
- `scripts/macos/preflight.sh`
- `scripts/macos/verify_bundle.sh`
- `.github/workflows/macos-distribution.yml`

CI secrets:

- `APPLE_CERTIFICATE`: base64-encoded `.p12` certificate
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_SIGNING_IDENTITY`: for example `Developer ID Application: Publisher Name (TEAMID)`
- `APPLE_ID`
- `APPLE_PASSWORD`: app-specific password
- `APPLE_TEAM_ID`
- `APPLE_PROVIDER_SHORT_NAME`: optional unless Apple account has multiple teams
- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

Build command on macOS:

```bash
bash scripts/macos/preflight.sh developer-id
python3 scripts/build_sidecar.py
npm run tauri -- build --config src-tauri/tauri.macos.conf.json --bundles app,dmg
bash scripts/macos/verify_bundle.sh
```

Expected output:

- `src-tauri/target/release/bundle/macos/ATANOR.app`
- `src-tauri/target/release/bundle/dmg/ATANOR_*.dmg`

### Track B: Mac App Store Candidate

This path is for a future consumer-friendly build. The App Store imposes sandboxing and review constraints, so the fully autonomous local-learning operator mode may need reduced capabilities or explicit user-selected file access.

Required Apple account assets:

- Apple Developer Program membership;
- `Apple Distribution` certificate;
- `3rd Party Mac Developer Installer` certificate;
- App Store Connect app record and bundle identifier reservation.

Repo files:

- `src-tauri/tauri.appstore.conf.json`
- `src-tauri/Entitlements.appstore.plist`
- `src-tauri/Info.appstore.plist`
- `scripts/macos/package_appstore_pkg.sh`
- `.github/workflows/macos-distribution.yml`

CI secrets:

- `APPLE_APPSTORE_CERTIFICATE`: base64-encoded `.p12` certificate
- `APPLE_APPSTORE_CERTIFICATE_PASSWORD`
- `APPLE_APPSTORE_SIGNING_IDENTITY`: for example `Apple Distribution: Publisher Name (TEAMID)`
- `APPLE_INSTALLER_SIGNING_IDENTITY`: for example `3rd Party Mac Developer Installer: Publisher Name (TEAMID)`
- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

Build command on macOS:

```bash
bash scripts/macos/preflight.sh app-store
python3 scripts/build_sidecar.py
npm run tauri -- build --config src-tauri/tauri.appstore.conf.json --bundles app
bash scripts/macos/package_appstore_pkg.sh
```

Expected output:

- `dist-artifacts/macos-appstore/ATANOR-macOS-AppStore.pkg`

## Release Workflow

GitHub Actions workflow:

```text
.github/workflows/macos-distribution.yml
```

Manual dispatch options:

- `developer-id`: build signed/notarized DMG.
- `app-store`: build App Store candidate PKG.
- `both`: run both release tracks.

The workflow intentionally fails early if Apple signing secrets are absent. That is better than silently producing an unsigned artifact that Gatekeeper will block.

## Engineering Notes

- Developer ID builds do not enable App Sandbox by default.
- App Store builds do enable App Sandbox.
- The Python sidecar is kept as a bundled external binary through Tauri `externalBin`.
- The app allows local networking because ATANOR uses a localhost sidecar bridge.
- macOS builds must run on macOS because Apple signing and notarization tooling require Xcode command line tools.

## References

- Microsoft code signing options: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- Apple Developer ID: https://developer.apple.com/developer-id/
- Apple macOS distribution: https://developer.apple.com/macos/distribution/
- Tauri macOS signing: https://v2.tauri.app/distribute/sign/macos/
- Tauri App Store packaging: https://v2.tauri.app/distribute/app-store/
