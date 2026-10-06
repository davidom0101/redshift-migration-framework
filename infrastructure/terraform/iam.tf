data "aws_iam_policy_document" "redshift_assume" {
  statement {
    sid     = "RedshiftServiceAssumeRole"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift-serverless.amazonaws.com", "redshift.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "redshift_s3" {
  name               = "${var.resource_prefix}-s3-read"
  assume_role_policy = data.aws_iam_policy_document.redshift_assume.json
}

data "aws_iam_policy_document" "read_project_data" {
  statement {
    sid       = "ListProjectData"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["redshift-migration/source/*", "redshift-migration/source/"]
    }
  }
  statement {
    sid       = "GetBucketLocation"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.data.arn]
  }
  statement {
    sid       = "ReadProjectSourceObjects"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/redshift-migration/source/*"]
  }
}

resource "aws_iam_role_policy" "read_project_data" {
  role   = aws_iam_role.redshift_s3.id
  name   = "read-project-source-data"
  policy = data.aws_iam_policy_document.read_project_data.json
}
