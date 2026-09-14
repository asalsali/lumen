from __future__ import annotations

from typing import List, Optional

from asgiref.sync import async_to_sync, sync_to_async
from pydantic import BaseModel, Field

from agents import Runner

from ..retry import run_with_retry

from main.models import Project

from .agents.chat_agent import chat_agent, ChatAssistantReply


class ChatTurn(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    project_id: int
    turns: List[ChatTurn] = Field(description="Conversation turns so far; newest last")


class ChatResponse(BaseModel):
    project_id: int
    reply: ChatAssistantReply
    last_response_id: Optional[str] = None


class ProjectChatServiceManager:
    """Orchestrates chat with the project research assistant agent.

    Usage:
        result = ProjectChatServiceManager().run_for_project_sync(project_id, turns)
    """

    def __init__(self) -> None:
        self.runner = Runner()

    async def process(self, project_id: int, turns: List[ChatTurn]) -> ChatResponse:
        # Ensure project exists; raises if missing
        await sync_to_async(Project.objects.get)(pk=project_id)

        # Build properly structured input items (TResponseInputItem)
        input_items: list[dict] = []
        input_items.append({"role": "user", "content": f"[project_id:{project_id}]"})
        for t in turns:
            role = "assistant" if t.role == "assistant" else "user"
            input_items.append({"role": role, "content": t.content})

        result = await run_with_retry(
            self.runner,
            chat_agent,
            input=input_items,
            max_turns=50,
        )

        reply: ChatAssistantReply = result.final_output  # type: ignore
        return ChatResponse(
            project_id=project_id,
            reply=reply,
            last_response_id=getattr(result, "last_response_id", None),
        )

    def run_for_project_sync(self, project_id: int, turns: List[ChatTurn]) -> ChatResponse:
        async def go():
            return await self.process(project_id, turns)

        return async_to_sync(go)()



