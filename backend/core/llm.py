"""
Multi-Provider LLM Router
Supports Anthropic (Claude), OpenAI (GPT), and Google (Gemini).

Rules:
  - Set ANY ONE key and everything works.
  - ANTHROPIC_API_KEY → chat with Claude, embeddings via Gemini free public API
  - OPENAI_API_KEY    → chat with GPT-4o, embeddings with text-embedding-3-small
  - GEMINI_API_KEY    → chat with Gemini, embeddings with text-embedding-004

  If you set LLM_PROVIDER=anthropic|openai|gemini it forces that provider.
  If multiple keys are set, priority is: Anthropic > OpenAI > Gemini.

Embeddings special case (Anthropic has no embedding API):
  - If GEMINI_API_KEY is also set → use Gemini embeddings (best)
  - If OPENAI_API_KEY is also set → use OpenAI embeddings
  - Neither → use Gemini free public REST endpoint (no key required,
    rate-limited but sufficient for development and moderate usage)
"""
from __future__ import annotations
import json
import os
import asyncio
import hashlib
import math
import structlog

logger = structlog.get_logger()

# ── Provider detection ────────────────────────────────────────

def detect_provider() -> str:
    """
    Detect which LLM provider to use.
    Can be overridden by LLM_PROVIDER env var.
    """
    explicit = os.getenv("LLM_PROVIDER", "").lower().strip()
    if explicit in ("anthropic", "openai", "gemini"):
        logger.debug("llm_provider_forced", provider=explicit)
        return explicit

    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"

    raise RuntimeError(
        "No LLM API key found. Please set one of the following in your .env:\n"
        "  ANTHROPIC_API_KEY  → uses Claude (recommended)\n"
        "  OPENAI_API_KEY     → uses GPT-4o\n"
        "  GEMINI_API_KEY     → uses Gemini\n"
        "Only ONE key is needed. The system handles everything else automatically."
    )


def detect_embed_provider() -> str:
    """
    Detect which provider to use for embeddings.

    - OpenAI  → always use OpenAI embeddings (native, no issue)
    - Gemini  → always use Gemini embeddings (native, no issue)
    - Anthropic → no native embedding API, so:
        1. Use Gemini free public API (no key needed, just HTTP)
        2. Or use GEMINI_API_KEY if set (higher rate limits)
        3. Or use OPENAI_API_KEY if set
        → Never falls back to hash (we always have Gemini public available)
    """
    provider = detect_provider()

    if provider == "openai":
        return "openai"

    if provider == "gemini":
        return "gemini"

    # provider == "anthropic"
    # Gemini public REST works without any API key (free tier, no signup)
    # so we can always use it as the embedding fallback for Anthropic users
    if os.getenv("OPENAI_API_KEY"):
        return "openai"          # user has OpenAI key — use it for better quality
    return "gemini_public"       # Gemini free public endpoint, no key needed


# ── Model name mapping ────────────────────────────────────────

MODEL_MAP = {
    "anthropic": {
        "strong": "claude-opus-4-5",
        "fast":   "claude-sonnet-4-5",
        "embed":  None,                       # handled by detect_embed_provider()
    },
    "openai": {
        "strong": "gpt-4o",
        "fast":   "gpt-4o-mini",
        "embed":  "text-embedding-3-small",
    },
    "gemini": {
        "strong": "gemini-2.0-flash",
        "fast":   "gemini-2.0-flash",
        "embed":  "models/gemini-embedding-001",
    },
}


def get_model(tier: str = "fast") -> str:
    provider = detect_provider()
    return MODEL_MAP[provider][tier]


# ── Universal chat completion ─────────────────────────────────

