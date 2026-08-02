# ATANOR Cloud Brain Broker Dev Stack

This folder contains the first real remote Cloud Brain Broker path for ATANOR.
It is deliberately tiny and cost-safe:

- AWS Lambda, Python 3.11, 128 MB
- API Gateway HTTP API
- DynamoDB pay-per-request tables
- Private S3 bucket for future large public fragments
- CloudWatch logs with 7-day retention
- Optional AWS Budget alerts at 1, 5, and 10 USD

It does not deploy EC2, Neptune, RDS, OpenSearch, ECS, EKS, SageMaker, Bedrock,
GPU workloads, crawlers, blockchain, or token infrastructure.

## Deploy With AWS SAM

Prerequisites:

- AWS account login handled by the user
- AWS CLI configured by the user
- AWS SAM CLI installed
- Region selected, for example `ap-northeast-2`

```powershell
cd infra/aws/cloud-brain-broker

sam build

sam deploy `
  --guided `
  --stack-name atanor-cloud-brain-broker-dev `
  --region ap-northeast-2 `
  --capabilities CAPABILITY_IAM
```

Or run the helper after AWS CLI/SAM CLI are installed and authenticated:

```powershell
.\deploy.ps1 -Region ap-northeast-2 -BudgetAlertEmail you@example.com
```

Recommended guided parameter values:

- `StageName`: `dev`
- `BrokerApiKey`: leave blank for first private smoke test, or enter a long random secret
- `AllowedOrigins`: `http://127.0.0.1:3022,http://localhost:3022,https://YOUR-VERCEL-APP.vercel.app`
- `BudgetAlertEmail`: your email address, or blank if you will create budgets manually

After deployment, copy the `CloudBrainBrokerEndpoint` output into local env:

```powershell
$env:ATANOR_CLOUD_MODE="remote"
$env:ATANOR_CLOUD_ENDPOINT="https://YOUR_HTTP_API_ID.execute-api.YOUR_REGION.amazonaws.com/dev"
$env:ATANOR_CLOUD_API_KEY=""
$env:ATANOR_NODE_ID="atanor-local-peer"
$env:ATANOR_CONTRIBUTION_ENABLED="true"
```

## Smoke Test

```powershell
python .\local_smoke.py
```

Expected `/cloud/status` shape:

```json
{
  "service": "atanor-cloud-brain-broker",
  "mode": "dev",
  "status": "ok"
}
```

## Security Boundary

The broker is a public-fragment control plane only.

- It rejects `raw_text`, `payload_vault`, local paths, and private graph markers.
- It accepts contributor node metadata, public task results, and small public hash fragments.
- Local Brain documents and Payload Vault records must remain local.
- Do not commit AWS credentials or broker API keys.

## Shut Down

To stop all resources created by this stack:

```powershell
sam delete --stack-name atanor-cloud-brain-broker-dev --region ap-northeast-2
```

If you created budgets manually in the AWS Billing console, delete them there too.
