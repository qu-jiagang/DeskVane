from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from typing import Any


class OllamaError(RuntimeError):
    pass


@dataclass(slots=True)
class OllamaTranslation:
    text: str
    model: str
    elapsed_ms: int


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout_s: int,
        prompt_extra: str = "",
        disable_thinking: bool = True,
        max_output_tokens: int = 1024,
    ) -> None:
        self.host = host.rstrip("/") + "/"
        self.timeout_s = timeout_s
        self.prompt_extra = prompt_extra.strip()
        self.disable_thinking = disable_thinking
        self.max_output_tokens = max_output_tokens
        self._direct_open = build_opener(ProxyHandler({})).open
        self._auto_model: str | None = None

    def list_models(self) -> list[str]:
        payload = self._request_json("/api/tags", None)
        models = payload.get("models", [])
        names = [item.get("name", "").strip() for item in models if item.get("name")]
        return [name for name in names if name]

    def translate(
        self,
        text: str,
        preferred_model: str,
        source_language: str,
        target_language: str,
        keep_alive: str,
    ) -> OllamaTranslation:
        model = self.resolve_model(preferred_model)
        system_prompt = build_system_prompt(
            source_language=source_language,
            target_language=target_language,
            prompt_extra=self.prompt_extra,
        )
        started_at = time.perf_counter()
        
        images = []
        if text.startswith("[img_b64]"):
            images.append(text[9:])
            text = "Please extract the text from this image."
            
        req_payload: dict[str, Any] = {
            "model": model,
            "prompt": text,
            "system": system_prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "think": not self.disable_thinking,
            "options": {
                "temperature": 0.1,
                "num_predict": self._estimate_num_predict(text),
            },
        }
        if images:
            req_payload["images"] = images
            
        payload = self._request_json("/api/generate", req_payload)
        translated = clean_translation(payload.get("response", ""))
        if not translated:
            raise OllamaError("Ollama 返回了空结果。")
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return OllamaTranslation(text=translated, model=model, elapsed_ms=elapsed_ms)

    def resolve_model(self, preferred_model: str) -> str:
        preferred_model = preferred_model.strip()
        if preferred_model:
            self._auto_model = preferred_model
            return preferred_model
        if self._auto_model:
            return self._auto_model
        models = self.list_models()
        if not models:
            raise OllamaError(
                "未检测到本地 Ollama 模型，请先执行 `ollama pull qwen2.5:3b`。"
            )
        self._auto_model = models[0]
        return self._auto_model

    def _request_json(self, path: str, payload: dict | None) -> dict:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(urljoin(self.host, path.lstrip("/")), data=data, headers=headers)
        try:
            open_fn = self._direct_open if self._should_bypass_proxy() else urlopen
            with open_fn(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            message = body.strip() or f"HTTP {exc.code}"
            raise OllamaError(f"Ollama 请求失败：{message}") from exc
        except URLError as exc:
            raise OllamaError(f"无法连接到 Ollama：{exc.reason}") from exc
        except TimeoutError as exc:
            raise OllamaError("Ollama 请求超时。") from exc

    def _estimate_num_predict(self, text: str) -> int:
        estimated = max(64, len(text))
        return min(self.max_output_tokens, estimated)

    def _should_bypass_proxy(self) -> bool:
        hostname = (urlparse(self.host).hostname or "").strip().lower()
        if hostname in {"localhost", "::1"}:
            return True
        try:
            return ip_address(hostname).is_loopback
        except ValueError:
            return False


def build_system_prompt(
    source_language: str,
    target_language: str,
    prompt_extra: str = "",
) -> str:
    if target_language.strip().upper() == "OCR":
        return (
            "You are an Optical Character Recognition (OCR) engine.\n"
            "Extract the text from the image exactly as it appears.\n"
            "Do NOT translate it. Do NOT explain it. Do NOT add formatting unless it represents the layout.\n"
            "Output ONLY the extracted text, nothing else."
        )
        
    source_line = (
        "Automatically detect the source language."
        if source_language.strip().lower() == "auto"
        else f"The source language is {source_language.strip()}."
    )
    extra = f"\nAdditional terminology rules:\n{prompt_extra.strip()}" if prompt_extra.strip() else ""
    return (
        "You are a translation engine.\n"
        f"{source_line}\n"
        f"Translate the text into {target_language.strip()}.\n"
        "Return only the translated text.\n"
        "Preserve formatting, line breaks, markdown, code blocks, punctuation, and proper nouns.\n"
        "Do not explain, do not add notes, and do not wrap the answer in quotes."
        f"{extra}"
    )


def clean_translation(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^(Translation|Translated text|译文|翻译)[：:]\s*", "", cleaned)
    return cleaned.strip()
