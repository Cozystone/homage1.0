# ATANOR Pricing Technical Model

ATANOR plans are runtime policies, not only payment tiers.

## Plans

| Plan | Price | Runtime Meaning |
| --- | ---: | --- |
| Free | $0 | Local-first, Seed Graph, low-resolution Cloud Brain hot fragments |
| Plus | $0 | Compute-backed access through opt-in Contributor Node |
| Pro | $49 | 24/7 cloud farming, larger Cloud Budget, background collection |
| On-Premise | $99 | High-end local machine, local hot shard snapshots, reduced cloud calls |
| Director | $199 | Contribution-exempt, cloud-hosted private cache/namespace |

## Plus Is Free But Compute-Backed

Plus does not require cash payment. It requires active contribution:

- public fragment validation
- source noise detection
- duplicate relation checks
- alias review
- freshness checks
- graph delta compression
- public source fetch planning

If contribution stops, Cloud Budget falls back toward Free.

## Cloud Budget Dimensions

Each plan controls:

- cloud fragment requests per day
- max cloud nodes per query
- max cloud edges per query
- max cloud bytes per query
- deep cloud search per day
- freshness tier
- cloud pack access level
- background farming
- contributor multiplier
- cache size limit
- snapshot limit

Code:

- `cloud_budget_for_plan()`
- `brain_balance_for_plan()`

## Brain Balance

Brain Balance uses:

- plan
- remaining Cloud Budget
- Local Brain strength
- Cloud Brain coverage
- Seed Graph stability
- Working Memory capacity
- Epistemic confidence
- provider health
- contribution state

Free may visually show high Cloud need when Local Brain is weak, but its Cloud
resolution remains low-cost. Director may use more cloud without contribution
because it is explicitly paid.

## Margin Reporting

Report infrastructure gross margin only as infrastructure gross margin.

Do not claim company net margin from infrastructure estimates. Company net margin
must include support, taxes, payment fees, app store fees, engineering, legal,
security, compliance, and operations.
