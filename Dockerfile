# AWS Lambda container image
FROM public.ecr.aws/lambda/python:3.13

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger_eng')"

# Copy application code
COPY *.py ./

# Lambda handler
CMD ["lambda_handler.handler"]
