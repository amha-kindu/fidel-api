from typing import Any, AsyncIterator, Iterable, Optional

import httpx
import structlog
from app.core.config import settings
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


logger = structlog.get_logger(__name__)


class InferenceClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url or settings.inference_base_url
        self.timeout = timeout or settings.inference_timeout_s
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream_chat(self, messages: Iterable[dict[str, Any]]) -> AsyncIterator[str]:
        """Stream chat completion from inference backend."""
        payload_messages = list(messages)
        logger.info("inference.stream.start", base_url=self.base_url)
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(httpx.HTTPError),
            wait=wait_exponential(multiplier=0.5, max=2),
            stop=stop_after_attempt(3),
            reraise=True,
        ):
            with attempt:
                async with self._client.stream(
                    "POST",
                    "/v1/chat/completions",
                    json={
                        "model": settings.inference_model,
                        "messages": payload_messages,
                        "temperature": settings.inference_temperature,
                        "top_p": settings.inference_top_p,
                        "top_k": settings.inference_top_k,
                        "max_tokens": settings.inference_max_tokens,
                        "stream": True,
                        "stop": [
                            "[DONE]"
                        ]
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        yield line
        logger.info("inference.stream.done", base_url=self.base_url)
