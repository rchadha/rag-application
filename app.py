from flask import Flask, request, jsonify
from flask_cors import CORS
from query_data import query_database
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from retrieval import PINECONE_INDEX_NAME, EMBEDDING_MODEL_NAME, COLLECTIONS
import os
import json
import boto3
from botocore.exceptions import ClientError


_secrets_loaded = False


def _load_secrets() -> None:
    """Fetch secrets from AWS Secrets Manager on first request. No-op if already in environment."""
    global _secrets_loaded
    if _secrets_loaded:
        return

    def _fetch(secret_name: str, env_key: str) -> None:
        if os.environ.get(env_key):
            return
        try:
            client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            response = client.get_secret_value(SecretId=secret_name)
            secret = response.get("SecretString", "")
            try:
                os.environ[env_key] = json.loads(secret)
            except (json.JSONDecodeError, TypeError):
                os.environ[env_key] = secret
        except ClientError as e:
            print(f"Warning: could not fetch secret {secret_name}: {e}")

    project = os.environ.get("PROJECT_NAME", "rag-application")
    _fetch(f"{project}/openai-api-key", "OPENAI_API_KEY")
    _fetch(f"{project}/pinecone-api-key", "PINECONE_API_KEY")
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

@app.route('/status', methods=['GET'])
def status():
    _load_secrets()
    try:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()

        result = {}
        for dataset, namespace in COLLECTIONS.items():
            ns_stats = stats.namespaces.get(namespace, {})
            vector_count = ns_stats.get("vector_count", 0)
            last_updated = None

            # For news, find the latest published_at from a sample query
            if dataset == "news" and vector_count > 0:
                store = PineconeVectorStore(
                    index_name=PINECONE_INDEX_NAME,
                    namespace=namespace,
                    embedding=OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME),
                )
                docs = store.similarity_search("NVIDIA", k=50)
                dates = [
                    doc.metadata["published_at"]
                    for doc in docs
                    if doc.metadata.get("published_at")
                ]
                if dates:
                    last_updated = max(dates)

            result[dataset] = {
                "vector_count": vector_count,
                "last_updated": last_updated,
            }

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Use environment variable for port, default to 3001
    port = int(os.environ.get('PORT', 3001))
    # Disable debug in production
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
