from flask import Flask, request, jsonify
from flask_cors import CORS
from query_data import query_database
import os
import json
import boto3
from botocore.exceptions import ClientError


def _load_secret(secret_name: str, env_key: str) -> None:
    """Fetch a secret from AWS Secrets Manager and inject into os.environ."""
    if os.environ.get(env_key):
        return  # already set (e.g. local dev via .env)
    try:
        client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        response = client.get_secret_value(SecretId=secret_name)
        secret = response.get("SecretString", "")
        # Secrets Manager may return JSON or a plain string
        try:
            os.environ[env_key] = json.loads(secret)
        except (json.JSONDecodeError, TypeError):
            os.environ[env_key] = secret
    except ClientError as e:
        print(f"Warning: could not fetch secret {secret_name}: {e}")


# Bootstrap secrets on cold start (no-op if already in environment)
_PROJECT = os.environ.get("PROJECT_NAME", "rag-application")
_load_secret(f"{_PROJECT}/openai-api-key", "OPENAI_API_KEY")
_load_secret(f"{_PROJECT}/pinecone-api-key", "PINECONE_API_KEY")

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for ECS/ALB"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/query', methods=['POST'])
def query():
    data = request.get_json()
    print(f"Received data: {data}")
    if not data or 'query' not in data:
        return jsonify({'error': 'Invalid input'}), 400

    query_string = data['query']
    dataset = data.get('dataset', 'sec')
    use_reranker = bool(data.get('use_reranker', False))
    result = query_database(query_string, dataset=dataset, use_reranker=use_reranker)

    if result is None:
        return jsonify({'error': 'Query failed'}), 500

    return jsonify(result)

if __name__ == '__main__':
    # Use environment variable for port, default to 3001
    port = int(os.environ.get('PORT', 3001))
    # Disable debug in production
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
