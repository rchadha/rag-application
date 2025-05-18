from langchain_community.embeddings import OpenAIEmbeddings
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt
import os
import numpy as np
from dotenv import load_dotenv


# Load the API key from the .env file
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

sentences = [
    "Paris is the capital of France.",
    "The capital city of France is Paris.",
    "Apples are a type of fruit that grow on trees."
]

embedding_function = OpenAIEmbeddings()
embeddings = [embedding_function.embed_query(sentence) for sentence in sentences]
embedding_array = np.array(embeddings)

# Set perplexity < number of sentences (3)
tsne = TSNE(n_components=2, perplexity=2, learning_rate=200, random_state=42)
reduced = tsne.fit_transform(embedding_array)

plt.figure(figsize=(7, 7))
colors = ['blue', 'green', 'red']
labels = ['Sentence 1', 'Sentence 2', 'Sentence 3']

for i in range(len(sentences)):
    plt.scatter(reduced[i, 0], reduced[i, 1], color=colors[i], label=labels[i])
    plt.annotate(labels[i], (reduced[i, 0]+1, reduced[i, 1]+1))

plt.title("2D t-SNE of Sentence Embeddings")
plt.xlabel("t-SNE Component 1")
plt.ylabel("t-SNE Component 2")
plt.grid(True)
plt.legend()
plt.show()