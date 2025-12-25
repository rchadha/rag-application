from langchain_community.embeddings import OpenAIEmbeddings
from langchain.evaluation import load_evaluator
import os
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

evaluator = load_evaluator("pairwise_embedding_distance")
prediction_a = "cat"
prediction_b = "programmer"
result = evaluator.evaluate_string_pairs(prediction=prediction_a, 
                                         prediction_b=prediction_b)
# Print result
print("Embedding distance for the pair:", prediction_a, "and", prediction_b)
print(result)


