output "s3_bucket" {
  value       = aws_s3_bucket.data.bucket
  description = "Private S3 bucket for prepared source data."
}

output "redshift_namespace" {
  value = aws_redshiftserverless_namespace.migration.namespace_name
}

output "redshift_workgroup" {
  value = aws_redshiftserverless_workgroup.migration.workgroup_name
}

output "redshift_s3_role_arn" {
  value       = aws_iam_role.redshift_s3.arn
  description = "Default Redshift role with restricted access to source-data prefix."
}

output "redshift_security_group_id" {
  value       = aws_security_group.redshift.id
  description = "Dedicated security group with no inbound rules."
}

output "database_name" {
  value       = aws_redshiftserverless_namespace.migration.db_name
  description = "Database created in the Redshift Serverless namespace."
}
