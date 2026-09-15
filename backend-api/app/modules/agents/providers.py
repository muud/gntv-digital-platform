"""Provider-neutral model boundary with a deterministic local mock."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class StructuredModelResponse(BaseModel):
    type: str = Field(pattern="^(final|tool_request|approval_request)$")
    message: str = ""
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)


class ModelUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_units: int


class ModelProvider(ABC):
    @abstractmethod
    def generate(
        self,
        *,
        system: str,
        trusted_context: dict[str, Any],
        untrusted_content: Any,
        user_request: Any,
    ) -> str: ...

    @abstractmethod
    def generate_structured(self, **kwargs: Any) -> StructuredModelResponse: ...

    @abstractmethod
    def estimate_usage(self, request: Any, response: Any) -> ModelUsage: ...

    @abstractmethod
    def validate_model(self, model_name: str) -> bool: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class MockModelProvider(ModelProvider):
    """Deterministic provider; it never performs network I/O."""

    def generate(
        self,
        *,
        system: str,
        trusted_context: dict[str, Any],
        untrusted_content: Any,
        user_request: Any,
    ) -> str:
        return self.generate_structured(
            system=system,
            trusted_context=trusted_context,
            untrusted_content=untrusted_content,
            user_request=user_request,
        ).message

    def generate_structured(self, **kwargs: Any) -> StructuredModelResponse:
        trusted_context = kwargs.get("trusted_context") or {}
        if trusted_context.get("last_tool_result") is not None:
            return StructuredModelResponse(
                type="final", message="Tool completed; deterministic run finished"
            )
        request = kwargs.get("user_request") or {}
        candidate = request.get("mock_response") if isinstance(request, dict) else None
        if candidate is not None:
            return StructuredModelResponse.model_validate(candidate)
        text = (
            request.get("request", "Completed by deterministic mock provider")
            if isinstance(request, dict)
            else str(request)
        )
        return StructuredModelResponse(
            type="final", message=f"Mock result: {text}"[:1000]
        )

    def estimate_usage(self, request: Any, response: Any) -> ModelUsage:
        input_tokens = max(1, len(str(request)) // 4)
        output_tokens = max(1, len(str(response)) // 4)
        return ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_units=1,
        )

    def validate_model(self, model_name: str) -> bool:
        return model_name == "deterministic-v1"

    def health_check(self) -> bool:
        return True


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {"mock": MockModelProvider()}

    def resolve(self, provider: str) -> ModelProvider:
        if provider not in self._providers:
            raise ValueError(f"Provider '{provider}' is not configured")
        return self._providers[provider]

    def identifiers(self) -> list[str]:
        return ["mock", "openai", "anthropic", "google", "local"]


provider_registry = ProviderRegistry()
