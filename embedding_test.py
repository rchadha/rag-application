from langchain.embeddings import OpenAIEmbeddings
from langchain.evaluation import load_evaluator
import os
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Load the evaluator
evaluator = load_evaluator("pairwise_embedding_distance")

# Define the two outputs to compare
# output_1 = "Paris is the capital of France."
# output_2 = "The capital city of France is Paris."
output_1 = "Paris is the capital of France."
output_2 = "The capital city of France is Paris."

# Evaluate similarity
result = evaluator.evaluate_strings(prediction=output_1, prediction_b=output_2)

# Print result
print("Embedding distance result:")
print(result)


