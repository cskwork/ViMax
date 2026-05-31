import asyncio
import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image

from tools.chat_model_claude_code_cli import ChatModelClaudeCodeCLI
from tools.chat_model_factory import build_chat_model
from tools.image_generator_codex_cli import ImageGeneratorCodexCLI
from tools.video_generator_gemini_omni_cli import VideoGeneratorGeminiOmniCLI


class LocalCliAdapterTests(unittest.TestCase):
    def _executable(self, directory: Path, name: str, body: str) -> str:
        path = directory / name
        path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def test_claude_code_chat_model_invokes_cli_with_formatted_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture_path = tmp_path / "prompt.txt"
            command = self._executable(
                tmp_path,
                "claude-fake",
                """
                import os
                import sys
                prompt = sys.argv[sys.argv.index('-p') + 1]
                with open(os.environ['VIMAX_CAPTURE_PATH'], 'w', encoding='utf-8') as f:
                    f.write(prompt)
                print('assistant reply')
                """,
            )

            model = ChatModelClaudeCodeCLI(
                command=command,
                model="sonnet",
                env={"VIMAX_CAPTURE_PATH": str(capture_path)},
            )
            result = model.invoke([
                SystemMessage(content="Return compact JSON."),
                HumanMessage(content="Describe a lantern."),
            ])

            self.assertEqual(result.content, "assistant reply")
            prompt = capture_path.read_text(encoding="utf-8")
            self.assertIn("System:\nReturn compact JSON.", prompt)
            self.assertIn("Human:\nDescribe a lantern.", prompt)

    def test_chat_model_factory_builds_cli_chat_model_from_class_path(self):
        section = {
            "class_path": "tools.ChatModelClaudeCodeCLI",
            "init_args": {"command": "claude", "model": "sonnet"},
        }

        model = build_chat_model(section)

        self.assertIsInstance(model, ChatModelClaudeCodeCLI)
        self.assertEqual(model.command, "claude")
        self.assertEqual(model.model, "sonnet")

    def test_codex_image_generator_invokes_cli_and_loads_written_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            command = self._executable(
                tmp_path,
                "codex-fake",
                """
                import base64
                import os
                output_path = os.environ['VIMAX_IMAGE_OUTPUT_PATH']
                png = 'iVBORw0KGgoAAAANSUhEUgAAACAAAAASCAIAAAC1qksFAAAAIUlEQVR4nGPkUbJgoCVgoqnpoxaMWjBqwagFoxaMWgAFADh3AIpqkpP5AAAAAElFTkSuQmCC'
                with open(output_path, 'wb') as f:
                    f.write(base64.b64decode(png))
                print('image written')
                """
            )

            generator = ImageGeneratorCodexCLI(command=command, work_dir=str(tmp_path))
            output = asyncio.run(generator.generate_single_image("A brass lantern", aspect_ratio="16:9"))

            self.assertEqual(output.fmt, "pil")
            self.assertEqual(output.ext, "png")
            self.assertEqual(output.data.size, (32, 18))
            self.assertEqual(output.data.getpixel((0, 0)), (12, 34, 56))

    def test_gemini_omni_video_generator_invokes_cli_and_returns_written_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            command = self._executable(
                tmp_path,
                "gemini-fake",
                """
                import os
                output_path = os.environ['VIMAX_VIDEO_OUTPUT_PATH']
                with open(output_path, 'wb') as f:
                    f.write(b'fake-mp4-bytes')
                print('video written')
                """,
            )

            generator = VideoGeneratorGeminiOmniCLI(
                command=command,
                model="gemini-omni",
                work_dir=str(tmp_path),
            )
            output = asyncio.run(generator.generate_single_video("A slow pan", [], duration=1))

            self.assertEqual(output.fmt, "bytes")
            self.assertEqual(output.ext, "mp4")
            self.assertEqual(output.data, b"fake-mp4-bytes")


if __name__ == "__main__":
    unittest.main()
