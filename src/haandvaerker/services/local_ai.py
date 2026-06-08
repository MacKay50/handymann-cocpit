"""Local AI abstraction for Ollama / LM Studio.

Disabled by default. Enable by setting LOCAL_AI_ENDPOINT in .env.
Only calls localhost — never external internet (sandbox constraint).
"""
from __future__ import annotations
import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Generator, Optional

from ..config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 30


def is_enabled() -> bool:
    return bool(getattr(settings, "local_ai_endpoint", None))


def _endpoint() -> str:
    ep: str = settings.local_ai_endpoint  # type: ignore[attr-defined]
    return ep.rstrip("/")


def _model() -> str:
    return getattr(settings, "local_ai_model", "mistral")


def _fallback_model() -> Optional[str]:
    v: str = getattr(settings, "local_ai_fallback_model", "")
    return v.strip() or None


def chat_completion(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = 1024,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """Send a chat completion request. Returns None on any error (fail loud via log).

    Tries the primary model first; on failure falls back to LOCAL_AI_FALLBACK_MODEL
    if one is configured.
    """
    if not is_enabled():
        logger.debug("Local AI disabled — skipping completion")
        return None
    ep = _endpoint()

    primary = _model()
    result = _do_chat(ep, prompt, system, max_tokens, timeout, primary)
    if result is not None:
        return result

    fallback = _fallback_model()
    if fallback and fallback != primary:
        logger.info("Primary model '%s' failed — trying fallback '%s'", primary, fallback)
        result = _do_chat(ep, prompt, system, max_tokens, timeout, fallback)
        if result is not None:
            return result
        logger.warning("Fallback model '%s' also failed", fallback)

    return None


def _do_chat(
    ep: str, prompt: str, system: Optional[str], max_tokens: int,
    timeout: Optional[int], model: str,
) -> Optional[str]:
    if "1234" in ep:
        return _lm_studio(ep, prompt, system, max_tokens, timeout, model)
    return _ollama(ep, prompt, system, max_tokens, timeout, model)


def _ollama(
    ep: str, prompt: str, system: Optional[str], max_tokens: int,
    timeout: Optional[int] = None, model: Optional[str] = None,
) -> Optional[str]:
    url = f"{ep}/api/chat"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps(
        {"model": model or _model(), "messages": messages, "stream": False,
         "options": {"num_predict": max_tokens}}
    ).encode()
    return _post(url, payload, timeout)


def _lm_studio(
    ep: str, prompt: str, system: Optional[str], max_tokens: int,
    timeout: Optional[int] = None, model: Optional[str] = None,
) -> Optional[str]:
    url = f"{ep}/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps(
        {"model": model or _model(), "messages": messages, "max_tokens": max_tokens}
    ).encode()
    return _post(url, payload, timeout)


def _post(url: str, payload: bytes, timeout: Optional[int] = None) -> Optional[str]:
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout if timeout is not None else _TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        logger.warning("Local AI request failed: %s", exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("Local AI response parse error: %s", exc)
        return None

    # Ollama: data["message"]["content"], LM Studio: data["choices"][0]["message"]["content"]
    try:
        if "message" in data:
            return str(data["message"]["content"])
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Unexpected Local AI response shape: %s — %s", exc, data)
        return None


def stream_chat_completion(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = 1024,
    timeout: Optional[int] = None,
) -> Generator[str, None, None]:
    """Yield text tokens from a streaming chat completion.

    Tries primary model first; if it yields nothing, tries fallback.
    Yields nothing on any error — never raises.
    """
    if not is_enabled():
        return
    ep = _endpoint()
    primary = _model()

    had_tokens = False
    for token in _stream_do_chat(ep, prompt, system, max_tokens, timeout, primary):
        had_tokens = True
        yield token

    if not had_tokens:
        fallback = _fallback_model()
        if fallback and fallback != primary:
            logger.info("Streaming: primary '%s' yielded nothing — trying fallback '%s'", primary, fallback)
            yield from _stream_do_chat(ep, prompt, system, max_tokens, timeout, fallback)


def _stream_do_chat(
    ep: str, prompt: str, system: Optional[str], max_tokens: int,
    timeout: Optional[int], model: str,
) -> Generator[str, None, None]:
    if "1234" in ep:
        yield from _stream_lm_studio(ep, prompt, system, max_tokens, timeout, model)
    else:
        yield from _stream_ollama(ep, prompt, system, max_tokens, timeout, model)


def _stream_ollama(
    ep: str, prompt: str, system: Optional[str], max_tokens: int,
    timeout: Optional[int], model: str,
) -> Generator[str, None, None]:
    url = f"{ep}/api/chat"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps(
        {"model": model, "messages": messages, "stream": True,
         "options": {"num_predict": max_tokens}}
    ).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout if timeout is not None else _TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    break
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        logger.warning("Ollama streaming failed: %s", exc)


def _stream_lm_studio(
    ep: str, prompt: str, system: Optional[str], max_tokens: int,
    timeout: Optional[int], model: str,
) -> Generator[str, None, None]:
    url = f"{ep}/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps(
        {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True}
    ).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout if timeout is not None else _TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    content = data["choices"][0]["delta"].get("content", "")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if content:
                    yield content
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        logger.warning("LM Studio streaming failed: %s", exc)


def generate_embeddings(text: str) -> Optional[list[float]]:
    """Return embedding vector for *text*, or None if unavailable."""
    if not is_enabled():
        return None
    ep = _endpoint()
    if "1234" in ep:
        return _lm_studio_embed(ep, text)
    return _ollama_embed(ep, text)


def _ollama_embed(ep: str, text: str) -> Optional[list[float]]:
    url = f"{ep}/api/embeddings"
    payload = json.dumps({"model": _model(), "prompt": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return list(data["embedding"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ollama embedding failed: %s", exc)
        return None


def _lm_studio_embed(ep: str, text: str) -> Optional[list[float]]:
    url = f"{ep}/v1/embeddings"
    payload = json.dumps({"model": _model(), "input": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return list(data["data"][0]["embedding"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("LM Studio embedding failed: %s", exc)
        return None
