from flask import Flask, request, jsonify
from flask_cors import CORS
from query_data import query_database
import os
import boto3
from botocore.exceptions import ClientError


_secrets_loaded = False


def _load_secrets() -> None:
    """Fetch secrets from AWS SSM Parameter Store on first request. No-op if already in environment."""
    global _secrets_loaded
    if _secrets_loaded:
        return

    project = os.environ.get("PROJECT_NAME", "rag-application")
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("ssm", region_name=region)

    param_map = {
        f"/{project}/openai-api-key": "OPENAI_API_KEY",
        f"/{project}/pinecone-api-key": "PINECONE_API_KEY",
    }
    for param_name, env_key in param_map.items():
        if os.environ.get(env_key):
            continue
        try:
            response = client.get_parameter(Name=param_name, WithDecryption=True)
            os.environ[env_key] = response["Parameter"]["Value"]
        except ClientError as e:
            print(f"Warning: could not fetch parameter {param_name}: {e}")

    _secrets_loaded = True

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/query', methods=['POST'])
def query():
    _load_secrets()
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
