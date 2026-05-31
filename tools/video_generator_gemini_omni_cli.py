"""Video generator backed by Gemini CLI / Gemini Omni."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from interfaces.video_output import VideoOutput
from utils.rate_limiter import RateLimiter


class VideoGeneratorGeminiOmniCLI:
    """Generate an MP4 by delegating to the local Gemini CLI.

    The adapter is intentionally CLI-first so it can use the user's logged-in
    Gemini account instead of a Google API key. It requests a concrete MP4 at a
    known path and returns the bytes through ViMax's existing ``VideoOutput``.
    """

    def __init__(
        self,
        command: str = "gemini",
        model: Optional[str] = None,
        work_dir: str = ".working_dir/gemini_omni_video_gen",
        timeout_seconds: int = 3600,
        extra_args: Optional[List[str]] = None,
        rate_limiter: Optional[RateLimiter] = None,
        yolo: bool = True,
    ):
        self.command = command
        self.model = model
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds
        self.extra_args = extra_args or []
        self.rate_limiter = rate_limiter
        self.yolo = yolo

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        duration: int = 8,
    ) -> VideoOutput:
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        work_dir = Path(self.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_path = work_dir / f"gemini_omni_video_{uuid4().hex}.mp4"

        completed = subprocess.run(
            self._command(output_path, prompt, reference_image_paths, resolution, aspect_ratio, duration),
            cwd=str(work_dir),
            env={**os.environ, "VIMAX_VIDEO_OUTPUT_PATH": str(output_path)},
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Gemini CLI video generation failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(
                "Gemini CLI completed without writing the requested video: "
                f"{output_path}\nstdout: {completed.stdout.strip()}\nstderr: {completed.stderr.strip()}"
            )

        return VideoOutput(fmt="bytes", ext="mp4", data=output_path.read_bytes())

    def _command(
        self,
        output_path: Path,
        prompt: str,
        reference_image_paths: List[str],
        resolution: str,
        aspect_ratio: str,
        duration: int,
    ) -> List[str]:
        command = [self.command, "--prompt", _build_video_prompt(
            output_path,
            prompt,
            reference_image_paths,
            resolution,
            aspect_ratio,
            duration,
        )]
        if self.model:
            command.extend(["--model", self.model])
        if self.yolo:
            command.append("--yolo")
        command.extend(self.extra_args)
        return command


def _build_video_prompt(
    output_path: Path,
    prompt: str,
    reference_image_paths: List[str],
    resolution: str,
    aspect_ratio: str,
    duration: int,
) -> str:
    references = "\n".join(f"- {path}" for path in reference_image_paths) or "- none"
    return (
        "Use Gemini app Gemini Omni video generation for one ViMax shot.\n"
        f"Output path: {output_path}\n"
        f"Resolution: {resolution}\n"
        f"Aspect ratio: {aspect_ratio}\n"
        f"Duration seconds: {duration}\n"
        f"Prompt: {prompt}\n"
        f"Reference image paths:\n{references}\n\n"
        "Requirements:\n"
        "- Write a valid MP4 exactly at the output path.\n"
        "- Use the installed Gemini CLI and logged-in account; do not require API keys.\n"
        "- Do not ask follow-up questions.\n"
        "- Keep the final response brief after the file is written.\n"
    )
