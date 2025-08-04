# apps/common/utils/llm_loader.py

import json
from pathlib import Path
from politiekmatcher import settings
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

from transformers import BitsAndBytesConfig
import torch


def load_local_llm():
    config_path = Path(settings.BASE_DIR) / "models/llm_config.json"
    if not config_path.exists():
        raise FileNotFoundError("⚠️ LLM config not found. Run `setup_local_llm` first.")

    with open(config_path, "r") as f:
        config = json.load(f)

    model_path = config["model_path"]
    system_info = config["system_info"]

    # Device logic
    if system_info["has_cuda"] and system_info["gpu_memory_gb"] >= 16:
        quantization_config = None
        device_map = "auto"
        torch_dtype = torch.float16
    elif system_info["has_cuda"]:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        device_map = "auto"
        torch_dtype = None
    else:
        quantization_config = None
        device_map = None
        torch_dtype = torch.float32

    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map=device_map,
        quantization_config=quantization_config,
        torch_dtype=torch_dtype,
        trust_remote_code=True,
    )

    llm = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        do_sample=True,
        temperature=0.1,
        pad_token_id=tokenizer.eos_token_id,
        device=0 if torch.cuda.is_available() else -1,
    )

    return llm


from sentence_transformers import SentenceTransformer
import re

# Global model cache to avoid reloading
_embedding_model = None


def get_embedding_model():
    """Get the embedding model, using cache if available."""
    global _embedding_model

    if _embedding_model is None:
        try:
            # Try to use the Dutch-specific model first
            _embedding_model = SentenceTransformer("GroNLP/bert-base-dutch-cased")
        except:
            try:
                # Fallback to multilingual model
                _embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")
            except:
                # Ultimate fallback
                _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    return _embedding_model


def embed_text(text, max_retries=3):
    """Embed text with improved preprocessing for Dutch political content."""
    import nltk
    from nltk.corpus import stopwords

    nltk.download("stopwords", quiet=True)
    stop_words = set(stopwords.words("dutch"))

    # Clean each text by removing stopwords
    words = text.split(" ")
    filtered_words = [word for word in words if word.lower() not in stop_words]
    cleaned_text = " ".join(filtered_words)

    # Get the cached model
    model = get_embedding_model()

    # Generate embedding with normalization
    embedding = model.encode(cleaned_text, normalize_embeddings=True)

    # Convert to list for JSON storage
    return embedding.tolist()


def embed_text_batch(texts: list):
    """Embed a batch of texts using the local LLM with stopword removal."""
    import nltk
    from nltk.corpus import stopwords
    from sentence_transformers import SentenceTransformer

    nltk.download("stopwords", quiet=True)
    stop_words = set(stopwords.words("dutch"))

    # Clean each text by removing stopwords
    cleaned_texts = []
    for text in texts:
        words = text.split()
        filtered_words = [word for word in words if word.lower() not in stop_words]
        cleaned_texts.append(" ".join(filtered_words))

    model = get_embedding_model()
    return model.encode(
        cleaned_texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()
