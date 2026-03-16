# Understanding OIDC for GitHub Actions + AWS

This document explains OpenID Connect (OIDC) authentication for GitHub Actions and why it's the recommended approach for AWS deployments.

## What is OIDC?

**OIDC (OpenID Connect)** is an authentication protocol that allows GitHub Actions to request short-lived access tokens from AWS without needing to store long-lived credentials (access keys) as secrets.

## How Traditional Access Keys Work (Option B)

```
┌─────────────┐
│   GitHub    │
│  Repository │
│             │
│  Secrets:   │
│  ├─ AWS_ACCESS_KEY_ID     ──────┐
│  └─ AWS_SECRET_ACCESS_KEY       │
└─────────────┘                    │
                                   │
                            Uses these credentials
                            (valid indefinitely)
                                   │
                                   ▼
                            ┌──────────┐
                            │   AWS    │
                            └──────────┘
```

**Problems:**
- Keys are **permanent** until you rotate them
- If someone steals the keys from GitHub secrets, they have unlimited AWS access
- Keys can be accidentally committed, leaked in logs, etc.
- You must manually rotate keys periodically
- If employee leaves, you need to remember to revoke their keys

## How OIDC Works (Option A)

```
┌─────────────────────┐
│  GitHub Actions     │
│  (Running workflow) │
└──────────┬──────────┘
           │
           │ 1. "I'm github.com/youruser/rag-application"
           │    Here's my JWT token (signed by GitHub)
           │
           ▼
    ┌──────────────────────┐
    │   AWS IAM OIDC      │
    │   Provider          │
    │                     │
    │  Trusts GitHub      │
    │  Verifies JWT       │
    └──────────┬──────────┘
               │
               │ 2. JWT valid ✓
               │    Repo matches trust policy ✓
               │    Here's a temporary token (15 min - 1 hour)
               │
               ▼
        ┌──────────┐
        │   AWS    │
        │ Services │
        └──────────┘
```

**Flow Step-by-Step:**

1. **GitHub Actions starts** your workflow
2. GitHub **generates a JWT token** that contains:
   - Repository name: `rchadha/rag-application`
   - Branch/tag being deployed
   - Workflow information
   - Expiration time
3. **Workflow requests AWS credentials** using this JWT
4. **AWS verifies** the JWT with GitHub's public keys
5. **AWS checks** if this specific repository is allowed (in the trust policy)
6. **AWS issues temporary credentials** (valid for ~15-60 minutes)
7. **Workflow uses temporary credentials** to deploy
8. **Credentials automatically expire** after the time limit

## Why OIDC is Better

### 1. No Stored Secrets
- No long-lived credentials in GitHub
- Nothing to steal from GitHub Secrets
- Even if someone accesses your repo settings, they can't get AWS access

### 2. Automatic Expiration
- Credentials expire in minutes/hours
- Even if intercepted, they're useless after expiration
- No manual rotation needed

### 3. Granular Trust
- Trust is scoped to **specific repositories**
- Trust policy example:
  ```json
  "Condition": {
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:rchadha/rag-application:*"
    }
  }
  ```
- Only workflows from `rchadha/rag-application` can assume the role
- You can even limit to specific branches:
  ```json
  "repo:rchadha/rag-application:ref:refs/heads/main"
  ```

### 4. Audit Trail
- CloudTrail shows which GitHub repository/workflow made each request
- You can see exactly which commit triggered the deployment

### 5. Industry Best Practice
- Recommended by AWS, GitHub, and security experts
- Aligns with "Zero Trust" security model
- No secrets to leak or manage

## Real-World Security Scenario

**With Access Keys:**
```
❌ Developer's laptop gets compromised
   → Attacker finds .env file with AWS keys
   → Attacker has full AWS access until keys are rotated
   → Potential damage: unlimited
```

**With OIDC:**
```
✅ Even if attacker gets GitHub access:
   → Can't get AWS credentials (they're not stored)
   → Even if they trigger a workflow:
     → Credentials only work for that workflow run
     → Credentials expire in 15-60 minutes
     → CloudTrail logs show suspicious activity from GitHub
     → Can be detected and stopped quickly
```

## Setup Comparison

