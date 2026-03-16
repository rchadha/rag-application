from langchain_community.document_loaders import DirectoryLoader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
import os
import re
import nltk
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('averaged_perceptron_tagger_eng')

# Load the API key from the .env file
load_dotenv()

DATA_PATH = "data"
CHROMA_PATH = "chroma"
SEC_FILINGS_PATH = os.path.join(DATA_PATH, "sec_filings_nvda")
SEC_COLLECTION_NAME = "sec_filings_nvda"
EMBEDDING_MODEL_NAME = "text-embedding-3-small"

def main():
    index_sec_filings_documents()

def index_sec_filings_documents():
    documents = load_sec_filings_documents()
    chunks = split_documents_into_chunks(documents)
    chunks = add_dataset_metadata(chunks, dataset_name=SEC_COLLECTION_NAME)
    rebuild_collection(chunks, collection_name=SEC_COLLECTION_NAME)

def load_sec_filings_documents():
    print(f"Loading SEC filings from: {SEC_FILINGS_PATH}")
    filings_loader = DirectoryLoader(
        SEC_FILINGS_PATH,
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = filings_loader.load()
    print(f"Loaded {len(documents)} SEC filing documents")
    return documents

def split_documents_into_chunks(documents: list[Document]):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=200,
        length_function=len,
        add_start_index=True
    )
    chunks = splitter.split_documents(documents)
    print(f"Split {len(documents)} documents into {len(chunks)} chunks")

    document = chunks[20]
    print(document.page_content)
    print(document.metadata)

    return chunks

def add_dataset_metadata(chunks: list[Document], dataset_name: str):
    prepared_chunks = []

    for chunk_index, chunk in enumerate(chunks):
        metadata = dict(chunk.metadata)
        source_name = os.path.basename(metadata.get("source", ""))
        filing_details = extract_filing_details(source_name)
        metadata["dataset"] = dataset_name
        metadata["chunk_id"] = f"{dataset_name}-chunk-{chunk_index}"
        metadata.update(filing_details)
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

def rebuild_collection(chunks: list[Document], collection_name: str):
    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    existing_db = Chroma(
        collection_name=collection_name,
        persist_directory=CHROMA_PATH,
        embedding_function=embedding_function,
    )

    try:
        existing_db.delete_collection()
        print(f"Deleted existing collection: {collection_name}")
    except Exception:
        print(f"Collection {collection_name} does not exist yet. Creating it now.")

    Chroma.from_documents(
        chunks,
        embedding_function,
        persist_directory=CHROMA_PATH,
        collection_name=collection_name,
    )

    print(f"Saved {len(chunks)} chunks to collection '{collection_name}' in {CHROMA_PATH}")

if __name__ == "__main__":
    main()
