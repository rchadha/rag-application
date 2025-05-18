from langchain_community.embeddings import OpenAIEmbeddings
from langchain.evaluation import load_evaluator
import os
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Load the evaluator
evaluator = load_evaluator("pairwise_embedding_distance")

# Define the two outputs to compare
output_1 = "A sad boy is walking."
output_2 = "A little boy is walking"

# Evaluate similarity
result = evaluator.evaluate_string_pairs(prediction="A sad boy is walking", 
                                         prediction_b="A little boy is walking")

# Print result
print("Embedding distance result:")
print(result)


