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
CHAT_MODEL_NAME = "gpt-5.4"
MIN_RELEVANCE_SCORE = 0.35
LANGSMITH_PROJECT = get_langsmith_project("rag-application-sec")

PROMPT = """
Answer the question based only on the following context:
{context}

Answer the question based on the above context: {question}
"""

@traceable(name="generate_answer")
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
def query_database(
    query_text: str,
    dataset: str = "sec",
    use_reranker: bool = False,
    candidate_k: int = 10,
    final_k: int = 3,
):
    print(f"Querying dataset '{dataset}' with query: {query_text}")
    results = get_top_results(
        query_text,
        dataset=dataset,
        candidate_k=candidate_k,
        final_k=final_k,
        use_reranker=use_reranker,
    )
    if len(results) == 0 or results[0]["vector_score"] < MIN_RELEVANCE_SCORE:
        print("Unable to find matching results")
        return
    return generate_answer(query_text, results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The text to query")
    parser.add_argument("--dataset", choices=["sec", "earnings"], default="sec")
    parser.add_argument("--use-reranker", action="store_true")
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--final-k", type=int, default=3)
    args = parser.parse_args()
    with tracing_context(
        project_name=LANGSMITH_PROJECT,
        enabled=is_langsmith_enabled(),
        tags=[args.dataset, "rag", "query"],
        metadata={
            "collection": get_collection_name(args.dataset),
            "embedding_model": EMBEDDING_MODEL_NAME,
            "cross_encoder_model": CROSS_ENCODER_MODEL_NAME,
            "use_reranker": args.use_reranker,
        },
    ):
        print(
            query_database(
                args.query_text,
                dataset=args.dataset,
                use_reranker=args.use_reranker,
                candidate_k=args.candidate_k,
                final_k=args.final_k,
            )
        )

if __name__ == "__main__":
    main()
