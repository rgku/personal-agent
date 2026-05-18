from abc import ABC, abstractmethod


class BaseAgent(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    async def execute(self, action: str, params: dict) -> dict: ...

    @abstractmethod
    def get_tool_definition(self) -> dict: ...
