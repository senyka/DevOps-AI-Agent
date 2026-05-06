# agent/llm.py
import os, logging, asyncio
from typing import Optional, Union
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

VLLM_BASE = os.getenv("OPENAI_API_BASE", "http://vllm:8000/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "empty")
DEFAULT_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
)
async def call_vllm(
    prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    response_format: Optional[dict] = None,
    model: Optional[str] = None,
    lora_adapter: Optional[str] = None
) -> str:
    """Вызов vLLM с поддержкой JSON-mode и LoRA"""
    
    messages = [{"role": "user", "content": prompt}]
    
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    
    # JSON mode (если требуется)
    if response_format and response_format.get("type") == "json_object":
        payload["response_format"] = {"type": "json_object"}
    
    # LoRA adapter (если указан)
    if lora_adapter:
        payload["extra_body"] = {"lora_name": lora_adapter}
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VLLM_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        logger.debug(f"LLM response ({len(content)} chars): {content[:200]}...")
        return content

async def call_vllm_with_tools(
    prompt: str,
    tools: list[dict],
    tool_choice: str = "auto",
    **kwargs
) -> dict:
    """Вызов с поддержкой tool-calling (если модель поддерживает)"""
    messages = [{"role": "user", "content": prompt}]
    
    payload = {
        "model": kwargs.get("model", DEFAULT_MODEL),
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "temperature": kwargs.get("temperature", 0.1),
        "max_tokens": kwargs.get("max_tokens", 1024),
        "stream": False,
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VLLM_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]
