"""Image generator backed by the local Codex CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from PIL import Image

from interfaces.image_output import ImageOutput
from utils.rate_limiter import RateLimiter


class ImageGeneratorCodexCLI:
    """Generate a PNG by delegating the creative/image step to Codex CLI.

    Codex CLI runs under the user's installed, logged-in account. The adapter
    asks Codex to write a concrete PNG file, then loads that file into the same
    ``ImageOutput`` contract used by the existing API-backed generators.
    """

    def __init__(
        self,
        command: str = "codex",
        model: Optional[str] = None,
        work_dir: str = ".working_dir/codex_image_gen",
        timeout_seconds: int = 1200,
        extra_args: Optional[List[str]] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.command = command
        self.model = model
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds
        self.extra_args = extra_args or []
        self.rate_limiter = rate_limiter

    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = "16:9",
        **kwargs,
    ) -> ImageOutput:
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        reference_image_paths = reference_image_paths or []
        work_dir = Path(self.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_path = work_dir / f"codex_image_{uuid4().hex}.png"
        reply_path = work_dir / f"codex_image_{uuid4().hex}.txt"

        completed = subprocess.run(
            self._command(output_path, reply_path, prompt, reference_image_paths, aspect_ratio),
            cwd=str(work_dir),
            env={**os.environ, "VIMAX_IMAGE_OUTPUT_PATH": str(output_path)},
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Codex CLI image generation failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(
                "Codex CLI completed without writing the requested image: "
                f"{output_path}\nstdout: {completed.stdout.strip()}\nstderr: {completed.stderr.strip()}"
            )

        with Image.open(output_path) as image:
            image.load()
            loaded = image.copy()
        return ImageOutput(fmt="pil", ext="png", data=loaded)

    def _command(
        self,
        output_path: Path,
        reply_path: Path,
        prompt: str,
        reference_image_paths: List[str],
        aspect_ratio: Optional[str],
    ) -> List[str]:
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
        command.append(_build_image_prompt(output_path, prompt, reference_image_paths, aspect_ratio))
        return command


def _build_image_prompt(
    output_path: Path,
    prompt: str,
    reference_image_paths: List[str],
    aspect_ratio: Optional[str],
) -> str:
    references = "\n".join(f"- {path}" for path in reference_image_paths) or "- none"
    return (
        "Create one finished PNG image for ViMax.\n"
        f"Output path: {output_path}\n"
        f"Aspect ratio: {aspect_ratio or 'unspecified'}\n"
        f"Prompt: {prompt}\n"
        f"Reference image paths:\n{references}\n\n"
        "Requirements:\n"
        "- Write a valid raster PNG exactly at the output path.\n"
        "- Use the installed Codex environment; do not require API keys.\n"
        "- Do not ask follow-up questions.\n"
        "- Keep the final response brief after the file is written.\n"
    )
