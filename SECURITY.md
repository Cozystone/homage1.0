# Security and Privacy Policy

ATANOR is designed around a strict privacy boundary: private memory stays on
the user's device, while the Cloud Brain accepts only opt-in public graph
fragments.

## Do Not Report Publicly

If you discover a vulnerability that could expose private data, secrets,
Payload Vault content, local file paths, raw IP addresses, node identifiers, or
Cloud Brain broker credentials, do not publish it in a public issue. Contact
the maintainers privately through the repository security channel once it is
available.

## Privacy Guarantees Targeted By This Release

- Private Local Brain data is not uploaded to Cloud Brain.
- Payload Vault raw records are not uploaded.
- Cloud fragments must declare `privacy_classification=public_only`.
- Cloud fragments must declare `raw_payload_exported=false`.
- Raw IP addresses and exact locations must not be returned to user-facing UI.
- Contributor Node participation must be opt-in.

## Current Limitations

- Multi-peer verification is not complete.
- The Cloudflare broker is an alpha runtime and currently uses KV for small
  public fragments unless R2 is configured.
- Desktop signing and updater trust must be verified before broad distribution.
