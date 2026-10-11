from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        ...

    def to_llm_tool(self) -> dict[str, Any]:
        from pydantic import create_model
        sig = self.execute.__annotations__
        fields = {k: (v, ...) for k, v in sig.items() if k != "return"}
        model = create_model(f"{self.name}_params", **fields)
        schema = model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }
