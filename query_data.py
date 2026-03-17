import argparse
# from dataclasses import dataclass
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable, tracing_context
from dotenv import load_dotenv
import os
import re
from langsmith_config import get_langsmith_project, is_langsmith_enabled

# Load the API key from the .env file
load_dotenv()
CHROMA_PATH = "chroma"
SEC_COLLECTION_NAME = "sec_filings_nvda"
EARNINGS_COLLECTION_NAME = "earnings_calls_nvda"
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
CHAT_MODEL_NAME = "gpt-5.4"
MIN_RELEVANCE_SCORE = 0.35
LANGSMITH_PROJECT = get_langsmith_project("rag-application-sec")

PROMPT = """
Answer the question based only on the following context:
{context}

Answer the question based on the above context: {question}
"""

def normalize_text(text) -> str:
    if isinstance(text, list):
        text = " ".join(text)
    return re.sub(r"\s+", " ", text).strip()

def get_collection_config(dataset_name: str):
    if dataset_name == "earnings":
        return {
            "collection_name": EARNINGS_COLLECTION_NAME,
            "trace_tag": "earnings",
        }

    return {
        "collection_name": SEC_COLLECTION_NAME,
        "trace_tag": "sec",
    }

@traceable(name="retrieve_sec_documents")
def retrieve_documents(query_text: str, collection_name: str):
    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    db = Chroma(
        collection_name=collection_name,
        persist_directory=CHROMA_PATH,
        embedding_function=embedding_function,
    )
    return db.similarity_search_with_relevance_scores(query_text, k=3)

@traceable(name="generate_sec_answer")
def generate_answer(query_text: str, results):
    context_text = "\n\n---\n\n".join(
        [normalize_text(doc.page_content) for doc, _score in results]
    )
    context_preview = context_text[:500]
    if len(context_text) > 500:
        context_preview += "..."
    print(f"Context preview: {context_preview}")

    prompt_template = ChatPromptTemplate.from_template(PROMPT)
    prompt = prompt_template.format(context=context_text, question=query_text)

    model = ChatOpenAI(model=CHAT_MODEL_NAME)
    response = model.invoke(prompt)
    response_text = response.content if hasattr(response, 'content') else response
    sources = [doc.metadata["source"] for doc, _score in results]
    return {
        "response": response_text,
        "sources": sources
    }

@traceable(name="query_database")
def query_database(query_text: str, collection_name: str):
    print(f"Querying Vector DB with Query: {query_text}")
    results = retrieve_documents(query_text, collection_name)
    if len(results) == 0 or results[0][1] < MIN_RELEVANCE_SCORE:
        print("Unable to find matching results")
        return
    return generate_answer(query_text, results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The text to query")
    parser.add_argument(
        "--dataset",
        choices=["sec", "earnings"],
        default="sec",
        help="Which dataset to query",
    )
    args = parser.parse_args()
    collection_config = get_collection_config(args.dataset)
    with tracing_context(
        project_name=LANGSMITH_PROJECT,
        enabled=is_langsmith_enabled(),
        tags=[collection_config["trace_tag"], "rag", "query"],
        metadata={
            "collection": collection_config["collection_name"],
            "embedding_model": EMBEDDING_MODEL_NAME,
            "dataset": args.dataset,
        },
    ):
        print(query_database(args.query_text, collection_config["collection_name"]))

if __name__ == "__main__":
    main()
