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

### Create Vector DB
```
python create_database.py
```

### Query 
```
python query_data.py "What is AWS Lambda?"
```

