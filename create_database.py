from langchain_community.document_loaders import DirectoryLoader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
import openai 
from dotenv import load_dotenv
import os
import shutil
import nltk
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('averaged_perceptron_tagger_eng')

# Load the API key from the .env file
load_dotenv()

DATA_PATH = "data"
CHROMA_PATH = "chroma"

def main():
    indexing()

def indexing():
    documents = load_documents()
    chunks = split_documents_into_chunks(documents)
    save_to_vector_db(chunks)


def load_documents():
    print(DATA_PATH)
    loader = DirectoryLoader(DATA_PATH, glob="*.md")
    documents = loader.load()
    return documents

def split_documents_into_chunks(documents: list[Document]):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=100,
        length_function=len,
        add_start_index=True
    )
    chunks = splitter.split_documents(documents)
    print(f"Split {len(documents)} documents into {len(chunks)} chunks")

    document = chunks[20]
    print(document.page_content)
    print(document.metadata)

    return chunks

def save_to_vector_db(chunks: list[Document]):
    # Clear out the database first
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)
    
    # Initialize Chroma
    embedding_function = OpenAIEmbeddings()
    db = Chroma.from_documents(chunks, embedding_function, persist_directory=CHROMA_PATH)


    # # Add documents to Chroma
    print(f"Saved {len(chunks)} chunks to {CHROMA_PATH}")

    # Check the number of chunks saved
    # collections = db.list_collections()
    # num_chunks = sum(len(collection['documents']) for collection in collections)
    # print(f"Number of chunks saved in Chroma database: {num_chunks}")
    

if __name__ == "__main__":
    main()