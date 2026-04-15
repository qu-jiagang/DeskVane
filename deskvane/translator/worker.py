from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from .ollama import OllamaClient, OllamaTranslation


@dataclass(slots=True)
class TranslationRequest:
    request_id: int
    source: str
    text: str
    pointer_x: int | None
    pointer_y: int | None
    preferred_model: str
    source_language: str
    target_language: str
    keep_alive: str
    is_pure_ocr: bool = False


@dataclass(slots=True)
class TranslationResult:
    request: TranslationRequest
    response: OllamaTranslation


class TranslationWorker(threading.Thread):
    def __init__(
        self,
        client: OllamaClient,
        on_result: Callable[[TranslationResult], None],
        on_error: Callable[[TranslationRequest, Exception], None],
    ) -> None:
        super().__init__(daemon=True)
        self.client = client
        self.on_result = on_result
        self.on_error = on_error
        self._condition = threading.Condition()
        self._pending_request: TranslationRequest | None = None
        self._stopped = False

    def submit(self, request: TranslationRequest) -> None:
        with self._condition:
            self._pending_request = request
            self._condition.notify()

    def replace_client(self, client: OllamaClient) -> None:
        self.client = client

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._condition.notify_all()

    def run(self) -> None:
        while True:
            with self._condition:
                while not self._stopped and self._pending_request is None:
                    self._condition.wait()
                if self._stopped:
                    return
                request = self._pending_request
                self._pending_request = None
            if request is None:
                continue
            try:
                response = self.client.translate(
                    text=request.text,
                    preferred_model=request.preferred_model,
                    source_language=request.source_language,
                    target_language=request.target_language,
                    keep_alive=request.keep_alive,
                )
            except Exception as exc:
                self.on_error(request, exc)
                continue
            self.on_result(TranslationResult(request=request, response=response))
