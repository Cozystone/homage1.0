# Windows Store MSIX Packaging

ATANOR has a reserved Microsoft Partner Center product:

- Product name: `ATANOR`
- Store ID: `9PBN2HNPWQ7V`
- Package/Identity/Name: `AnseokKim.ATANOR`
- Package/Identity/Publisher: `CN=BAE07AF0-E1EB-4107-96CD-CACBEBF82C23`
- Publisher display name: `Anseok Kim`
- Package family name: `AnseokKim.ATANOR_ram6gtk9ph338`
- Store URL: `https://apps.microsoft.com/detail/9PBN2HNPWQ7V`

## Build Command

From the repository root:

```powershell
npm run store:msix -- -SkipDesktopBuild
```

For a clean production rebuild first:

```powershell
npm run store:msix
```

The command stages the existing Tauri desktop executable and Python sidecar into a Store identity-matched MSIX package.

## Outputs

```text
dist-artifacts/windows-store/ATANOR_0.1.0.0_x64.msix
dist-artifacts/windows-store/ATANOR_0.1.0.0_x64.msixupload
```

Upload the `.msixupload` file in Partner Center after starting a submission for the `ATANOR` product.

## Important Notes

- The package is a Win32 / Desktop Bridge style package and declares `runFullTrust`.
- Partner Center may require the account to be authorized for restricted desktop capabilities. If package validation rejects `runFullTrust`, request the appropriate Store capability authorization or switch the first public listing to the EXE/MSI Store path while keeping MSIX as the target path.
- The local signing certificate is self-signed with the exact Partner Center publisher identity. This is for Store upload identity matching only. It is not a public trust certificate and should not be used as a public direct-download signing solution.
- Microsoft re-signs accepted Store MSIX packages after certification.

## Source Files

- `packaging/windows-msix/store-identity.json`
- `packaging/windows-msix/AppxManifest.xml.template`
- `scripts/build_store_msix.ps1`
- `package.json` script: `store:msix`

## Partner Center Flow

1. Open `ATANOR` in Partner Center.
2. Click `?쒖텧 ?쒖옉`.
3. Complete listing metadata, pricing, age rating, privacy URL, and package requirements.
4. Upload `ATANOR_0.1.0.0_x64.msixupload`.
5. Resolve Partner Center package validation warnings.
6. Submit for certification only after package validation passes.
