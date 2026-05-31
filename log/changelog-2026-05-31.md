# Changelog 2026-05-31

## Replace hanging Gemini CLI video backend with Playwright-Agent-CLI Gemini Omni driver

### Why
`VideoGeneratorGeminiOmniCLI` shelled out to the `gemini` CLI with a natural-language
prompt. The CLI has no native video command, so every call hung for the full
`timeout_seconds=3600` and the pipeline crashed with `TimeoutExpired` at the first
shot video. ViMax never reached `final_video.mp4`.

### Decision
Drive the user's already-logged-in Chrome to the real Gemini Omni `동영상 만들기`
tool via the **Playwright Agent CLI** (`npx @playwright/cli@latest`) - plain Bash
commands, no MCP server, no `.mcp.json`, no Claude Code restart, no API key. This
reuses the Google login/account context as-is. Pattern borrowed from the
`seomachine-ai-blog` `tistory-seo-blog-poster` skill.

The browser-driving logic is packaged as a standalone, reusable skill in a separate
private repo (`cskwork/gemini-omni-video-skill`, installed at
`~/.claude/skills/gemini-omni-video`). ViMax shells out to that skill's CLI.

### What changed
- New: `tools/video_generator_gemini_omni_playwright.py` - `VideoGeneratorGeminiOmniPlaywright`.
  Same `generate_single_video(prompt, reference_image_paths, ...)` interface; serializes
  calls with an `asyncio.Lock` (one Chrome tab, concurrent shots) and attaches once.
- `tools/__init__.py` - export the new class.
- `configs/idea2video.yaml` - `video_generator.class_path` -> the new adapter (CDP attach,
  `app_url` /u/1, 600s timeout). Old CLI backend left in the tree for fallback.
- `docs/gemini_omni_playwright_cli_runbook.md` - verified repeatable runbook.

### Verified
- Text-to-video and image-conditioned generation both produce valid MP4
  (`ffprobe`: h264 + aac, 1280x720, 10.0s) downloaded through the authenticated
  session. The image path uses the shot's `first_frame.png` as the Omni starting image.

### Key constraints (learned)
- Gemini Omni output is fixed 16:9 720p ~10s; the adapter ignores resolution/aspect/
  duration kwargs (UI exposes no control), matching the old CLI adapter's behavior.
- Download path: in-page `fetch(src)` is CORS-blocked and `run-code` is sandboxed
  (no `require`/`process`/`fs`). Only `page.context().request.get(src)` (cookie-bearing)
  works -> base64 -> decode on disk.
- Requires Chrome signed into an account whose desktop Gemini surfaces `동영상 만들기`
  (verified `/u/1`). `/u/0` did not in earlier checks.

### Out of scope (unchanged)
- Story/script/portrait/storyboard/frame generation. No fake-MP4 fallback. No public
  Veo API / API key.
