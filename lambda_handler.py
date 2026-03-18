"""
AWS Lambda handler — wraps the Flask app using aws-wsgi.
Lambda receives API Gateway events and forwards them to the Flask app.
"""
import awsgi
from app import app


def handler(event, context):
    return awsgi.response(app, event, context)