### Option B (Access Keys) - Simpler but Less Secure
```bash
# Create user
aws iam create-user --user-name github-actions

# Create access key
aws iam create-access-key --user-name github-actions

# Copy output to GitHub Secrets
# AWS_ACCESS_KEY_ID: AKIAIOSFODNN7EXAMPLE
# AWS_SECRET_ACCESS_KEY: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

### Option A (OIDC) - More Secure
```bash
# One-time: Create OIDC provider (trust GitHub)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com

# Create role with trust policy for your specific repo
aws iam create-role --role-name GitHubActionsRole \
  --assume-role-policy-document file://trust-policy.json

# Only need to store the role ARN in GitHub (not a credential)
# AWS_ROLE_TO_ASSUME: arn:aws:iam::123456789:role/GitHubActionsRole
```

## What You're Actually Storing

**Option B (Access Keys):**
- `AWS_ACCESS_KEY_ID`: `AKIAIOSFODNN7EXAMPLE` ← Can authenticate to AWS
- `AWS_SECRET_ACCESS_KEY`: `wJalrXUtnFEMI/K7MDENG...` ← Secret key with full access

**Option A (OIDC):**
- `AWS_ROLE_TO_ASSUME`: `arn:aws:iam::123456789:role/GitHubActionsRole` ← Just an identifier, not a credential!

The ARN is **not a secret** - it's just an address. Only GitHub Actions from your specific repository can use it because of the trust policy.

## Detailed OIDC Setup Guide

### Step 1: Create OIDC Provider in AWS

This is a **one-time setup per AWS account** (not per project).

```bash
# Set your AWS account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create OIDC provider for GitHub
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# Verify it was created
aws iam list-open-id-connect-providers
```

**What this does:**
- Tells AWS to trust JWT tokens issued by `token.actions.githubusercontent.com`
- The thumbprint verifies GitHub's SSL certificate
- This is a global setting for your AWS account

### Step 2: Create Trust Policy Document

Create a file that defines **which GitHub repositories** can assume the role:

```bash
# Replace YOUR_GITHUB_USERNAME with your actual GitHub username
export GITHUB_USERNAME="rchadha"
export GITHUB_REPO="rag-application"

# Create trust policy
cat > github-actions-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_USERNAME}/${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
EOF

cat github-actions-trust-policy.json
```

**Understanding the trust policy:**
- `Federated`: Points to the OIDC provider we created
- `sts:AssumeRoleWithWebIdentity`: Allows assuming role with JWT token
- `token.actions.githubusercontent.com:aud`: Audience must be AWS STS
- `token.actions.githubusercontent.com:sub`: Subject must match your repo
  - `repo:rchadha/rag-application:*` means any branch/tag in this repo
  - For main branch only: `repo:rchadha/rag-application:ref:refs/heads/main`

### Step 3: Create IAM Role

```bash
# Create the role
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document file://github-actions-trust-policy.json \
  --description "Role for GitHub Actions to deploy RAG application"

# Get the role ARN (save this!)
export ROLE_ARN=$(aws iam get-role \
  --role-name GitHubActionsRole \
  --query Role.Arn --output text)

echo "Role ARN: $ROLE_ARN"
```

### Step 4: Attach Permissions to the Role

The role needs permissions to deploy your application:

```bash
# Option 1: Attach AWS managed policies (easier)
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess

# Option 2: Create custom policy with least privilege (recommended for production)
cat > github-actions-permissions.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeRepositories",
        "ecr:DescribeImages"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:DescribeTasks",
        "ecs:ListTasks",
        "ecs:RegisterTaskDefinition",
        "ecs:UpdateService"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/rag-application-ecs-task-execution-role",
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/rag-application-ecs-task-role"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "elbv2:DescribeLoadBalancers",
        "elbv2:DescribeTargetGroups",
        "elbv2:DescribeTargetHealth"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name GitHubActionsRole \
  --policy-name GitHubActionsDeploymentPolicy \
  --policy-document file://github-actions-permissions.json
```

### Step 5: Configure GitHub Repository Secret

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `AWS_ROLE_TO_ASSUME`
5. Value: Paste the role ARN from Step 3 (e.g., `arn:aws:iam::123456789012:role/GitHubActionsRole`)
6. Click **Add secret**

### Step 6: Update GitHub Actions Workflow

The workflow is already configured in `.github/workflows/deploy.yml`:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
    aws-region: ${{ env.AWS_REGION }}
```

That's it! No access keys needed.

## Advanced OIDC Configurations

### Limit to Specific Branch

Only allow deployments from the `main` branch:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub": "repo:rchadha/rag-application:ref:refs/heads/main"
  }
}
```

### Limit to Specific Environment

Only allow deployments from GitHub Environments named "production":

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
  },
  "StringLike": {
    "token.actions.githubusercontent.com:sub": "repo:rchadha/rag-application:environment:production"
  }
}
```

