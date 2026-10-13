import os
from dotenv import load_dotenv
load_dotenv()
from langchain_nvidia_ai_endpoints import ChatNVIDIA

api_key = os.getenv("NVIDIA_API_KEY")

test_list = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "microsoft/phi-3.5-mini-instruct",
    "qwen/qwen2.5-7b-instruct",
    "mistralai/mistral-7b-instruct-v0.2",
    "meta/llama-4-scout-17b-16e-instruct"
]

for m in test_list:
    try:
        llm = ChatNVIDIA(model=m, api_key=api_key, timeout=15)
        res = llm.invoke("Hello, answer in one short sentence.")
        print(f"✅ SUCCESS for '{m}': {res.content.strip()[:60]}")
    except Exception as e:
        print(f"❌ FAILED for '{m}': {e}")
