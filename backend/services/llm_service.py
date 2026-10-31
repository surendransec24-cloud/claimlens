import os
import json
from typing import Type, TypeVar, Optional, Any, List, Union, Tuple
from pydantic import BaseModel
from google import genai
from google.genai import types
from backend.config import settings

T = TypeVar("T", bound=BaseModel)

# Ordered fallback chain: first working model is used
_MODEL_FALLBACK_CHAIN = [
    "models/gemini-flash-lite-latest",
    "models/gemini-flash-latest",
    "models/gemini-2.5-flash-lite",
    "models/gemini-3-flash-preview",
    "models/gemini-pro-latest",
]


class LLMService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
        raw_model = settings.GEMINI_MODEL
        # SDK requires the full "models/<name>" prefix; add it if missing
        self.model_name = raw_model if raw_model.startswith("models/") else f"models/{raw_model}"
        self._client: Optional[genai.Client] = None
        self._resolved_model: Optional[str] = None  # cached after first successful call
        if self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[LLMService] Failed to initialize Gemini client: {e}")
                self._client = None

    @property
    def is_configured(self) -> bool:
        return self._client is not None and bool(self.api_key)

    def _get_model_with_fallback(self, contents, config) -> Tuple[Optional[Any], Optional[str]]:
        """Try self.model_name first, then fallback chain on 503/404."""
        # Build ordered list: preferred model first, then fallbacks
        candidates = [self.model_name] + [m for m in _MODEL_FALLBACK_CHAIN if m != self.model_name]
        # If we already found a working model, put it first
        if self._resolved_model and self._resolved_model != self.model_name:
            candidates = [self._resolved_model] + [m for m in candidates if m != self._resolved_model]

        last_err = None
        for model in candidates:
            try:
                resp = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                # Cache the working model to avoid retrying others every call
                self._resolved_model = model
                return resp, None
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "404" in err_str or "NOT_FOUND" in err_str:
                    last_err = err_str
                    continue  # try next fallback
                return None, err_str  # non-transient error, don't retry
        return None, f"All models unavailable. Last error: {last_err}"

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        images: Optional[List[dict]] = None,  # list of {"data": bytes, "mime_type": str}
        system_instruction: Optional[str] = None
    ) -> Tuple[Optional[T], Optional[str]]:
        """
        Executes a Gemini generation call with structured JSON output enforced against a Pydantic schema.
        Returns: (parsed_pydantic_object, error_message_if_failed)
        """
        if not self.is_configured:
            return None, "GEMINI_API_KEY not configured or client initialization failed"

        contents: List[Any] = []
        if images:
            for img in images:
                part = types.Part.from_bytes(data=img["data"], mime_type=img["mime_type"])
                contents.append(part)
        contents.append(prompt)

        config_kwargs: dict = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
            "temperature": 0.1,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        try:
            config = types.GenerateContentConfig(**config_kwargs)
            response, err = self._get_model_with_fallback(contents, config)
            if err:
                return None, err

            raw_text = response.text
            if not raw_text:
                return None, "Empty response received from Gemini"

            # Validate through Pydantic
            parsed = response_schema.model_validate_json(raw_text)
            return parsed, None
        except Exception as e:
            return None, str(e)


llm_service = LLMService()
