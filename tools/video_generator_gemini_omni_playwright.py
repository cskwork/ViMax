"""Video generator backed by Google video tools via the Playwright Agent CLI.

Replaces the hanging `gemini` CLI backend. Drives the user's already-logged-in
Chrome (CDP/extension attach) to make a Veo-backed video with Gemini Omni or
Google Flow, then downloads the MP4 through the authenticated session.

The browser-driving logic lives in reusable skills. This adapter shells out to a
skill CLI and serializes calls, because the pipeline generates shots concurrently
but a single Chrome tab must be driven one request at a time.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from interfaces.video_output import VideoOutput
from utils.rate_limiter import RateLimiter

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_GEMINI_SKILL_DIR = os.environ.get(
    "GEMINI_OMNI_SKILL_DIR",
    os.path.expanduser("~/.claude/skills/gemini-omni-video"),
)
_DEFAULT_FLOW_SKILL_DIR = os.environ.get(
    "GOOGLE_FLOW_SKILL_DIR",
    str(_REPO_ROOT / "skills" / "google-flow-video"),
)
_DEFAULT_APP_URLS = {
    "gemini": "https://gemini.google.com/u/1/app?hl=ko",
    "flow": "https://labs.google/fx/ko/tools/flow",
}
_SCRIPT_NAMES = {
    "gemini": "gemini_omni_cli.py",
    "flow": "google_flow_cli.py",
}


def _normalize_surface(surface: str) -> str:
    value = surface.lower().strip()
    if value not in _SCRIPT_NAMES:
        raise ValueError(f"Unsupported video Playwright surface: {surface}")
    return value


def _default_skill_dir(surface: str) -> str:
    if surface == "flow":
        return _DEFAULT_FLOW_SKILL_DIR
    return _DEFAULT_GEMINI_SKILL_DIR


class VideoGeneratorGeminiOmniPlaywright:
    """Generate an MP4 through a Google web video surface.

    Calls are serialized with an ``asyncio.Lock`` so concurrent shot generation
    does not drive the same browser tab at once.
    """

    def __init__(
        self,
        skill_dir: Optional[str] = None,
        app_url: Optional[str] = None,
        surface: str = "gemini",
        attach: str = "cdp",
        session: Optional[str] = None,
        python_executable: Optional[str] = None,
        work_dir: str = ".working_dir/gemini_omni_playwright",
        timeout_seconds: int = 600,
        poll_interval: int = 15,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.surface = _normalize_surface(surface)
        resolved_skill_dir = skill_dir or _default_skill_dir(self.surface)
        self.cli_path = (
            Path(resolved_skill_dir) / "scripts" / _SCRIPT_NAMES[self.surface]
        )
        if not self.cli_path.exists():
            raise FileNotFoundError(
                f"{self.surface} video skill CLI not found at {self.cli_path}. "
                "Set skill_dir, GEMINI_OMNI_SKILL_DIR, or GOOGLE_FLOW_SKILL_DIR."
        )
        self.app_url = app_url or _DEFAULT_APP_URLS[self.surface]
        self.attach = attach
        self.session = session or self.surface
        self.python_executable = python_executable or "python3"
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval
        self.rate_limiter = rate_limiter
        self._lock = asyncio.Lock()
        self._attached = False

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        duration: int = 8,
    ) -> VideoOutput:
        work_dir = Path(self.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_path = work_dir / f"{self.surface}_{uuid4().hex}.mp4"

        async with self._lock:
            if self.rate_limiter:
                await self.rate_limiter.acquire()

            cmd = self._build_command(
                prompt,
                reference_image_paths,
                output_path,
                aspect_ratio,
                duration,
            )
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout_seconds + 60
                )
            except asyncio.TimeoutError:
                proc.kill()
                self._attached = False
                raise RuntimeError(
                    f"{self.surface} Playwright generation timed out after "
                    f"{self.timeout_seconds + 60}s for prompt: {prompt[:80]}"
                )

            if proc.returncode != 0:
                self._attached = False
                raise RuntimeError(
                    f"{self.surface} Playwright generation failed "
                    f"(exit {proc.returncode}).\n"
                    f"stdout: {stdout.decode(errors='ignore').strip()}\n"
                    f"stderr: {stderr.decode(errors='ignore').strip()}"
                )

            self._attached = True

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(
                f"{self.surface} Playwright completed but wrote no video: {output_path}\n"
                f"stdout: {stdout.decode(errors='ignore').strip()}"
            )

        return VideoOutput(fmt="bytes", ext="mp4", data=output_path.read_bytes())

    def _build_command(
        self,
        prompt: str,
        reference_image_paths: List[str],
        output_path: Path,
        aspect_ratio: str = "16:9",
        duration: int = 8,
    ) -> List[str]:
        cmd = [
            self.python_executable,
            str(self.cli_path),
            "--prompt", prompt,
            "--out", str(output_path),
            "--app-url", self.app_url,
            "--attach", self.attach,
            "--session", self.session,
            "--timeout", str(self.timeout_seconds),
            "--poll-interval", str(self.poll_interval),
            "--fresh",
        ]
        if reference_image_paths and self.surface == "flow":
            for image_path in reference_image_paths:
                cmd.extend(["--image", image_path])
        elif reference_image_paths:
            cmd.extend(["--image", reference_image_paths[0]])
        if self.surface == "flow":
            cmd.extend(["--aspect-ratio", aspect_ratio])
            cmd.extend(["--duration", str(duration)])
        if self._attached:
            cmd.append("--no-attach")
        return cmd
