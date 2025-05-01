from openai import OpenAI
import os
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Set your API key
openai.api_key = OPENAI_API_KEY


# Words to embed
words = ["apple", "iPhone", "banana", "Samsung"]

# Get embeddings from OpenAI
def get_embedding(text, model="text-embedding-3-small"):
    response = client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding

embeddings = [get_embedding(word) for word in words]

# Reduce dimensionality
pca = PCA(n_components=2)
reduced = pca.fit_transform(embeddings)

# Plot
plt.figure(figsize=(8, 6))
for i, word in enumerate(words):
    x, y = reduced[i]
    plt.scatter(x, y)
    plt.text(x + 0.01, y + 0.01, word, fontsize=12)

plt.title("2D PCA of Embeddings")
plt.grid(True)
plt.xlabel("PCA Component 1")
plt.ylabel("PCA Component 2")
plt.show()
