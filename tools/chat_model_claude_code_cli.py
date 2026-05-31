"""LangChain chat model adapter backed by the local Claude Code CLI."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

from langchain.chat_models.base import BaseChatModel
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ChatModelClaudeCodeCLI(BaseChatModel):
    """Use the installed Claude Code CLI as ViMax's chat model.

    This adapter intentionally goes through the user's local Claude Code login
    instead of requiring an Anthropic API key. It presents LangChain messages as
    a single transcript and returns Claude Code's final printed response.
    """

    command: str = "claude"
    model: Optional[str] = "sonnet"
    timeout_seconds: int = 600
    cwd: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    extra_args: List[str] = Field(default_factory=list)
    disable_tools: bool = True

    @property
    def _llm_type(self) -> str:
        return "claude-code-cli"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "disable_tools": self.disable_tools,
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = _format_messages(messages)
        # Pass the prompt over stdin, not argv: large prompts (e.g. reference-image
        # selection embedding image data URIs) overflow ARG_MAX and raise
        # OSError(7, 'Argument list too long').
        completed = subprocess.run(
            self._command(),
            input=prompt,
            cwd=self.cwd,
            env={**os.environ, **self.env},
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Claude Code CLI failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )

        content = _apply_stop(completed.stdout.strip(), stop)
        generation = ChatGeneration(message=AIMessage(content=content))
        return ChatResult(generations=[generation], llm_output={"command": self.command})

    def _command(self) -> list[str]:
        # Print mode reads the prompt from stdin (see _generate); no prompt argv.
        command = [
            self.command,
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
        ]
        if self.model:
            command.extend(["--model", self.model])
        if self.disable_tools:
            command.extend(["--tools", ""])
        command.extend(self.extra_args)
        return command


def _format_messages(messages: list[BaseMessage]) -> str:
    parts: list[str] = []
    for message in messages:
        role = _role_name(message)
        parts.append(f"{role}:\n{_content_to_text(message.content)}")
    return "\n\n".join(parts)


def _role_name(message: BaseMessage) -> str:
    if message.type == "system":
        return "System"
    if message.type == "human":
        return "Human"
    if message.type == "ai":
        return "Assistant"
    return message.type.title()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
            elif isinstance(item, dict) and item.get("type") == "image_url":
                image_url = item.get("image_url", {})
                url = image_url.get("url", image_url) if isinstance(image_url, dict) else image_url
                chunks.append(f"[image_url]\n{url}")
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return str(content)


def _apply_stop(text: str, stop: Optional[list[str]]) -> str:
    if not stop:
        return text
    earliest = len(text)
    for marker in stop:
        index = text.find(marker)
        if index != -1 and index < earliest:
            earliest = index
    return text[:earliest]
