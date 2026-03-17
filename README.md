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
