# ATANOR AWS Cloud Brain Broker

Status: implementation package prepared, AWS deployment requires user login/2FA/payment verification.

Positioning: AWS is preserved as an enterprise-compatible remote provider option.
For consumer/global edge Cloud Brain, Cloudflare is the preferred low-cost first
candidate. Do not treat AWS as the only Cloud Brain path.

## Objective

Move ATANOR from `local_broker_mode` toward the first real remote Cloud Brain Broker:

- contributor node registration
- heartbeat
- safe public task polling
- public task result submission
- pending internal contribution credits
- tiny public fragment put/query
- no private Local Brain upload

For commercial cost control, AWS should remain:

- enterprise/customer VPC option
- backup provider
- remote provider option
- compliance-oriented deployment path

It should not become the default centralized crawler, parser, graph database, or
GPU inference platform.

## Architecture

The prepared stack is intentionally small and serverless:

- API Gateway HTTP API
- one Python 3.11 Lambda function
- four DynamoDB tables
- one private S3 bucket for future larger public fragments
- CloudWatch logs with 7-day retention
- optional AWS Budgets at 1, 5, and 10 USD

Avoided by design:

- EC2
- Neptune
- OpenSearch
- RDS
- ECS/EKS
- SageMaker
- Bedrock
- GPU workloads
- crawlers
- blockchain/token infrastructure

## Repo Package

Path:

`infra/aws/cloud-brain-broker/`

Files:

- `handler.py`
- `template.yaml`
- `README.md`
- `example.env`
- `local_smoke.py`

## Routes

The Lambda broker implements:

- `GET /cloud/status`
- `POST /cloud/register-node`
- `POST /cloud/heartbeat`
- `POST /cloud/tasks/poll`
- `POST /cloud/tasks/submit`
- `GET /cloud/fragments/query`
- `POST /cloud/fragments/put`
- `GET /cloud/shards`
- `GET /cloud/credits`

Expected status response:

```json
{
  "service": "atanor-cloud-brain-broker",
  "mode": "dev",
  "status": "ok"
}
```

## DynamoDB Tables

The SAM template creates:

- `atanor_cloud_nodes_dev`
- `atanor_cloud_tasks_dev`
- `atanor_cloud_fragments_dev`
- `atanor_cloud_credits_dev`

All use `PAY_PER_REQUEST` to avoid provisioned capacity mistakes during early dev.

## S3 Bucket

The SAM template creates a private bucket:

`atanor-cloud-fragments-dev-<account>-<region>`

Current Lambda code stores tiny fragments in DynamoDB first. The bucket is reserved for larger public envelopes later.

## Local Environment

Set these after deployment:

```powershell
$env:ATANOR_CLOUD_MODE="remote"
$env:ATANOR_CLOUD_ENDPOINT="https://YOUR_HTTP_API_ID.execute-api.YOUR_REGION.amazonaws.com/dev"
$env:ATANOR_CLOUD_API_KEY=""
$env:ATANOR_NODE_ID="atanor-local-peer"
$env:ATANOR_CONTRIBUTION_ENABLED="true"
```

To return to local mode:

```powershell
$env:ATANOR_CLOUD_MODE="local_broker"
Remove-Item Env:ATANOR_CLOUD_ENDPOINT -ErrorAction SilentlyContinue
Remove-Item Env:ATANOR_CLOUD_API_KEY -ErrorAction SilentlyContinue
```

## Security Boundary

The broker rejects:

- `raw_text`
- `raw_document`
- `payload_vault`
- `private_graph`
- chat logs
- local file paths
- common executable/local path markers

The local app sends only:

- contributor node metadata
- bounded public task results
- summary-only public fragments
- hash topology and public concept metadata

Private Payload Vault records remain local.

## Deployment Steps

User-only/manual prerequisites:

- AWS login
- 2FA
- payment or identity verification if AWS asks
- AWS CLI/SAM authentication

Recommended region:

- `ap-northeast-2` for Korea latency, or your preferred cheapest/closest region.

SAM deployment:

```powershell
cd infra\aws\cloud-brain-broker
sam build
sam deploy --guided --stack-name atanor-cloud-brain-broker-dev --region ap-northeast-2 --capabilities CAPABILITY_IAM
```

Smoke test:

```powershell
python .\local_smoke.py
```

## Cost Guardrails

Expected near-zero traffic cost should be very low, but not guaranteed to be exactly zero.

Cost-sensitive services:

- Lambda invocations and compute duration
- API Gateway HTTP API calls
- DynamoDB reads/writes/storage
- S3 storage/requests/egress
- CloudWatch logs
- AWS Budgets, depending on account/pricing policy

Official references:

- AWS Lambda pricing/free tier: https://aws.amazon.com/lambda/pricing/
- API Gateway pricing/free tier: https://aws.amazon.com/api-gateway/pricing/
- DynamoDB pricing/free tier: https://aws.amazon.com/dynamodb/pricing/
- S3 pricing/free tier credits: https://aws.amazon.com/s3/pricing/
- AWS Budgets creation: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-create.html

Budget alerts:

- The template can create 1, 5, and 10 USD budgets if `BudgetAlertEmail` is provided.
- If CloudFormation lacks billing permissions, create budgets manually in AWS Billing and Cost Management.

## Shutdown

Delete the stack:

```powershell
sam delete --stack-name atanor-cloud-brain-broker-dev --region ap-northeast-2
```

Also delete manually created budgets if they were not created by CloudFormation.

## Current Limitations

- This is a dev broker, not the full Cloud Brain network.
- It is not P2P.
- It does not perform global consensus.
- It does not store private local memory.
- It does not run heavy crawling, embedding, or GPU workloads.
- It creates pending internal credits only; no token economy exists.
