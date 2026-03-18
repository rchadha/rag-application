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

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 7
}

variable "ingest_tickers" {
  description = "JSON array of tickers to ingest, e.g. [{\"ticker\":\"NVDA\",\"company\":\"NVIDIA\"}]"
  type        = string
  default     = "[{\"ticker\":\"NVDA\",\"company\":\"NVIDIA\"}]"
}

variable "ingest_days" {
  description = "How many days back to fetch on each ingestion run"
  type        = number
  default     = 1
}

variable "ingest_sources" {
  description = "Comma-separated ingestion sources: news,reddit"
  type        = string
  default     = "news,reddit"
}
