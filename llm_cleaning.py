"""
LLM text cleaning module using Ollama.

Provides functions to clean OCR text using Qwen or other models via Ollama API.
All processing is done locally - no internet connection required.

Ollama must be installed and running locally. Models are downloaded once
and then run entirely on your machine.
"""

import requests
import json
from typing import Optional, Dict, Any
import os


def get_default_system_prompt() -> str:
    """
    Returns the default system prompt for OCR text cleaning.
    
    Returns:
        System prompt string
    """
    return """You are correcting OCR text from a historical document. Fix spelling errors, merge words that are hyphenated due to line wrapping, correct character recognition mistakes. Preserve all original content, numbers, punctuation and formatting. Do not add or remove information. 
    
    The OCR text may be in a different order than would be logical for a human reader. Reorder paragraphs or stray lines as necessary to preserve logical flow of articles on the newspaper page. Do not delete text, only reorder it.  

    Do not label articles with extraneous information. Do not add special characters or symbols to delineate paragraphs or articles. 

    When correcting words, carefully consider the historical context for spellings, especially for proper nouns, without prioritizing the most likely spelling based on the text context and OCR text."""


def build_user_prompt(text: str, context: Optional[str] = None) -> str:
    """
    Build user prompt with OCR text and optional context.
    
    Args:
        text: OCR text to be cleaned
        context: Optional contextual information (e.g., "This is a 1972 newspaper from New York. Contains classifieds and news articles.")
        
    Returns:
        User prompt string
    """
    prompt = "Please clean and correct the following OCR text and carefully reorder text blocks, as the column alignment have reordered paragraphs across articles.\n\n"
    
    if context:
        prompt += f"Context: {context}\n\n"
    
    prompt += text
    
    return prompt


def call_ollama(model: str, messages: list, base_url: str = "http://localhost:11434") -> str:
    """
    Call Ollama API to generate text (runs locally, no internet required).
    
    Args:
        model: Model name (e.g., 'qwen2.5') - must be installed locally
        messages: List of message dictionaries with 'role' and 'content' keys
        base_url: Ollama API base URL (default: http://localhost:11434 - local service)
        
    Returns:
        Generated text response
        
    Raises:
        RuntimeError: If API call fails with specific error details
        
    Note:
        This function communicates with a local Ollama instance. No internet
        connection is required once Ollama and the model are installed.
    """
    url = f"{base_url}/api/chat"
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=300)  # 5 minute timeout
        
        # Handle HTTP errors with specific messages
        if response.status_code == 404:
            raise RuntimeError(
                f"Local Ollama API endpoint not found at {base_url}. "
                f"Is Ollama installed and running? Start it with: ollama serve "
                f"(This is a local service - no internet needed)"
            )
        elif response.status_code == 400:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('error', {}).get('message', str(error_data))
            except:
                error_detail = response.text[:200]
            raise RuntimeError(
                f"Bad request to Ollama API: {error_detail}. "
                f"Check if model '{model}' is installed: ollama list"
            )
        elif response.status_code == 500:
            raise RuntimeError(
                f"Ollama server error. The model '{model}' may not be installed or "
                f"there may be insufficient memory. Try: ollama pull {model}"
            )
        
        response.raise_for_status()
        
        # Parse JSON response
        try:
            result = response.json()
        except ValueError as e:
            raise RuntimeError(f"Invalid JSON response from Ollama: {str(e)}")
        
        # Extract message content from response
        if 'message' in result and 'content' in result['message']:
            content = result['message']['content']
            if not content or not content.strip():
                raise RuntimeError("Ollama returned empty response. The model may have failed to generate text.")
            return content
        else:
            raise RuntimeError(
                f"Unexpected response format from Ollama. Expected 'message.content' but got: {list(result.keys())}"
            )
            
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            f"Cannot connect to local Ollama service at {base_url}. "
            f"Is Ollama installed and running? Start it with: ollama serve "
            f"(Note: Ollama runs locally - no internet connection needed)"
        )
    except requests.exceptions.Timeout as e:
        raise RuntimeError(
            f"Ollama API call timed out after 5 minutes. "
            f"The text may be too long or the model is too slow. "
            f"Try processing in smaller chunks."
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama API call failed: {str(e)}")
    except RuntimeError:
        # Re-raise our custom RuntimeErrors
        raise
    except Exception as e:
        raise RuntimeError(f"Unexpected error calling Ollama API: {str(e)}")


def check_ollama_available(base_url: str = "http://localhost:11434") -> bool:
    """
    Check if local Ollama service is running and accessible.
    
    Args:
        base_url: Ollama API base URL (default: localhost)
        
    Returns:
        True if Ollama is available, False otherwise
        
    Note:
        This checks the local Ollama service. No internet connection required.
    """
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def get_available_models(base_url: str = "http://localhost:11434") -> list:
    """
    Get list of available Ollama models installed locally.
    
    Args:
        base_url: Ollama API base URL (default: localhost)
        
    Returns:
        List of locally installed model names
        
    Note:
        Returns models that are already downloaded and available locally.
        To install a model, use: ollama pull <model_name>
    """
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
        return [model['name'] for model in data.get('models', [])]
    except Exception:
        return []


def clean_text_with_llm(text: str, model: str = "qwen2.5:14b", 
                       system_prompt: Optional[str] = None,
                       user_context: Optional[str] = None,
                       base_url: str = "http://localhost:11434") -> str:
    """
    Clean OCR text using LLM via local Ollama instance.
    
    All processing happens locally - no internet connection required.
    The model must be installed locally first: ollama pull qwen2.5:14b
    
    Args:
        text: OCR text to be cleaned
        model: Model name (default: 'qwen2.5:14b') - must be installed locally
        system_prompt: Optional custom system prompt (uses default if None)
        user_context: Optional contextual information for the prompt
        base_url: Ollama API base URL (default: localhost - local service)
        
    Returns:
        Cleaned text string
        
    Raises:
        RuntimeError: If cleaning fails
    """
    if system_prompt is None:
        system_prompt = get_default_system_prompt()
    
    user_prompt = build_user_prompt(text, user_context)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    cleaned_text = call_ollama(model, messages, base_url)
    
    return cleaned_text


def clean_text_file(input_path: str, output_path: str, model: str = "qwen2.5:14b",
                   system_prompt: Optional[str] = None,
                   user_context: Optional[str] = None,
                   base_url: str = "http://localhost:11434") -> str:
    """
    Clean OCR text from a file and save to output file.
    
    Args:
        input_path: Path to input text file
        output_path: Path to save cleaned text
        model: Model name (default: 'qwen2.5:14b') - must be installed locally
        system_prompt: Optional custom system prompt
        user_context: Optional contextual information
        base_url: Ollama API base URL
        
    Returns:
        Path to output file
    """
    # Read input text
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Clean text
    cleaned_text = clean_text_with_llm(text, model, system_prompt, user_context, base_url)
    
    # Save output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_text)
    
    return output_path

