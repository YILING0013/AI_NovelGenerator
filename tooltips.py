# tooltips.py
# -*- coding: utf-8 -*-

tooltips = {
    "api_key": "Enter your API Key here. For OpenAI, get it from https://platform.openai.com/account/api-keys.",
    "base_url": "The API endpoint for the model. For OpenAI: https://api.openai.com/v1. For local Ollama: e.g., http://localhost:11434/v1. Not needed for Gemini.",
    "interface_format": "Specifies the LLM interface compatibility (OpenAI, DeepSeek, Ollama, ML Studio, Gemini, etc.).\n\nNote: OpenAI compatibility refers to any API following that standard, not just api.openai.com.",
    "model_name": "The name of the model to use (e.g., deepseek-reasoner, gpt-4o). For Ollama, use your local model name.",
    "temperature": "Controls the randomness of generated text. Higher values are more creative, lower values are more consistent.",
    "max_tokens": "Limits the maximum tokens per generation. Range: 1-100,000.\n"+
                  "Common maximums:\n"+
                  "o1: 100,000\n"+
                  "o1-mini: 65,536\n"+
                  "gpt-4o: 16,384\n"+
                  "gpt-4o-mini: 16,384\n"+
                  "deepseek-reasoner: 8,192\n"+
                  "deepseek-chat: 4,096\n",
    "embedding_api_key": "API Key required for the Embedding model.",
    "embedding_interface_format": "The style of the Embedding API (OpenAI or Ollama).",
    "embedding_url": "The endpoint for the Embedding model.",
    "embedding_model_name": "The name of the Embedding model (e.g., text-embedding-3-small).",
    "embedding_retrieval_k": "Number of Top-K results returned during vector retrieval.",
    "topic": "General theme or main story background description of the novel.",
    "genre": "Genre of the novel (e.g., Fantasy, Sci-Fi, Urban).",
    "num_chapters": "Expected total number of chapters.",
    "word_number": "Target word count per chapter.",
    "filepath": "Root directory for generated files (txt files, vector store, etc.).",
    "chapter_num": "Current chapter number being processed.",
    "user_guidance": "Additional instructions or writing guidance for the current chapter.",
    "characters_involved": "List of characters to focus on or who impact the plot in this chapter.",
    "key_items": "Important props, clues, or items appearing in this chapter.",
    "scene_location": "Main location or scene description for this chapter.",
    "time_constraint": "Time pressure or deadline elements in this chapter's plot.",
    "interface_config": "Select the AI interface configuration to use."
}
