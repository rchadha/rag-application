## Setup Virtual Env

### Create a Virtual Environment:
```
python3 -m venv rag-application
```
### Activate the Virtual Environment:
```
source rag-application/bin/activate
```
### Install the Package: Inside the virtual environment, run:
```
pip install chromadb
```
### Deactivate the Environment (When Done):
```
deactivate
```

## Steps to Delete a Virtual Environment
Locate the folder containing the virtual environment. By default, it will have the name you provided when creating it (e.g., myenv).

### Use the following command to delete the folder:

```
rm -rf rag-application
```
