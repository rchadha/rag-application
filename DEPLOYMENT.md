# AWS ECS Deployment Guide - Terraform + GitHub Actions

This guide explains how to deploy the RAG application to AWS ECS using Terraform for infrastructure and GitHub Actions for CI/CD.

## Architecture

- **Infrastructure**: Terraform manages all AWS resources
- **Container Orchestration**: AWS ECS Fargate (serverless)
- **Load Balancer**: Application Load Balancer (ALB)
- **Container Registry**: Amazon ECR
- **Secrets**: AWS Secrets Manager
- **Logging**: CloudWatch Logs
- **Networking**: VPC with public/private subnets, NAT gateways
- **CI/CD**: GitHub Actions

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
3. **Terraform** >= 1.0 installed
4. **GitHub repository** with this code
5. **OpenAI API key**

## Step 1: Set Up AWS Credentials for GitHub Actions

You have two options:

### Option A: OIDC (Recommended - No Long-lived Credentials)

1. Create an OIDC provider in AWS IAM:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

2. Create an IAM role for GitHub Actions:

```bash
# Create trust policy
cat > github-actions-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/rag-application:*"
        }
      }
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document file://github-actions-trust-policy.json

# Attach policies (adjust as needed)
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess

# Get role ARN
aws iam get-role --role-name GitHubActionsRole --query Role.Arn
```

3. Add GitHub secret:
   - Go to your repo → Settings → Secrets and variables → Actions
   - Add secret: `AWS_ROLE_TO_ASSUME` = `arn:aws:iam::YOUR_ACCOUNT_ID:role/GitHubActionsRole`

### Option B: Access Keys (Simpler but Less Secure)

1. Create IAM user with programmatic access
2. Attach policies: `AmazonEC2ContainerRegistryPowerUser`, `AmazonECS_FullAccess`
3. Add GitHub secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
4. Update `.github/workflows/deploy.yml` to use access keys (uncomment the relevant section)

## Step 2: Deploy Infrastructure with Terraform

### 2.1 Initialize Terraform

```bash
cd terraform

# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
# At minimum, verify aws_region and project_name

# Initialize Terraform
terraform init
```

### 2.2 Review and Apply

```bash
# See what will be created
terraform plan

# Create infrastructure
terraform apply

# Save outputs (you'll need these)
terraform output > ../terraform-outputs.txt
```

