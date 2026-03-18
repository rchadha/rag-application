terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Optional: Configure S3 backend for state management
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "rag-application/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region
}

# Data sources
data "aws_caller_identity" "current" {}

# ECR Repository
resource "aws_ecr_repository" "app" {
  name                 = var.project_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = var.project_name
    Environment = var.environment
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# Secrets Manager
resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "${var.project_name}/openai-api-key"
  description             = "OpenAI API Key for RAG Application"
  recovery_window_in_days = 7

  tags = {
    Name        = "${var.project_name}-openai-key"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret" "pinecone_api_key" {
  name                    = "${var.project_name}/pinecone-api-key"
  description             = "Pinecone API Key for RAG Application"
  recovery_window_in_days = 7

  tags = {
    Name        = "${var.project_name}-pinecone-key"
    Environment = var.environment
  }
}

# Note: The secret value must be set manually or via GitHub Actions
# aws secretsmanager put-secret-value --secret-id <secret-name> --secret-string "your-key"


# Application Load Balancer - uncomment all resources below to re-enable ALB
# Also uncomment: aws_security_group.alb, the ALB ingress in aws_security_group.ecs_tasks,
# the load_balancer block and depends_on in aws_ecs_service.app, and the ALB outputs.
#
# resource "aws_lb" "main" {
#   name               = "${var.project_name}-alb"
#   internal           = false
#   load_balancer_type = "application"
#   security_groups    = [aws_security_group.alb.id]
#   subnets            = aws_subnet.public[*].id
#
#   enable_deletion_protection = false
#   enable_http2              = true
#
#   tags = {
#     Name        = "${var.project_name}-alb"
#     Environment = var.environment
#   }
# }
#
# resource "aws_lb_target_group" "app" {
#   name                 = "${var.project_name}-tg"
#   port                 = var.container_port
#   protocol             = "HTTP"
#   vpc_id               = aws_vpc.main.id
#   target_type          = "ip"
#   deregistration_delay = 30
#
#   health_check {
#     enabled             = true
#     healthy_threshold   = 2
#     interval            = 30
#     matcher             = "200"
#     path                = "/health"
#     port                = "traffic-port"
#     protocol            = "HTTP"
#     timeout             = 10
#     unhealthy_threshold = 3
#   }
#
#   tags = {
#     Name        = "${var.project_name}-tg"
#     Environment = var.environment
#   }
# }
#
# resource "aws_lb_listener" "http" {
#   load_balancer_arn = aws_lb.main.arn
#   port              = "80"
#   protocol          = "HTTP"
#
#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.app.arn
#   }
# }
#
# Optional: HTTPS Listener (requires ACM certificate)
# resource "aws_lb_listener" "https" {
#   load_balancer_arn = aws_lb.main.arn
#   port              = "443"
#   protocol          = "HTTPS"
#   ssl_policy        = "ELBSecurityPolicy-2016-08"
#   certificate_arn   = var.certificate_arn
#
#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.app.arn
#   }
# }

# Lambda Function
resource "aws_lambda_function" "app" {
  function_name = var.project_name
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}:latest"
  role          = aws_iam_role.lambda_exec.arn
  timeout       = 120
  memory_size   = 1024

  environment {
    variables = {
      FLASK_ENV          = var.environment
      PINECONE_INDEX_NAME = "rag-application"
    }
  }

  # Secrets injected via Secrets Manager at runtime (fetched in app startup)
  # OPENAI_API_KEY and PINECONE_API_KEY are read from Secrets Manager

  tags = {
    Name        = var.project_name
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = var.project_name
    Environment = var.environment
  }
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-lambda-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = {
    Name        = "${var.project_name}-lambda-exec-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_secrets" {
  name = "secrets-access"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.openai_api_key.arn,
        aws_secretsmanager_secret.pinecone_api_key.arn
      ]
    }]
  })
}

# API Gateway (HTTP API - cheaper than REST API)
resource "aws_apigatewayv2_api" "app" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  tags = {
    Name        = "${var.project_name}-api"
    Environment = var.environment
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id             = aws_apigatewayv2_api.app.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.app.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.app.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.app.id
  name        = "$default"
  auto_deploy = true

  tags = {
    Name        = "${var.project_name}-stage"
    Environment = var.environment
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.app.execution_arn}/*/*"
}