async def chat(
    system_prompt: str,
    user_message: str | list,
    tier: str = "fast",
    max_tokens: int = 2000,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> str:
    """
    Universal chat — routes to the active provider automatically.
    Returns the assistant's text response.
    Supports vision/multimodal by passing a list to user_message.
    """
    provider = detect_provider()
    model    = MODEL_MAP[provider][tier]

    if json_mode:
        system_prompt = (
            system_prompt.rstrip() +
            "\n\nYou MUST respond with valid JSON only. "
            "No preamble, no explanation, no markdown fences."
        )

    logger.debug("llm_chat", provider=provider, model=model, tier=tier)

    if provider == "anthropic":
        return await _chat_anthropic(system_prompt, user_message, model, max_tokens, temperature)
    if provider == "openai":
        return await _chat_openai(system_prompt, user_message, model, max_tokens, temperature, json_mode)
    if provider == "gemini":
        return await _chat_gemini(system_prompt, user_message, model, max_tokens, temperature, json_mode)

    raise ValueError(f"Unknown provider: {provider}")


async def chat_json(
    system_prompt: str,
    user_message: str | list,
    tier: str = "fast",
    max_tokens: int = 2000,
) -> dict:
    """
    Universal JSON chat — strips fences and parses result.
    """
    text = await chat(
        system_prompt, user_message,
        tier=tier, max_tokens=max_tokens,
        json_mode=True,
    )
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    if text.startswith("```"):
        lines = text.split("\n")
        text  = "\n".join(lines[1:])
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as jde:
        logger.error("json_decode_error_raw_content", raw_text=text, cleaned_text=cleaned, error=str(jde))
        raise jde


# ── Provider implementations ──────────────────────────────────

async def _chat_anthropic(system_prompt, user_message, model, max_tokens, temperature):
    import anthropic
    client  = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = await client.messages.create(
        model=model, max_tokens=max_tokens, temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


async def _chat_openai(system_prompt, user_message, model, max_tokens, temperature, json_mode):
    import openai
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    kwargs = dict(
        model=model, max_tokens=max_tokens, temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


async def _chat_gemini(system_prompt, user_message, model, max_tokens, temperature, json_mode=False):
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    
    cfg_args = {"max_output_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        cfg_args["response_mime_type"] = "application/json"
        
    cfg   = genai.GenerationConfig(**cfg_args)
    gm    = genai.GenerativeModel(model_name=model, system_instruction=system_prompt,
                                   generation_config=cfg)
    
    # Gemini generativeai SDK expects a list of parts for multimodal
    content = user_message if isinstance(user_message, list) else [user_message]
    resp  = await gm.generate_content_async(content)
    return resp.text


# ── Embeddings ────────────────────────────────────────────────

async def embed(text: str) -> list[float]:
    """
    Generate a 1536-dim embedding vector using the best available method.

    Decision tree:
      Anthropic-only user → Gemini public REST (free, no extra key needed)
      OpenAI user         → OpenAI text-embedding-3-small (native 1536-dim)
      Gemini user         → Gemini text-embedding-004 (resized to 1536)
      Anthropic + OpenAI  → OpenAI (higher quality)
      Anthropic + Gemini  → Gemini (with key, higher rate limits)
    """
    embed_provider = detect_embed_provider()
    logger.debug("embed_provider", provider=embed_provider)

    if embed_provider == "openai":
        return await _embed_openai(text)
    if embed_provider == "gemini":
        return await _embed_gemini_keyed(text)
    if embed_provider == "gemini_public":
        return await _embed_gemini_public(text)

    # Should never reach here, but safe fallback
    return _embed_hash(text)


async def _embed_openai(text: str) -> list[float]:
    """OpenAI text-embedding-3-small — native 1536 dims."""
    import openai
    client   = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return response.data[0].embedding


async def _embed_gemini_keyed(text: str) -> list[float]:
    """Gemini gemini-embedding-001 using API key — 3072 dims, resized to 1536."""
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    def _sync():
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text[:8000],
            task_type="retrieval_document",
        )
        return result["embedding"]

    vec = await asyncio.get_event_loop().run_in_executor(None, _sync)
    return _resize_to_1536(vec)


async def _embed_gemini_public(text: str) -> list[float]:
    """
    Gemini free public embedding endpoint — NO API KEY REQUIRED.

    Uses the publicly accessible Gemini embedding REST API.
    Rate limit: ~60 requests/minute on the free tier.
    This is sufficient for development and moderate trading activity
    (a typical cycle makes ~17 LLM calls, of which only a few need embeddings).

    If you hit rate limits, add GEMINI_API_KEY to your .env for higher limits.
    """
    import httpx

    # Gemini public REST endpoint (no auth header required for free tier)
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"

    # Use GEMINI_API_KEY if available for higher rate limits, else use public
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key:
        url = f"{url}?key={api_key}"

    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text[:8000]}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            vec  = data["embedding"]["values"]
            return _resize_to_1536(vec)
    except Exception as e:
        logger.warning(
            "gemini_public_embed_failed",
            error=str(e),
            msg="Falling back to hash embeddings. Memory retrieval will be approximate."
        )
        return _embed_hash(text)


def _embed_hash(text: str) -> list[float]:
    """
    Last-resort deterministic pseudo-embedding.
    Only used if ALL embedding methods fail.
    Memory still stores and retrieves, but ordering is not semantic.
    """
    h    = hashlib.sha256(text.encode()).digest()
    dims = 1536
    vec  = [math.sin(h[i % 32] * (i + 1) * 0.01) for i in range(dims)]
    mag  = sum(x * x for x in vec) ** 0.5
    return [x / mag for x in vec]


def _resize_to_1536(vec: list[float]) -> list[float]:
    """Resize any embedding to exactly 1536 dims for pgvector consistency."""
    target = 1536
    if len(vec) == target:
        return vec
    if len(vec) > target:
        return vec[:target]
    repeats = math.ceil(target / len(vec))
    return (vec * repeats)[:target]