This will create:
- VPC with public and private subnets
- NAT gateways
- Security groups
- Application Load Balancer
- ECS cluster
- ECR repository
- Secrets Manager secret (empty - you'll populate it next)
- CloudWatch log group
- IAM roles
- Auto-scaling configuration

### 2.3 Store OpenAI API Key

```bash
# Get the secret ARN from terraform output
SECRET_ARN=$(terraform output -raw secret_arn)

# Store your OpenAI API key
aws secretsmanager put-secret-value \
  --secret-id $SECRET_ARN \
  --secret-string "your-openai-api-key-here"
```

## Step 3: Build and Push Initial Docker Image

Before GitHub Actions can deploy, you need an initial image in ECR:

```bash
# Get ECR repository URL from terraform output
cd ..
ECR_REPO=$(cd terraform && terraform output -raw ecr_repository_url)
AWS_REGION=us-east-1  # or your region

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REPO

# Build and push
docker build -t rag-application .
docker tag rag-application:latest $ECR_REPO:latest
docker push $ECR_REPO:latest
```

## Step 4: Initial ECS Service Deployment

The ECS service is already created by Terraform, but you may need to force a deployment:

```bash
aws ecs update-service \
  --cluster rag-application-cluster \
  --service rag-application-service \
  --force-new-deployment \
  --region $AWS_REGION
```

## Step 5: Configure GitHub Actions

The `.github/workflows/deploy.yml` file is already configured. It will:

1. **On Pull Request**: Run tests and Terraform plan
2. **On Push to main/master**: Build Docker image, push to ECR, and deploy to ECS

### Update workflow variables if needed:

Edit `.github/workflows/deploy.yml` and update:
- `AWS_REGION` (if different from us-east-1)
- `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`, `CONTAINER_NAME` (if you changed names in Terraform)

## Step 6: Test the Deployment

### 6.1 Get Application URL

```bash
cd terraform
ALB_URL=$(terraform output -raw alb_url)
echo "Application URL: $ALB_URL"
```

### 6.2 Test Endpoints

```bash
# Health check
curl $ALB_URL/health

# Query endpoint
curl -X POST $ALB_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is AWS Lambda?"}'
```

### 6.3 View Logs

```bash
# Tail logs
aws logs tail /ecs/rag-application --follow

# Or use AWS Console:
# CloudWatch → Log groups → /ecs/rag-application
```

## CI/CD Workflow

### Automated Deployment Process

1. **Developer pushes code** to a feature branch
2. **Pull Request created** → GitHub Actions runs:
   - Tests (lint, unit tests)
   - Terraform plan (shows infrastructure changes)
3. **PR merged to main** → GitHub Actions runs:
   - Builds Docker image
   - Pushes to ECR with git SHA and `latest` tags
   - Updates ECS task definition
   - Deploys to ECS
   - Waits for service stability
   - Verifies health endpoint

### Manual Deployment

You can trigger deployments manually:
- Go to GitHub → Actions → Deploy to AWS ECS → Run workflow

## Monitoring and Operations

### View Service Status

```bash
aws ecs describe-services \
  --cluster rag-application-cluster \
  --services rag-application-service
```

### View Running Tasks

```bash
aws ecs list-tasks \
  --cluster rag-application-cluster \
  --service-name rag-application-service
```

### Scale Service

```bash
# Via CLI
aws ecs update-service \
  --cluster rag-application-cluster \
  --service rag-application-service \
  --desired-count 4

# Or update terraform/variables.tf and apply
```

### View Metrics

- AWS Console → CloudWatch → Dashboards
- ECS Cluster → Metrics tab
- Load Balancer → Monitoring tab

### Auto-Scaling

The Terraform configuration includes auto-scaling based on:
- CPU utilization (target: 70%)
- Memory utilization (target: 80%)
- Min: 1 task, Max: 10 tasks

## Cost Optimization

### Current Configuration Costs (Approximate)

- **Fargate**: ~$0.04/hour per task (1 vCPU, 2GB RAM)
  - 2 tasks = ~$58/month
- **NAT Gateway**: ~$0.045/hour × 2 = ~$65/month
- **ALB**: ~$16/month + data transfer
- **ECR Storage**: ~$0.10/GB/month
- **CloudWatch Logs**: First 5GB free, then $0.50/GB

**Monthly estimate: ~$140-160/month**

### Optimization Tips

1. **Use Fargate Spot** (70% cheaper):
   ```hcl
   # In terraform/main.tf, update capacity provider strategy
   capacity_provider = "FARGATE_SPOT"
   ```

2. **Single NAT Gateway** (if you can tolerate lower availability):
   ```hcl
   # In terraform/main.tf, reduce NAT gateways from 2 to 1
   ```

3. **Schedule scaling** for off-hours:
   ```bash
   # Scale down at night, up in morning using EventBridge + Lambda
   ```

4. **Reduce log retention**:
   ```hcl
   log_retention_days = 3  # in variables.tf
   ```

## Updating Infrastructure

### Make Changes to Terraform

```bash
cd terraform

# Edit .tf files
vim main.tf

# Plan changes
terraform plan

# Apply changes
terraform apply
```

### Common Updates

**Change task size:**
```hcl
# variables.tf
task_cpu    = "2048"  # 2 vCPU
task_memory = "4096"  # 4 GB
```

**Add HTTPS:**
1. Request ACM certificate in AWS Console
2. Uncomment HTTPS listener in `terraform/main.tf`
3. Set `certificate_arn` variable
4. Apply

**Change region:**
```hcl
# terraform.tfvars
aws_region = "us-west-2"
```

## Rollback

### Rollback to Previous Task Definition

```bash
# List task definitions
aws ecs list-task-definition-families

# Describe specific version
aws ecs describe-task-definition --task-definition rag-application:5

# Update service to use older version
aws ecs update-service \
  --cluster rag-application-cluster \
  --service rag-application-service \
  --task-definition rag-application:5
```

### Rollback via GitHub Actions

Re-run a previous successful deployment from the Actions tab.

## Disaster Recovery

### State Management (Recommended)

Configure Terraform remote state:

```hcl
# terraform/main.tf
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "rag-application/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

Create the S3 bucket and DynamoDB table:

```bash
# Create S3 bucket
aws s3 mb s3://your-terraform-state-bucket
aws s3api put-bucket-versioning \
  --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## Cleanup

### Destroy All Resources

```bash
cd terraform

# WARNING: This will delete everything
terraform destroy

# Confirm by typing 'yes'
```

### Manual Cleanup (if Terraform destroy fails)

```bash
# Delete ECS service
aws ecs update-service \
  --cluster rag-application-cluster \
  --service rag-application-service \
  --desired-count 0

aws ecs delete-service \
  --cluster rag-application-cluster \
  --service rag-application-service --force

# Then retry terraform destroy
cd terraform && terraform destroy
```

## Troubleshooting

### Task Fails to Start

1. Check CloudWatch logs
2. Verify secret exists and has correct value
3. Check security groups allow outbound internet (for OpenAI API)
4. Verify IAM roles have correct permissions

### Health Check Failing

1. Check `/health` endpoint works locally
2. Verify security group allows ALB → ECS traffic on port 3001
3. Check task has enough CPU/memory
4. Increase health check grace period

### Cannot Pull ECR Image

1. Verify image exists: `aws ecr describe-images --repository-name rag-application`
2. Check task execution role has ECR permissions
3. Verify image URI in task definition is correct

### GitHub Actions Failing

1. Check AWS credentials are configured correctly
2. Verify IAM role/user has necessary permissions
3. Check secrets are set in GitHub repo
4. Review Actions logs for specific errors

### High Costs

1. Review CloudWatch metrics for utilization
2. Consider Fargate Spot
3. Reduce NAT gateways
4. Optimize auto-scaling parameters
5. Reduce log retention

## Security Best Practices

1. **Secrets**: Never commit API keys - use Secrets Manager
2. **HTTPS**: Add SSL certificate for production
3. **Private Subnets**: Tasks run in private subnets (✓ already configured)
4. **Security Groups**: Minimal required access (✓ configured)
5. **IAM Roles**: Least privilege principle
6. **VPC**: Isolated network (✓ created by Terraform)
7. **ECR Scanning**: Enabled by default in Terraform
8. **Logging**: CloudWatch logs enabled (✓ configured)

## Production Checklist

- [ ] Use HTTPS with ACM certificate
- [ ] Set up custom domain with Route 53
- [ ] Configure CloudWatch alarms
- [ ] Set up AWS Backup for state files
- [ ] Enable AWS WAF on ALB
- [ ] Implement proper CI/CD approval gates
- [ ] Set up separate dev/staging/prod environments
- [ ] Configure VPC Flow Logs
- [ ] Enable ECS Exec for debugging
- [ ] Set up cost alerts

## Support and Resources

- **Terraform AWS Provider**: https://registry.terraform.io/providers/hashicorp/aws
- **ECS Best Practices**: https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide
- **GitHub Actions**: https://docs.github.com/en/actions
- **AWS Well-Architected Framework**: https://aws.amazon.com/architecture/well-architected/

## Next Steps

1. Set up monitoring dashboards
2. Configure CloudWatch alarms
3. Implement blue/green deployments
4. Add integration tests to CI/CD
5. Set up staging environment
6. Configure custom domain
7. Add HTTPS support
8. Implement API authentication
