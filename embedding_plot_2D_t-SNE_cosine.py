from langchain_community.embeddings import OpenAIEmbeddings
from sklearn.manifold import TSNE
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import numpy as np
import os
from dotenv import load_dotenv


# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Step 1: Sentences
sentences = [
    "Paris is the capital of France.",
    "Apples are a type of fruit that grow on trees.",
    
]

# Step 2: Generate embeddings
embedding_function = OpenAIEmbeddings()
embeddings = [embedding_function.embed_query(sentence) for sentence in sentences]
embedding_array = np.array(embeddings)

# Step 3: Cosine similarity matrix
similarity_matrix = cosine_similarity(embedding_array)
print("Cosine Similarity Matrix:")
print(similarity_matrix)

# Step 4: t-SNE visualization
tsne = TSNE(n_components=2, perplexity=1, learning_rate=200, random_state=42)
reduced = tsne.fit_transform(embedding_array)

# Step 5: Plot
plt.figure(figsize=(7, 7))
colors = ['blue', 'green', 'red']
labels = ['Sentence 1', 'Sentence 2']

for i in range(len(sentences)):
    plt.scatter(reduced[i, 0], reduced[i, 1], color=colors[i], label=labels[i])
    plt.annotate(labels[i], (reduced[i, 0] + 1, reduced[i, 1] + 1))

plt.title("2D t-SNE of Sentence Embeddings")
plt.xlabel("t-SNE Component 1")
plt.ylabel("t-SNE Component 2")
plt.grid(True)
plt.legend()
plt.show()
