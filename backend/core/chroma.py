# backend/core/chroma.py
import os
from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

BACKEND_DIR = Path(__file__).resolve().parent.parent
CHROMA_DATA_PATH = str(BACKEND_DIR / "chroma_db")

# Point ONNX model cache to backend/.cache so it's always self-contained in the project
ONNX_CACHE_DIR = BACKEND_DIR / ".cache" / "onnx_models" / ONNXMiniLM_L6_V2.MODEL_NAME
ONNXMiniLM_L6_V2.DOWNLOAD_PATH = ONNX_CACHE_DIR

COLLECTION_NAME = "unikl_programs"


def get_chroma_client():
    """Initializes and returns a persistent ChromaDB client."""
    os.makedirs(CHROMA_DATA_PATH, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DATA_PATH)


def get_program_collection():
    """Returns the persistent ChromaDB collection for UniKL academic programmes."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "UniKL Academic Programmes for Major Selection RAG"}
    )

