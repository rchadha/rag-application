import argparse
# from dataclasses import dataclass
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

# Load the API key from the .env file
load_dotenv()
CHROMA_PATH = "chroma"

PROMPT = """
Answer the question based on the following context:
{context}

Answer the question based on the above context: {question}
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The text to query")
    args = parser.parse_args()
    query_text = args.query_text

    # Prepare the DB
    embedding_function = OpenAIEmbeddings()
    db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embedding_function)

    # Search the DB
    results = db.similarity_search_with_relevance_scores(query_text, k=3)
    # Print the results
    print("Results:", results[0])
    if len(results) == 0 or results[0][1] < 0.7:
        print("Unable to find matching results")
        return
    
    context_text = "\n\n---\n\n".join([doc.page_content for doc, _score in results])
    promt_template = ChatPromptTemplate.from_template(PROMPT)
    prompt = promt_template.format(context=context_text, question=query_text)
    print(f"Prompt: {prompt}")

    model = ChatOpenAI()
    response = model(prompt)

    sources = [doc.metadata["source"] for doc, _score in results]
    formatted_response = f"Response: {response}\n\nSources: {', '.join(sources)}"
    print(formatted_response)

if __name__ == "__main__":
    main()