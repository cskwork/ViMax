# Changelog 2026-05-31

## Add Google Flow video surface for Playwright session generation

### Why
The existing Playwright-backed ViMax video option only targeted Gemini Omni.
The requested target is a Google Flow project URL, which uses the same practical
auth boundary: the user's already-logged-in Chrome session and Playwright Agent
CLI remote debugging.

### Decision
Keep `VideoGeneratorGeminiOmniPlaywright` as the existing adapter, but add a
`surface: flow` option. Gemini stays the default for backward compatibility.
Flow uses a repo-local reusable skill at `skills/google-flow-video`, so ViMax
does not need to mutate the separate global Gemini Omni skill.

### What changed
- Added `surface` routing to `tools/video_generator_gemini_omni_playwright.py`.
- Added Flow configs: `configs/idea2video_flow.yaml` and
  `configs/script2video_flow.yaml`.
- Added reusable skill: `skills/google-flow-video`.
- Added unit coverage for Gemini/Flow Playwright command construction and Flow
  config YAML.

### Constraints
- Flow consumes the user's Google Flow credits; no unattended loops.
- The Flow UI is browser-locale and product-version sensitive. If compose
  selectors drift, update only `skills/google-flow-video/scripts/js/flow_compose.tmpl.js`.
- Downloads first try `page.context().request.get(videoSrc)` and fall back to
  Flow's visible Download button when the media redirect endpoint returns 401.

## Harden Flow submission after live run

### Why
The first live Flow run generated a valid MP4, but it bypassed ViMax's normal
frame pipeline and exposed two integration gaps: the submit selector matched the
header "more/create" menu before the composer submit button, and only one image
was passed even when ViMax had both first and last frames.

### Decision
Prefer the prompt-bar `arrow_forward 만들기` button and allow repeated `--image`
arguments for Flow so medium/large shots can pass all generated frame references.
Gemini keeps its single-starting-image behavior.

## Add Flow download button fallback

### Why
During a full ViMax scene run, Flow produced the media card but the direct
`media.getMediaUrlRedirect` request returned `ERR:http-401`. The authenticated
browser UI could still download the MP4 through the edit page.

### Decision
Keep the direct media fetch as the fast path, then navigate to the newest Flow
edit page and save the video through the Download button if the fast path fails.
