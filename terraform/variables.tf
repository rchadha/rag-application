variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "rag-application"
}

variable "environment" {
  description = "Environment (development, staging, production)"
  type        = string
  default     = "production"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 3001
}

variable "task_cpu" {
  description = "Fargate task CPU units"
  type        = string
  default     = "512" # 0.5 vCPU
}

variable "task_memory" {
  description = "Fargate task memory in MB"
  type        = string
  default     = "1024" # 1 GB
}

variable "desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "min_capacity" {
  description = "Minimum number of tasks for auto scaling"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum number of tasks for auto scaling"
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 7
}

# Optional: For HTTPS
# variable "certificate_arn" {
#   description = "ARN of ACM certificate for HTTPS"
#   type        = string
#   default     = ""
# }
