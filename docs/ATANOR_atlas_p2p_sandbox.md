# ATANOR Atlas P2P Sandbox

Status: proof-only local simulator.

Atlas P2P Sandbox simulates future ATANOR peer and cartridge exchange without
opening sockets, using libp2p, connecting to public peers, uploading to cloud, or
exporting private raw data. Accepted exchanges are safe only as
working-memory/candidate proposals.

## Safety Boundaries

- No real P2P.
- No public WAN.
- No cloud upload.
- No raw private payload export.
- No Local Brain write.
- No production mutation.
- No candidate promotion.
- No privacy-zero claim; residual risk must be measured by later gates.

## Local Models

- `SandboxPeer`: local peer fixture with trust, privacy grade, online state, and
  capabilities.
- `SandboxCartridge`: metadata-only cartridge fixture with public-only flag,
  privacy grade, license hint, semantic tags, and payload summary.
- `ExchangeResult`: local exchange verdict. It cannot mark data safe for Local
  Brain and cannot report real P2P usage.

## Proof Cases

- Trusted public peer with open-license public cartridge is accepted for
  working-memory/candidate proposal only.
- Low-trust peer is rejected.
- Private or raw cartridge is rejected.
- Unknown license is rejected.
- Private peer export is rejected.

## Future Gates

- Promotion gate before any store promotion.
- Privacy gate before any data sharing.
- Identity gate before real peer identity.
- Real P2P gate before sockets or libp2p.
- Signed cartridge gate before accepting external cartridge metadata.

This sandbox is intentionally smaller than real Atlas networking. Its purpose is
to keep future P2P integration honest while preserving local-only safety.
