import os
import sys
from dotenv import load_dotenv
load_dotenv()

from langchain_nvidia_ai_endpoints import ChatNVIDIA

api_key = os.getenv("NVIDIA_API_KEY")
print(f"NVIDIA API Key exists: {bool(api_key and len(api_key) > 10)}")

models_to_test = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "mistralai/mistral-7b-instruct-v0.3",
    "meta/llama-3.3-70b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "meta/llama3-70b-instruct",
    "mistralai/mixtral-8x7b-instruct-v0.1"
]

for m in models_to_test:
    try:
        llm = ChatNVIDIA(model=m, api_key=api_key, timeout=10)
        res = llm.invoke("Say 'OK'")
        print(f"  [SUCCESS] Model '{m}' is ACTIVE: {res.content.strip()[:40]}")
    except Exception as e:
        print(f"  [FAILED]  Model '{m}': {e}")
