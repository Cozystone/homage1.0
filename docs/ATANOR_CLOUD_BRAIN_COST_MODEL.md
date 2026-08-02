# ATANOR Cloud Brain Cost Model

The cost model is explicit and configurable.

Code:

- `packages/cost_model/pricing_defaults.json`
- `packages/cost_model/cost_model/model.py`
- `/api/neuro/cost-estimate`
- `/api/neuro/cost-scenarios`
- `/api/neuro/cloud-budget/{plan}`

## Inputs

`CostModel` accepts:

- provider: `cloudflare | aws | hybrid`
- api requests
- worker invocations
- db reads
- db writes
- object storage GB
- object gets
- object puts
- egress GB
- logs GB
- queue ops
- contributor tasks
- hot fragment hits
- cold fragment fetches

## Scenarios

Initial scenario assumptions:

| Plan | Optimistic | Base | Risk |
| --- | ---: | ---: | ---: |
| Free | $0.05 | $0.10 | $0.20 |
| Plus | $0.05 | $0.20 | $1.00 |
| Pro | $4 | $5 | $8 |
| On-Premise | $2 | $3 | $5 |
| Director | $29 | $35 | $50 |

Revenue:

| Plan | Revenue |
| --- | ---: |
| Free | $0 |
| Plus | $0 |
| Pro | $49 |
| On-Premise | $99 |
| Director | $199 |

Default distribution:

- Free 40%
- Plus 45%
- Pro 10%
- On-Premise 4%
- Director 1%

## Important Margin Rule

Infrastructure gross margin is not company net margin.

The model intentionally outputs:

- `blended_arpu`
- `blended_infra_cost`
- `infra_gross_margin`
- `company_net_margin: null`

Company net margin must be calculated separately.

## Why Contributor Nodes Matter

Contributor Nodes keep cloud cost low by doing:

- public source fetch
- public fragment candidate extraction
- source noise detection
- duplicate relation check
- public alias review
- graph delta compression
- freshness check

The broker does:

- assignment
- validation
- result collection
- trust/provenance ledger
- credit ledger
- hot fragment promotion
- shard registry updates

The cloud provider should not become a crawler, parser cluster, graph database,
or GPU inference platform.

## UI Binding

The ATANOR app now surfaces the following runtime fields:

- Provider: `cloud_provider` and endpoint class
- Broker State: `remote_connected`, `local_broker_mode`, or fallback state
- Cloud Budget: plan and effective public fragment request budget
- Brain Balance: planned/actual Local vs Cloud context ratio
- Contribution State: contributor task and credit ledger preview

Verified Cloudflare remote mode:

```text
cloud_provider=cloudflare
cloud_mode=remote
broker_state=remote_connected
fragment_store=kv (dev fallback; R2 not enabled yet)
```

Budget results are operational limits, not product pricing promises. The current
`Plus` plan remains a dev placeholder with zero revenue in the model. Before
commercial rollout, update `packages/cost_model/pricing_defaults.json` with the
real billing plan and re-run `/api/neuro/cost-scenarios`.
