"""Stage 3 support — model backends.

The pipeline is model-agnostic. Three backends:

  OpenAICompatClient  -> any OpenAI-compatible /chat/completions server.
                         This is the production path for a LOCAL model:
                         serve Qwen3-VL (or similar) with vLLM / LM Studio /
                         llama.cpp server and point base_url at it.
  OllamaClient        -> Ollama's native /api/chat (easiest local start).
  MockClient          -> replays a fixture JSON; lets you develop and test
                         stages 4-6 (validation, confidence, review) with no
                         GPU attached.

All clients expose:  chat(prompt, images=[Path,...], system=None) -> str
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path


def _b64(p: str | Path) -> str:
    return base64.b64encode(Path(p).read_bytes()).decode()


def extract_json(text: str) -> dict:
    """Tolerant JSON recovery with multi-stage repair.

    Real model outputs are messy — especially from Gemini's thinking models
    which can inject ``<think>`` blocks, truncate mid-token, emit trailing
    commas, or wrap in markdown fences.  This function tries increasingly
    aggressive repairs so a single stray comma doesn't kill a whole grounding
    attempt.

    Repair stages (applied in order, each re-attempts json.loads):
      1. strip markdown fences + <think> blocks + BOM/control chars
      2. fix trailing commas before } or ]
      3. fix single-quoted keys/values → double-quoted
      4. fix unescaped newlines inside string values
      5. attempt regex extraction of the outermost { … } object
    """
    # --- stage 1: strip wrappers and control chars ---
    t = text
    # remove <think>...</think> blocks (Gemini thinking models)
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.DOTALL)
    # remove markdown code fences
    t = re.sub(r"```(?:json)?", "", t).strip("` \n\r\t")
    # strip BOM + C0 control chars except \n \r \t
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufeff]", "", t)

    # --- try raw parse first (happy path) ---
    obj = _try_parse(t)
    if obj is not None:
        return obj

    # --- isolate outermost { … } ---
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    t = t[start : end + 1]
    obj = _try_parse(t)
    if obj is not None:
        return obj

    # --- stage 2: trailing commas ---
    t2 = re.sub(r",\s*([}\]])", r"\1", t)
    obj = _try_parse(t2)
    if obj is not None:
        return obj

    # --- stage 3: single-quoted keys/values → double-quoted ---
    t3 = re.sub(r"(?<=[\{,\s])\s*'([^']+?)'\s*:", r' "\1":', t2)
    t3 = re.sub(r":\s*'([^']*?)'", r': "\1"', t3)
    obj = _try_parse(t3)
    if obj is not None:
        return obj

    # --- stage 4: unescaped newlines inside strings ---
    t4 = _escape_newlines_in_strings(t3)
    obj = _try_parse(t4)
    if obj is not None:
        return obj

    # --- nothing worked ---
    raise ValueError(f"JSON repair failed on model output: {t[:300]!r}")


def _try_parse(text: str) -> dict | None:
    """Return parsed dict or None on failure."""
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _escape_newlines_in_strings(text: str) -> str:
    """Escape literal newlines that sit inside JSON string values."""
    out, in_str, esc = [], False, False
    for ch in text:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            esc = True
            out.append(ch)
            continue
        if ch == '"':
            in_str = not in_str
        if in_str and ch == "\n":
            out.append("\\n")
            continue
        out.append(ch)
    return "".join(out)


def _post(url: str, payload: dict, headers: dict | None = None, timeout: int = 300) -> dict:
    """POST with exponential backoff on 429/503 (rate limit / service unavailable)."""
    import time
    import urllib.error

    max_retries = 4
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries:
                wait = 2 ** (attempt + 1)   # 2, 4, 8, 16 seconds
                time.sleep(wait)
                continue
            raise


class OpenAICompatClient:
    """vLLM / LM Studio / llama.cpp server / any OpenAI-compatible endpoint.

    Example (local Qwen3-VL under vLLM):
        vllm serve Qwen/Qwen3-VL-8B-Instruct --port 8000
        client = OpenAICompatClient("http://localhost:8000/v1", "Qwen/Qwen3-VL-8B-Instruct")
    """

    def __init__(self, base_url: str, model: str, api_key: str = "local"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def chat(self, prompt: str, images: list = (), system: str | None = None,
             max_tokens: int | None = None, thinking_budget: int | None = None) -> str:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(p)}"}}
            for p in images
        ]
        content.append({"type": "text", "text": prompt})
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": content}
        ]
        out = _post(
            f"{self.base_url}/chat/completions",
            {"model": self.model, "messages": messages, "temperature": 0,
             "max_tokens": max_tokens or 2000},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return out["choices"][0]["message"]["content"]


class OllamaClient:
    """Ollama native API. Example: OllamaClient(model='qwen3-vl') — use whatever
    vision-capable tag you have pulled locally (`ollama list`)."""

    def __init__(self, model: str, host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def chat(self, prompt: str, images: list = (), system: str | None = None,
             max_tokens: int | None = None, thinking_budget: int | None = None) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt, "images": [_b64(p) for p in images]}
        ]
        options: dict = {"temperature": 0}
        if max_tokens:
            options["num_predict"] = max_tokens
        out = _post(
            f"{self.host}/api/chat",
            {"model": self.model, "messages": messages, "stream": False,
             "options": options},
        )
        return out["message"]["content"]


class GeminiClient:
    """Google Gemini via the Generative Language REST API.

    Key resolution order: explicit api_key arg -> GEMINI_API_KEY -> GOOGLE_API_KEY.
    Get a key at https://aistudio.google.com/apikey

    Default model 'gemini-2.5-flash' is fast, cheap and very strong on OCR;
    pass any other id you have access to (e.g. a Gemini 3 flash variant)
    via --model. responseMimeType=application/json forces raw JSON out,
    which suits this pipeline exactly.
    """

    API = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        import os

        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini backend needs an API key: pass --api-key or set GEMINI_API_KEY"
            )

    def chat(self, prompt: str, images: list = (), system: str | None = None,
             max_tokens: int | None = None, thinking_budget: int | None = None) -> str:
        parts = [
            {"inline_data": {"mime_type": "image/png", "data": _b64(p)}} for p in images
        ]
        parts.append({"text": prompt})
        gen: dict = {
            "temperature": 0,
            "maxOutputTokens": max_tokens or 4096,
            "responseMimeType": "application/json",
        }
        if thinking_budget is not None:
            # cap "thinking" so it cannot starve the answer of output tokens
            # (2.5-class models count thoughts against maxOutputTokens)
            gen["thinkingConfig"] = {"thinkingBudget": thinking_budget}
        payload: dict = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen,
        }
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        out = _post(
            f"{self.API}/{self.model}:generateContent",
            payload,
            headers={"x-goog-api-key": self.api_key},
        )
        cands = out.get("candidates") or []
        if not cands:
            raise RuntimeError(f"Gemini returned no candidates: {json.dumps(out)[:300]}")
        return "".join(p.get("text", "") for p in cands[0]["content"]["parts"])


class MockClient:
    """Replays a fixture: {"page": {...}, "fields": {...}, "blocks": {...}}.
    extract.py detects this class and reads the fixture directly instead of
    prompting - it exists purely so the downstream stages can be exercised
    end-to-end (validation, confidence, review UI) without inference."""

    def __init__(self, fixture_path: str | Path):
        self.fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))

    def chat(self, prompt: str, images: list = (), system: str | None = None) -> str:
        raise RuntimeError("MockClient is consumed directly by extract.py")


DEFAULT_MODELS = {
    "ollama": "qwen3-vl",        # `ollama pull qwen3-vl` (8B). glm-ocr / llava also work.
    "openai": "Qwen/Qwen3-VL-8B-Instruct",
    "gemini": "gemini-2.5-flash",
}


def make_client(backend: str, **kw):
    model = kw.get("model") or DEFAULT_MODELS.get(backend)
    if backend == "openai":
        return OpenAICompatClient(kw["base_url"], model, kw.get("api_key") or "local")
    if backend == "ollama":
        return OllamaClient(model, kw.get("base_url") or "http://localhost:11434")
    if backend == "gemini":
        return GeminiClient(model, kw.get("api_key"))
    if backend == "mock":
        return MockClient(kw["fixture"])
    raise ValueError(f"unknown backend {backend!r}")
