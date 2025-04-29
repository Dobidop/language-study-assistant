import json
import os
import requests
from dotenv import load_dotenv  # <-- new import

# --- Load environment variables ---
ENV_PATH = os.path.join(os.path.dirname(__file__), '..', 'api-key.env')
load_dotenv(ENV_PATH)

# --- Load config once ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)

# --- Preload and validate API key ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY is None:
    raise EnvironmentError("Missing OPENAI_API_KEY environment variable. Please create 'api-key.env' and set it.")

def chat(messages, provider=None, model=None, temperature=None):
    """
    Sends a chat request to either OpenAI (v1.x) or a local OpenAI-compatible LLM.
    """
    provider = provider or config.get("default_provider", "openai")
    temperature = temperature if temperature is not None else config.get("temperature", 0.4)

    if provider == "openai":
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=model or config.get("openai_model", "gpt-4"),
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()

    elif provider == "local":
        local_model = model or config.get("local_model", "mistral-7b-instruct")
        local_host = config.get("local_host", "http://localhost")
        local_port = config.get("local_port", 11434)
        endpoint = f"{local_host}:{local_port}/v1/chat/completions"

        payload = {
            "model": local_model,
            "messages": messages,
            "temperature": temperature
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"⚠️ Local model request failed: {e}")
            return ""

    else:
        raise ValueError(f"Unsupported provider: {provider}")
