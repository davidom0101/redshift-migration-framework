provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project     = "redshift-deep-copy-migration"
      Environment = "portfolio"
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
