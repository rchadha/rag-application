from flask import Flask, request, jsonify
from query_data import query_database

app = Flask(__name__)
@app.route('/query', methods=['POST'])
def query():
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Invalid input'}), 400

    query_string = data['query']
    result = query_database(query_string)

    if result is None:
        return jsonify({'error': 'Query failed'}), 500

    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

