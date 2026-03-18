output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.app.repository_url
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.app.function_name
}

output "api_gateway_url" {
  description = "URL of the API Gateway endpoint"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "secret_arn" {
  description = "ARN of the OpenAI API key secret"
  value       = aws_secretsmanager_secret.openai_api_key.arn
}

output "ingest_lambda_function_name" {
  description = "Name of the ingestion Lambda function"
  value       = aws_lambda_function.ingest.function_name
}

output "ingest_schedule_name" {
  description = "Name of the EventBridge schedule"
  value       = aws_scheduler_schedule.daily_ingest.name
}

output "finnhub_secret_arn" {
  description = "ARN of the Finnhub API key secret"
  value       = aws_secretsmanager_secret.finnhub_api_key.arn
}

