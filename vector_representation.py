from langchain.embeddings import OpenAIEmbeddings
from langchain.evaluation import load_evaluator
import os
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAIEmbeddings object
embedding_function = OpenAIEmbeddings()

word_to_embed = "software engineer"

# Get the embedding for a sample text
vector = embedding_function.embed_query(word_to_embed)

# Print the length of the embedding vector
print("Length of embedding vector:", len(vector))

# Print the embedding vector
# print(f"Embedding vector for '{word_to_embed}':", vector[:10], "...")
# Print the embedding vector with 4 decimal places
print(f"Embedding vector for '{word_to_embed}':", [round(val, 4) for val in vector[:10]], "...")

