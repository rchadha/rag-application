from langchain_community.document_loaders import DirectoryLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from langsmith import traceable, tracing_context
from dotenv import load_dotenv
import os
import re
import nltk
from langsmith_config import get_langsmith_project, is_langsmith_enabled
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('averaged_perceptron_tagger_eng')

# Load the API key from the .env file
load_dotenv()

DATA_PATH = "data"
SEC_FILINGS_PATH = os.path.join(DATA_PATH, "sec_filings_nvda")
EARNINGS_CALLS_PATH = os.path.join(DATA_PATH, "earnings_calls_nvda")
SEC_NAMESPACE = "sec_filings_nvda"
EARNINGS_NAMESPACE = "earnings_calls_nvda"
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "rag-application")
LANGSMITH_PROJECT = get_langsmith_project("rag-application-sec")

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        choices=["sec", "earnings"],
        default="sec",
        help="Which dataset to index",
    )
    args = parser.parse_args()

    dataset_config = get_dataset_config(args.dataset)
    with tracing_context(
        project_name=LANGSMITH_PROJECT,
        enabled=is_langsmith_enabled(),
        tags=[dataset_config["trace_tag"], "indexing"],
        metadata={
            "namespace": dataset_config["namespace"],
            "embedding_model": EMBEDDING_MODEL_NAME,
            "dataset": args.dataset,
        },
    ):
        index_documents(dataset_config)

def get_dataset_config(dataset_name: str):
    if dataset_name == "earnings":
        return {
            "dataset_name": EARNINGS_NAMESPACE,
            "namespace": EARNINGS_NAMESPACE,
            "path": EARNINGS_CALLS_PATH,
            "globs": ["*.txt", "*.docx"],
            "chunk_size": 800,
            "chunk_overlap": 120,
            "trace_tag": "earnings",
            "loader_name": "earnings_calls",
        }

    return {
        "dataset_name": SEC_NAMESPACE,
        "namespace": SEC_NAMESPACE,
        "path": SEC_FILINGS_PATH,
        "globs": ["*.txt"],
        "chunk_size": 1200,
        "chunk_overlap": 200,
        "trace_tag": "sec",
        "loader_name": "sec_filings",
    }

@traceable(name="index_documents")
def index_documents(dataset_config: dict):
    documents = load_documents(
        dataset_path=dataset_config["path"],
        file_globs=dataset_config["globs"],
        loader_name=dataset_config["loader_name"],
    )
    chunks = split_documents_into_chunks(
        documents,
        chunk_size=dataset_config["chunk_size"],
        chunk_overlap=dataset_config["chunk_overlap"],
    )
    chunks = add_dataset_metadata(chunks, dataset_name=dataset_config["dataset_name"])
    rebuild_collection(chunks, namespace=dataset_config["namespace"])

@traceable(name="load_documents")
def load_documents(dataset_path: str, file_globs: list[str], loader_name: str):
    print(f"Loading {loader_name} documents from: {dataset_path}")
    documents = []

    for file_glob in file_globs:
        if file_glob.endswith(".docx"):
            loader_cls = Docx2txtLoader
            loader_kwargs = {}
        else:
            loader_cls = TextLoader
            loader_kwargs = {"encoding": "utf-8"}

        loader = DirectoryLoader(
            dataset_path,
            glob=file_glob,
            loader_cls=loader_cls,
            loader_kwargs=loader_kwargs,
        )
        documents.extend(loader.load())

    print(f"Loaded {len(documents)} {loader_name} documents")
    return documents

@traceable(name="split_documents_into_chunks")
def split_documents_into_chunks(documents: list[Document], chunk_size: int, chunk_overlap: int):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=True
    )
    chunks = splitter.split_documents(documents)
    print(f"Split {len(documents)} documents into {len(chunks)} chunks")

    if len(chunks) > 20:
        document = chunks[20]
        print(document.page_content)
        print(document.metadata)

    return chunks

@traceable(name="add_dataset_metadata")
def add_dataset_metadata(chunks: list[Document], dataset_name: str):
    prepared_chunks = []

    for chunk_index, chunk in enumerate(chunks):
        metadata = dict(chunk.metadata)
        source_name = os.path.basename(metadata.get("source", ""))
        filing_details = extract_filing_details(source_name)
        earnings_call_details = extract_earnings_call_details(source_name)
        metadata["dataset"] = dataset_name
        metadata["chunk_id"] = f"{dataset_name}-chunk-{chunk_index}"
        metadata.update(filing_details)
        metadata.update(earnings_call_details)
        chunk.metadata = metadata
        prepared_chunks.append(chunk)

    return prepared_chunks

def extract_filing_details(source_name: str):
    match = re.match(r"(?P<filing_date>\d{4}-\d{2}-\d{2})_(?P<form_type>[^_]+)_(?P<accession_number>.+)\.txt", source_name)
    if not match:
        return {}

    details = match.groupdict()
    details["ticker"] = "NVDA"
    return details

def extract_earnings_call_details(source_name: str):
    match = re.match(
        r"(?P<call_date>\d{4}-\d{2}-\d{2})_(?P<quarter>q[1-4])_(?P<call_type>.+)\.txt",
        source_name,
        re.IGNORECASE,
    )
    if not match:
        return {}

    details = match.groupdict()
    details["ticker"] = "NVDA"
    details["quarter"] = details["quarter"].upper()
    details["call_type"] = details["call_type"].replace("_", " ")
    return details

@traceable(name="rebuild_collection")
def rebuild_collection(chunks: list[Document], namespace: str):
    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(PINECONE_INDEX_NAME)

    # Delete all existing vectors in this namespace before re-indexing
    try:
        index.delete(delete_all=True, namespace=namespace)
        print(f"Deleted existing vectors in namespace: {namespace}")
    except Exception as e:
        print(f"Could not delete namespace {namespace} (may not exist yet): {e}")

    PineconeVectorStore.from_documents(
        chunks,
        embedding_function,
        index_name=PINECONE_INDEX_NAME,
        namespace=namespace,
    )

    print(f"Saved {len(chunks)} chunks to namespace '{namespace}' in Pinecone index '{PINECONE_INDEX_NAME}'")

if __name__ == "__main__":
    main()
