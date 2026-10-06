variable "aws_region" {
  type        = string
  description = "AWS Region where Redshift and the dataset bucket will live."
  default     = "eu-west-1"
}

variable "aws_account_id" {
  type        = string
  description = "Expected 12-digit AWS account ID. Prevents an accidental plan or apply in another account."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "resource_prefix" {
  type        = string
  description = "Short lowercase prefix; forms bucket and role names."
  default     = "rs-migration-portfolio"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.resource_prefix))
    error_message = "Use 3-25 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "subnet_ids" {
  type        = list(string)
  description = "At least two compatible existing subnets in separate AZs (without enhanced VPC routing)."
  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "Supply at least two compatible subnet IDs."
  }
  validation {
    condition     = alltrue([for id in var.subnet_ids : can(regex("^subnet-[0-9a-f]+$", id))])
    error_message = "Every subnet_ids entry must look like an AWS subnet ID."
  }
}

variable "base_capacity" {
  type        = number
  description = "Starting Redshift Serverless capacity. 4 RPUs are supported in Ireland."
  default     = 4
  validation {
    condition = (
      var.base_capacity == 4 ||
      (var.base_capacity >= 8 && var.base_capacity <= 512 && var.base_capacity % 8 == 0)
    )
    error_message = "Use 4 RPUs or a multiple of 8 from 8 through 512."
  }
}

variable "daily_rpu_hours" {
  type        = number
  description = "Daily RPU-hour limit. Note: usage limits are not hard cash caps."
  default     = 8
  validation {
    condition     = var.daily_rpu_hours >= 1 && floor(var.daily_rpu_hours) == var.daily_rpu_hours
    error_message = "daily_rpu_hours must be a positive whole number."
  }
}

variable "budget_email" {
  type        = string
  description = "Optional notification email for AWS Budgets; empty disables budget creation."
  default     = ""
}

variable "monthly_budget_usd" {
  type        = number
  description = "Monthly AWS budget threshold in USD if budget_email is configured."
  default     = 20
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "monthly_budget_usd must be greater than zero."
  }
}
