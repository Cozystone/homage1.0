param(
    [string]$Region = "ap-northeast-2",
    [string]$StackName = "atanor-cloud-brain-broker-dev",
    [string]$StageName = "dev",
    [string]$AllowedOrigins = "http://127.0.0.1:3022,http://localhost:3022",
    [string]$BudgetAlertEmail = "",
    [string]$BrokerApiKey = ""
)

$ErrorActionPreference = "Stop"

function Require-Command($Name, $InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is not installed. $InstallHint"
    }
}

Require-Command "aws" "Install AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
Require-Command "sam" "Install AWS SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"

Write-Host "[ATANOR] Checking AWS identity..."
aws sts get-caller-identity | Out-Host

Write-Host "[ATANOR] Building SAM package..."
sam build

Write-Host "[ATANOR] Deploying Cloud Brain Broker..."
sam deploy `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides `
        StageName=$StageName `
        BrokerApiKey=$BrokerApiKey `
        AllowedOrigins=$AllowedOrigins `
        BudgetAlertEmail=$BudgetAlertEmail `
    --no-fail-on-empty-changeset

Write-Host "[ATANOR] Stack outputs:"
aws cloudformation describe-stacks `
    --region $Region `
    --stack-name $StackName `
    --query "Stacks[0].Outputs" `
    --output table
