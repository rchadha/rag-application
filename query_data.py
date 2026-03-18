import argparse
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable, tracing_context
from dotenv import load_dotenv
import os
from langsmith_config import get_langsmith_project, is_langsmith_enabled
from retrieval import (
    CROSS_ENCODER_MODEL_NAME,
    EMBEDDING_MODEL_NAME,
    get_collection_name,
    get_top_results,
)

# Load the API key from the .env file
load_dotenv()
CHAT_MODEL_NAME = "gpt-4o"
MIN_RELEVANCE_SCORE = 0.35
LANGSMITH_PROJECT = get_langsmith_project("rag-application-sec")

PROMPT = """
Answer the question based only on the following context:
{context}

Answer the question based on the above context: {question}
"""

def get_collection_config(dataset_name: str):
    if dataset_name == "earnings":
        return {"dataset": "earnings", "trace_tag": "earnings"}
    if dataset_name == "social":
        return {"dataset": "social", "trace_tag": "social"}
    if dataset_name == "news":
        return {"dataset": "news", "trace_tag": "news"}
    return {"dataset": "sec", "trace_tag": "sec"}

@traceable(name="generate_sec_answer")
def generate_answer(query_text: str, results):
    context_text = "\n\n---\n\n".join(
        [result["content"] for result in results]
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
    sources = []
    for result in results:
        if result["source"] not in sources:
            sources.append(result["source"])
    return {
        "response": response_text,
        "sources": sources,
        "retrieval": [
            {
                "source": result["source"],
                "vector_score": result.get("vector_score"),
                "rerank_score": result.get("rerank_score"),
            }
            for result in results
        ],
    }

@traceable(name="query_database")
def query_database(query_text: str, dataset: str = "sec", use_reranker: bool = False):
    print(f"Querying Vector DB with Query: {query_text}")
    results = get_top_results(query_text, dataset=dataset, use_reranker=use_reranker)
    if not results:
        print("Unable to find matching results")
        return
    return generate_answer(query_text, results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The text to query")
    parser.add_argument(
        "--dataset",
        choices=["sec", "earnings", "social", "news"],
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
            "dataset": args.dataset,
            "embedding_model": EMBEDDING_MODEL_NAME,
        },
    ):
        print(query_database(args.query_text, dataset=collection_config["dataset"]))

if __name__ == "__main__":
    main()
