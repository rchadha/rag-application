from langchain_community.embeddings import OpenAIEmbeddings
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt
import os
from dotenv import load_dotenv


# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Step 1: Initialize embedding function
embedding_function = OpenAIEmbeddings()

# Step 2: Define your sentences
sentences = [
    "Paris is the capital of France.",               # Sentence 1
    # "The capital city of France is Paris.",          # Sentence 2 (similar)
    "Apples are a type of fruit that grow on trees." # Sentence 3 (different)
]

# Step 3: Get embeddings
embeddings = [embedding_function.embed_query(sentence) for sentence in sentences]

# Step 4: Apply PCA to reduce dimensions to 2D
pca = PCA(n_components=2)
reduced = pca.fit_transform(embeddings)

# Step 5: Plot the embeddings
plt.figure(figsize=(10, 10))
colors = ['blue', 'green']
labels = ['Sentence 1', 'Sentence 2']

for i in range(len(sentences)):
    plt.scatter(reduced[i, 0], reduced[i, 1], color=colors[i], label=labels[i])
    plt.annotate(labels[i], (reduced[i, 0]+0.01, reduced[i, 1]+0.01))

plt.title("2D PCA of Sentence Embeddings")
plt.xlabel("PCA Component 1")
plt.ylabel("PCA Component 2")
plt.grid(True)
plt.legend()
plt.show()