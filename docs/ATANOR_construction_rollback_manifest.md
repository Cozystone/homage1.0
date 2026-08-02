# ATANOR Construction Rollback Manifest v0

Status: rollback planning only.

Every self-grown construction promotion manifest receives a rollback manifest id. The rollback manifest records which candidate ids would need to be disabled and which route scopes would be affected if a future production activation were reverted.

In v0 rollback manifests are deliberately non-executable:

- `executable=false`
- no production state is changed
- no candidate is disabled
- no Local Brain write occurs
- no verified store mutation occurs

The purpose is to make rollback planning mandatory before any future activation work exists. A later production gate must prove that the operator can inspect, sign, and execute rollback separately from promotion.

UTF-8 cleanup note: rollback planning remains a non-executable safety artifact after cleanup. A rollback manifest is required before any future activation dry-run can be considered.
