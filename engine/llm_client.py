import json
import os
import requests

# Load config once at module level
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)


def chat(messages, provider=None, model=None, temperature=None):
    """
    Sends a chat request to either OpenAI (v1.x) or a local OpenAI-compatible LLM.
    """
    provider = provider or config.get("default_provider", "openai")
    temperature = temperature if temperature is not None else config.get("temperature", 0.4)

    if provider == "openai":
        import openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", config.get("openai_api_key")))

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
