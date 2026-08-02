# ATANOR UI Quality Loop

ATANOR's release risk is not only code failure. It is also product drift:
broken Korean, preview states that look live, raw identifiers in UI, local
paths in public docs, and old mock labels that make the project feel less
trustworthy.

Run the UI quality audit before public release work:

```powershell
npm run audit:ui
```

The audit writes:

```text
reports/ui-quality/latest.md
```

It checks:

- invalid UTF-8 and common mojibake.
- replacement characters.
- local absolute paths.
- secret/API-key-looking strings.
- overclaiming global-network phrases.
- user-facing node/peer/device identifiers.
- lingering mock, stub, and placeholder labels.

Severity levels:

- `BLOCKER`: must be fixed before public release.
- `HIGH`: likely to damage user trust.
- `MEDIUM`: should be reviewed before release.
- `LOW`: polish issue.

The audit is intentionally conservative. Some internal code identifiers may be
allowed after review, but public-facing UI and documentation should stay clean,
privacy-safe, and honest about what is real versus preview.
