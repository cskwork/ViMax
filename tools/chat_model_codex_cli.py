"""Vision-capable LangChain chat model backed by the local Codex CLI.

ViMax's reference-image selection is multimodal: the model must actually see
candidate images. The Claude Code CLI adapter is text-only (it cannot ingest
inline base64), so this Codex-backed adapter handles the vision step instead.

Inline ``image_url`` content (base64 data URIs produced by ``image_path_to_b64``)
is materialized to PNG files under ``work_dir`` and referenced by path; Codex
reads those files with its own file tools (``--sandbox workspace-write``) and
returns its final message via ``--output-last-message``.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain.chat_models.base import BaseChatModel
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ChatModelCodexCLI(BaseChatModel):
    """Use the installed Codex CLI as a vision-capable chat model.

    Goes through the user's logged-in Codex environment (no API key). Images are
    written to ``work_dir`` and referenced by absolute path so Codex can view them.
    """

    command: str = "codex"
    model: Optional[str] = None
    timeout_seconds: int = 1200
    work_dir: str = ".working_dir/codex_vision"
    extra_args: List[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "codex-cli"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"command": self.command, "model": self.model, "timeout_seconds": self.timeout_seconds}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        work_dir = Path(self.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        prompt, image_paths = self._render_messages(messages, work_dir)
        reply_path = work_dir / f"codex_reply_{uuid4().hex}.txt"

        completed = subprocess.run(
            self._command(reply_path, prompt),
            env={**os.environ},
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Codex CLI chat failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )

        content = reply_path.read_text(encoding="utf-8").strip() if reply_path.exists() else completed.stdout.strip()
        content = _apply_stop(content, stop)
        self._cleanup(image_paths + [reply_path])
        generation = ChatGeneration(message=AIMessage(content=content))
        return ChatResult(generations=[generation], llm_output={"command": self.command})

    def _command(self, reply_path: Path, prompt: str) -> list[str]:
        # Images are materialized to files, so the prompt text stays small;
        # passing it as the positional arg (like the Codex image generator) is safe.
        command = [
            self.command,
            "--ask-for-approval",
            "never",
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--output-last-message",
            str(reply_path),
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.extend(self.extra_args)
        command.append(prompt)
        return command

    def _render_messages(self, messages: list[BaseMessage], work_dir: Path) -> Tuple[str, List[Path]]:
        parts: List[str] = []
        image_paths: List[Path] = []
        for message in messages:
            role = _role_name(message)
            text = self._content_to_text(message.content, work_dir, image_paths)
            parts.append(f"{role}:\n{text}")
        if image_paths:
            parts.append(
                "The images referenced above are local PNG files. Open and view "
                "each one before answering. Reply with ONLY the requested output "
                "(no preamble, no file writes)."
            )
        return "\n\n".join(parts), image_paths

    def _content_to_text(self, content: Any, work_dir: Path, image_paths: List[Path]) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
                elif isinstance(item, dict) and item.get("type") == "image_url":
                    image_url = item.get("image_url", {})
                    url = image_url.get("url", image_url) if isinstance(image_url, dict) else image_url
                    path = self._materialize_image(url, work_dir)
                    if path is not None:
                        image_paths.append(path)
                        chunks.append(f"[image file to view: {path}]")
                    else:
                        chunks.append(f"[image_url]\n{url}")
                else:
                    chunks.append(str(item))
            return "\n".join(chunks)
        return str(content)

    def _materialize_image(self, url: Any, work_dir: Path) -> Optional[Path]:
        if not isinstance(url, str):
            return None
        if url.startswith("data:") and ";base64," in url:
            header, b64 = url.split(";base64,", 1)
            ext = "png"
            if "/" in header:
                ext = header.split("/", 1)[1] or "png"
            path = (work_dir / f"img_{uuid4().hex}.{ext}").resolve()
            path.write_bytes(base64.b64decode(b64))
            return path
        if os.path.isfile(url):
            return Path(url).resolve()
        return None

    @staticmethod
    def _cleanup(paths: List[Path]) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _role_name(message: BaseMessage) -> str:
    if message.type == "system":
        return "System"
    if message.type == "human":
        return "Human"
    if message.type == "ai":
        return "Assistant"
    return message.type.title()


def _apply_stop(text: str, stop: Optional[list[str]]) -> str:
    if not stop:
        return text
    earliest = len(text)
    for marker in stop:
        index = text.find(marker)
        if index != -1 and index < earliest:
            earliest = index
    return text[:earliest]
