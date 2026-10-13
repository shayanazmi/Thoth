import os
from dotenv import load_dotenv
load_dotenv()
from langchain_nvidia_ai_endpoints import ChatNVIDIA

api_key = os.getenv("NVIDIA_API_KEY")
llm = ChatNVIDIA(api_key=api_key)
try:
    available = llm.available_models
    print(f"Total available models: {len(available)}")
    for m in available:
        if any(keyword in m.id.lower() for keyword in ["nemo", "llama", "mistral", "qwen", "phi", "deepseek"]):
            print(f"  - {m.id}")
except Exception as e:
    print("Error getting models:", e)
