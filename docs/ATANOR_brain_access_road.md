# ATANOR Brain Access Road

Local Brain and Cloud Brain are not raw databases exposed to agents. They are
reached through audited roads.

## Local Brain

- redacted summary read is allowed with scope;
- user-approved context read is gated;
- memory writes become candidate drafts;
- direct write is rejected;
- raw private memory cannot be sent to browser/API/MCP tools.

## Cloud Brain

- verified read summary is allowed for non-private context;
- candidate writes are draft-only;
- evidence attach is draft-only;
- production promotion becomes an approval request;
- production direct write is rejected.

Every request creates an audit record and returns `mutation_performed=false` in
proof paths.
