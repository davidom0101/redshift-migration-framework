data "aws_subnet" "selected" {
  for_each = toset(var.subnet_ids)
  id       = each.value
}

locals {
  subnet_availability_zone_ids = distinct([
    for subnet in data.aws_subnet.selected : subnet.availability_zone_id
  ])
  subnet_vpc_ids = distinct([
    for subnet in data.aws_subnet.selected : subnet.vpc_id
  ])
}

check "subnets_are_suitable" {
  assert {
    condition     = length(local.subnet_vpc_ids) == 1
    error_message = "All subnet_ids must belong to the same VPC."
  }

  assert {
    condition     = length(local.subnet_availability_zone_ids) >= 2
    error_message = "Redshift Serverless without enhanced VPC routing needs subnets in at least two availability zones."
  }

  assert {
    condition = alltrue([
      for subnet in data.aws_subnet.selected : subnet.available_ip_address_count >= 3
    ])
    error_message = "Each subnet must have at least three available IP addresses for Redshift Serverless."
  }
}

resource "aws_security_group" "redshift" {
  name        = "${var.resource_prefix}-redshift"
  description = "Private Redshift Serverless workgroup; no direct inbound access"
  vpc_id      = one(local.subnet_vpc_ids)

  egress {
    description = "Allow Redshift managed outbound connections"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
