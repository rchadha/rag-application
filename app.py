from flask import Flask, request, jsonify
from flask_cors import CORS
from query_data import query_database
import os

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
