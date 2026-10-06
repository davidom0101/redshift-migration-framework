resource "aws_redshiftserverless_namespace" "migration" {
  namespace_name        = "migration-portfolio"
  db_name               = "migration_lab"
  manage_admin_password = true
  iam_roles             = [aws_iam_role.redshift_s3.arn]
  default_iam_role_arn  = aws_iam_role.redshift_s3.arn
  depends_on            = [aws_iam_role_policy.read_project_data]
}

resource "aws_redshiftserverless_workgroup" "migration" {
  workgroup_name       = "migration-dev"
  namespace_name       = aws_redshiftserverless_namespace.migration.namespace_name
  base_capacity        = var.base_capacity
  publicly_accessible  = false
  enhanced_vpc_routing = false
  subnet_ids           = var.subnet_ids
  security_group_ids   = [aws_security_group.redshift.id]
  track_name           = "current"

  config_parameter {
    parameter_key   = "require_ssl"
    parameter_value = "true"
  }
}

resource "aws_redshiftserverless_usage_limit" "daily" {
  resource_arn  = aws_redshiftserverless_workgroup.migration.arn
  usage_type    = "serverless-compute"
  period        = "daily"
  amount        = var.daily_rpu_hours
  breach_action = "deactivate"
}
