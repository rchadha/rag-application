## Setup Project
### Clone the project
```
git clone git@github.com:rchadha/rag-application.git
```

#### Setup Virtual Env

```
# Create venv
python3 -m venv rag-application
# Activate
source rag-application/bin/activate
```

### Deactivate venv
```
deactivate
```
### Delete a Virtual Environment
```
rm -rf rag-application
```

### Install packages
```
pip install -r requirements.txt
```

### Optional: Enable LangSmith observability
Add these variables to `.env` to capture indexing and query traces in LangSmith:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY="your-langsmith-api-key"
LANGSMITH_PROJECT="rag-application-sec"
```

### Create Vector DB
```
python create_database.py
```

To index earnings call transcripts instead of SEC filings:

```bash
python create_database.py --dataset earnings
```

To download earnings call transcripts first:

```bash
python data/download-earnings-calls.py
```

### Query 
```
python query_data.py "What is AWS Lambda?"
```

To query earnings calls:

```bash
python query_data.py --dataset earnings "What did NVIDIA say about demand?"
```

### Run Flask App
```
# Create venv
python3 -m venv rag-application
# Activate
source rag-application/bin/activate
# Run Flask App
python app.py

```

### Demo
What is AWS Lambda?
What programming languages does it support?
Is it free to use AWS Lambda?
Is AWS Lambda deployed on EC2?
What is serverless land?

---

## Ingestion

### Run locally
```bash
# Ingest last 1 day of news + Reddit for NVDA (default)
python ingest_social.py --ticker NVDA --company "NVIDIA"

# Ingest last 7 days for a different ticker
python ingest_social.py --ticker AMD --company "AMD" --days 7

# News only, or Reddit only
python ingest_social.py --ticker NVDA --company "NVIDIA" --sources news
python ingest_social.py --ticker NVDA --company "NVIDIA" --sources reddit
```

### Trigger ingestion Lambda manually (backfill or ad-hoc run)
```bash
aws lambda invoke \
  --function-name rag-application-ingest \
  --payload '{"tickers":[{"ticker":"NVDA","company":"NVIDIA"}],"days":1}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  /tmp/ingest_response.json && cat /tmp/ingest_response.json
```

To run for multiple tickers or backfill more days:
```bash
aws lambda invoke \
  --function-name rag-application-ingest \
  --payload '{"tickers":[{"ticker":"NVDA","company":"NVIDIA"},{"ticker":"AMD","company":"AMD"}],"days":7}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  /tmp/ingest_response.json && cat /tmp/ingest_response.json
```

### Automated daily cron
An EventBridge Scheduler runs `rag-application-ingest` every day at **6 AM UTC** (just after US markets close overnight, before open).

To add or remove tickers from the daily run, update `terraform/terraform.tfvars`:
```hcl
ingest_tickers = "[{\"ticker\":\"NVDA\",\"company\":\"NVIDIA\"},{\"ticker\":\"AMD\",\"company\":\"AMD\"}]"
```
Then apply:
```bash
cd terraform && terraform apply
```

---

## Deployment

### Build and push Docker image
```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 359208843644.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 --provenance=false \
  -t rag-application:latest \
  -t 359208843644.dkr.ecr.us-east-1.amazonaws.com/rag-application:latest .

docker push 359208843644.dkr.ecr.us-east-1.amazonaws.com/rag-application:latest
```

### Update Lambdas to latest image
```bash
aws lambda update-function-code \
  --function-name rag-application \
  --image-uri 359208843644.dkr.ecr.us-east-1.amazonaws.com/rag-application:latest \
  --region us-east-1

aws lambda update-function-code \
  --function-name rag-application-ingest \
  --image-uri 359208843644.dkr.ecr.us-east-1.amazonaws.com/rag-application:latest \
  --region us-east-1
```

### Terraform (infrastructure changes)
```bash
cd terraform
terraform plan
terraform apply
```
