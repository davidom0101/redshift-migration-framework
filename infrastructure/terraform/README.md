# Redshift infrastructure

Private Redshift Serverless, S3, IAM role, security group and compute usage limit.
Uses an existing VPC and subnets; tables and data are set up separately.

## Setup

Install Terraform and authenticate to AWS with an IAM user or role, not root.
Use subnets in the same VPC across at least two availability zones.
From the repository root:

```powershell
cd infrastructure/terraform
Copy-Item terraform.tfvars.example terraform.tfvars
# Set your account ID, region and subnet IDs in terraform.tfvars.
terraform init
terraform validate
terraform plan
```

Review the plan and costs before `terraform apply`. For existing resources, reuse
their state or import them first. Keep actual variables, state and `.terraform/`
out of Git; retain the provider lockfile.

## Database access

Use Query Editor v2 or the Data API for `migration-dev` / `migration_lab`.
Grant IAM query and managed-secret access separately; the secret provides admin
database access. Follow the [example setup](../../examples/README.md) for a new
database. Do not replay setup against populated tables.

## Costs and cleanup

Defaults: Ireland, 4 RPUs, daily deactivate limit of 8 RPU-hours. This is not a
total-bill cap; storage and other services still incur charges. Budget alerts are
optional via `budget_email`.

Save needed data and intentionally empty the project bucket before cleanup.
Review `terraform plan -destroy`, then run `terraform destroy` if approved.
Existing VPC/subnets are not managed by this project.
