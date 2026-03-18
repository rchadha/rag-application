"""
AWS Lambda handler — wraps the Flask app using apig-wsgi.
Lambda receives API Gateway events and forwards them to the Flask app.
"""
from apig_wsgi import make_lambda_handler
from app import app

handler = make_lambda_handler(app)
