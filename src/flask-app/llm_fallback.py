import time

from typing import List, Any

from council.llm import LLMBase, LLMMessage, LLMResult, LLMException


class LLMFallback(LLMBase):
    _llm: LLMBase
    _fallback: LLMBase

    def __init__(self, llm: LLMBase, fallback: LLMBase, retry_before_fallback: int = 2):
        super().__init__()
        self._llm = llm
        self._fallback = fallback
        self._retry_before_fallback = retry_before_fallback

    def _post_chat_request(self, messages: List[LLMMessage], **kwargs: Any) -> LLMResult:
        try:
            return self._llm_call_with_retry(messages, **kwargs)
        except LLMException as e:
            try:
                return self._fallback.post_chat_request(messages, **kwargs)
            except Exception:
                raise e

    def _llm_call_with_retry(self, messages: List[LLMMessage], **kwargs: Any) -> LLMResult:
        retry_count = 0
        while retry_count < self._retry_before_fallback:
            try:
                return self._llm.post_chat_request(messages, **kwargs)
            except LLMException as e:
                if "503" in str(e):
                    time.sleep(1.25 ** retry_count)
                    retry_count += 1
                else:
                    raise e
            except Exception:
                raise