### Multiple Repositories

Allow multiple repositories to use the same role:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
  },
  "StringLike": {
    "token.actions.githubusercontent.com:sub": [
      "repo:rchadha/rag-application:*",
      "repo:rchadha/another-project:*"
    ]
  }
}
```

### Session Duration

Control how long the temporary credentials last (default is 1 hour):

```bash
aws iam update-role \
  --role-name GitHubActionsRole \
  --max-session-duration 3600  # 1 hour in seconds (3600-43200)
```

## Troubleshooting OIDC

### Error: "Not authorized to perform sts:AssumeRoleWithWebIdentity"

**Problem:** Trust policy doesn't match your repository.

**Solution:**
```bash
# Check the trust policy
aws iam get-role --role-name GitHubActionsRole --query Role.AssumeRolePolicyDocument

# Verify repository name matches exactly (case-sensitive!)
# Should be: repo:YOUR_USERNAME/YOUR_REPO:*
```

### Error: "An error occurred (InvalidIdentityToken)"

**Problem:** OIDC provider not set up or thumbprint is wrong.

**Solution:**
```bash
# List OIDC providers
aws iam list-open-id-connect-providers

# Should see: arn:aws:iam::YOUR_ACCOUNT:oidc-provider/token.actions.githubusercontent.com

# If missing, create it:
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Error: "User is not authorized to perform: ecs:UpdateService"

**Problem:** Role lacks necessary permissions.

**Solution:**
```bash
# Check attached policies
aws iam list-attached-role-policies --role-name GitHubActionsRole

# Attach required policy
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess
```

### Verify JWT Token Contents (Debugging)

You can decode the JWT token in your workflow to see what GitHub is sending:

```yaml
- name: Debug JWT claims
  run: |
    # Decode the JWT token (without verification)
    echo ${{ github.token }} | cut -d'.' -f2 | base64 -d | jq .
```

## Security Best Practices

1. **Use least privilege**: Only grant permissions the workflow actually needs
2. **Scope to specific repos**: Don't use wildcard in trust policy
3. **Limit to specific branches**: For production, only allow `main` branch
4. **Use GitHub Environments**: Add manual approval gates for production
5. **Monitor CloudTrail**: Watch for unexpected AssumeRoleWithWebIdentity calls
6. **Rotate regularly**: Delete and recreate OIDC provider yearly
7. **Audit permissions**: Review role permissions quarterly

## Comparing Security Models

| Aspect | Access Keys | OIDC |
|--------|-------------|------|
| **Credential Storage** | GitHub Secrets | None (just role ARN) |
| **Credential Lifetime** | Permanent | 15-60 minutes |
| **Rotation Required** | Yes, manually | No, automatic |
| **Theft Impact** | Full AWS access | Limited by session duration |
| **Scope Control** | Per user/role | Per repo + branch + environment |
| **Audit Trail** | User ID | Repo + commit SHA |
| **Revocation** | Delete access key | Update trust policy |
| **Compliance** | ⚠️ Requires key management | ✅ Meets zero-trust requirements |

## References

- [GitHub: Security hardening with OpenID Connect](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [AWS: IAM roles for GitHub Actions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)
- [GitHub Actions: configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials)

## Recommendation

Use **Option A (OIDC)** for production deployments. The initial setup takes 5 extra minutes but provides:
- ✅ Better security
- ✅ No credential management
- ✅ Automatic rotation
- ✅ Detailed audit trail
- ✅ Granular access control

Only use access keys (Option B) for:
- Quick proof-of-concepts
- Legacy systems that don't support OIDC
- Organizations with strict IAM policies preventing OIDC setup
