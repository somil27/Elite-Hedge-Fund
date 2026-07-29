"""
BaseAgent — every agent inherits this.
Uses the universal LLM router — works with Anthropic, OpenAI, or Gemini.
Agents never import any provider SDK directly.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import asyncpg
from core.llm import chat, chat_json, detect_provider, get_model
from core.memory import write_memory, retrieve_memories
import structlog

logger = structlog.get_logger()


class BaseAgent(ABC):
    def __init__(self, agent_id: str, tier: str = "fast"):
        """
        tier: "fast" (research/execution agents) | "strong" (CIO, Risk Manager)
        The actual model used depends on the active LLM provider.
        """
        self.agent_id = agent_id
        self.tier     = tier

    @property
    def provider(self) -> str:
        return detect_provider()

    @property
    def model(self) -> str:
        return get_model(self.tier)

    async def think(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> str:
        """Call the active LLM provider and return text response."""
        logger.info("agent_thinking", agent=self.agent_id,
                    provider=self.provider, model=self.model)
        return await chat(
            system_prompt, user_message,
            tier=self.tier,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def think_json(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
    ) -> dict:
        """Call LLM and parse JSON response."""
        logger.info("agent_thinking_json", agent=self.agent_id,
                    provider=self.provider, model=self.model)
        return await chat_json(
            system_prompt, user_message,
            tier=self.tier,
            max_tokens=max_tokens,
        )

    async def remember(
        self,
        conn: asyncpg.Connection,
        memory_type: str,
        content: str,
        metadata: dict = None,
        cycle_id: str = None,
        importance: float = 0.5,
        expires_in_hours: int = None,
    ) -> None:
        """Store a memory."""
        await write_memory(
            conn, self.agent_id, memory_type, content,
            metadata=metadata, cycle_id=cycle_id,
            importance_score=importance,
            expires_in_hours=expires_in_hours,
        )
        logger.debug("memory_stored", agent=self.agent_id, type=memory_type)

    async def recall(
        self,
        conn: asyncpg.Connection,
        query: str,
        memory_types: list[str] = None,
        limit: int = 6,
    ) -> list[dict]:
        """Retrieve relevant past memories."""
        return await retrieve_memories(
            conn, self.agent_id, query,
            memory_types=memory_types, limit=limit,
        )

    @abstractmethod
    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        """Execute agent logic. Returns partial state update."""
        ...

    def _format_memories(self, memories: list[dict]) -> str:
        if not memories:
            return "No relevant past memories."
        lines = []
        for m in memories:
            ts = m.get("created_at", "")
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%Y-%m-%d")
            mem_type = m.get("memory_type", "observation")
            lines.append(f"[{ts}] ({mem_type}) {m['content'][:300]}")
        return "\n".join(lines)
