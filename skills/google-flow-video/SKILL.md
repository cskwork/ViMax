---
name: google-flow-video
description: Generate a video in Google Flow by driving a logged-in Chrome session through the Playwright Agent CLI. Use when a user wants Flow, labs.google/fx, flow.google, or a Google Flow project URL to produce an MP4 from a prompt, optionally with reference images, without an API key.
---

<objective>
Drive the user's existing authenticated Chrome session to a Google Flow project,
submit a text-to-video prompt, poll until a video appears, and download the MP4
through Playwright's authenticated browser context.
</objective>

<when_to_use>
- The user asks to use Google Flow or a `labs.google/fx/.../flow/project/...` URL for video generation.
- A ViMax config uses `VideoGeneratorGeminiOmniPlaywright` with `surface: flow`.
- The task needs browser-session generation without exporting cookies or adding API keys.
</when_to_use>

<quick_start>
```bash
python3 scripts/google_flow_cli.py \
  --prompt "A slow cinematic pan across a rainy neon street, 8 seconds" \
  --out ./flow_out.mp4 \
  --app-url "https://labs.google/fx/ko/tools/flow/project/01bad1c6-8d7a-4567-9deb-47ff1b6cd3c1" \
  --fresh
```

Add one or more `--image /abs/path/frame.png` arguments when the shot should
use reference frames. Use `--no-attach` only after a previous call already
attached the same Playwright Agent CLI session.
</quick_start>

<process>
1. Confirm Chrome is open and signed into the Google account that can use Flow.
2. Attach with CDP by default: `npx @playwright/cli@latest attach --cdp=chrome --session=flow`.
3. Select an existing Flow tab or open the `--app-url` project URL.
4. Use the script's role/text based Playwright actions to set Video mode, add an optional image, fill the prompt, and click Generate.
5. Poll `scripts/js/flow_status.js` until generation is no longer active and a new `<video>` source appears.
6. Download the selected video source with `page.context().request.get(videoSrc)`, then fall back to Flow's edit-page Download button if the media redirect returns 401.
</process>

<important_constraints>
- Do not export cookies or browser profiles. Attach to the live user-owned Chrome session.
- Flow UI labels and locale can change. If the script fails at compose time, inspect the latest Playwright snapshot and update only `scripts/js/flow_compose.tmpl.js`.
- Google Flow credits are consumed by each submission; avoid unattended loops.
- The official Flow help describes standard creation as: open a Flow project, enter a prompt, switch the model to Video, select preferences, then click Generate.
</important_constraints>

<files>
- `scripts/google_flow_cli.py`: command-line orchestrator used by ViMax.
- `scripts/js/flow_compose.tmpl.js`: Flow compose/submit automation.
- `scripts/js/flow_status.js`: generation-state and video metadata poll.
- `scripts/js/download_b64.js`: authenticated video download.
- `scripts/js/flow_download_button.tmpl.js`: edit-page Download button fallback.
- `references/flow_runbook.md`: manual debugging procedure.
</files>
