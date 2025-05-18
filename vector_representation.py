from langchain.embeddings import OpenAIEmbeddings
from langchain.evaluation import load_evaluator
import os
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAIEmbeddings object
embedding_function = OpenAIEmbeddings()

# Get the embedding for a sample text
vector = embedding_function.embed_query("apple")

# Print the embedding vector
print("Embedding vector:", vector)

# Print the length of the embedding vector
print("Length of embedding vector:", len(vector))
