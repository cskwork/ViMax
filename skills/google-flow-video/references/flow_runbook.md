# Google Flow via Playwright Agent CLI

Manual procedure for debugging `scripts/google_flow_cli.py` against a live,
logged-in Chrome session.

## Preconditions

- Chrome is running and signed into the Google account with Flow access.
- Open the target Flow project, for example:
  `https://labs.google/fx/ko/tools/flow/project/01bad1c6-8d7a-4567-9deb-47ff1b6cd3c1`
- `node` and `npx` are available.

Google's current Flow help says standard video creation starts from an existing
project, uses the prompt box, switches the model to Video, optionally adds
ingredients or frames, chooses video preferences, and clicks Generate.

## Attach

```bash
PWCLI="npm_config_cache=/private/tmp/npm-cache npx @playwright/cli@latest"
SESSION=flow
$PWCLI attach --cdp=chrome --session=$SESSION
$PWCLI -s=$SESSION tab-list
$PWCLI -s=$SESSION tab-select <flow-tab-index>
$PWCLI -s=$SESSION eval '"location.href"'
```

Use `attach --extension=chrome` only when CDP is unavailable; extension attach
requires the user to click Connect.

## Run the reusable CLI

```bash
python3 skills/google-flow-video/scripts/google_flow_cli.py \
  --prompt "A slow cinematic pan across a rainy neon street, 8 seconds" \
  --out .working_dir/flow_playwright/test.mp4 \
  --app-url "https://labs.google/fx/ko/tools/flow/project/01bad1c6-8d7a-4567-9deb-47ff1b6cd3c1" \
  --session flow \
  --fresh
```

For an image-conditioned ViMax shot:

```bash
python3 skills/google-flow-video/scripts/google_flow_cli.py \
  --prompt "$SHOT_PROMPT" \
  --image /abs/path/to/first_frame.png \
  --image /abs/path/to/last_frame.png \
  --out .working_dir/flow_playwright/shot.mp4 \
  --app-url "$FLOW_PROJECT_URL" \
  --session flow
```

## Failure points

- `attach failed`: Chrome is not reachable over CDP. Start Chrome with remote
  debugging or use the Playwright extension attach path.
- `prompt-box-not-found`: the Flow page did not load into a project/editor, or
  the UI changed. Run `snapshot` and update `scripts/js/flow_compose.tmpl.js`.
- `generate-button-not-found`: the prompt box filled, but the Generate control
  label changed or a modal is blocking the composer.
- `download error: ERR:no-video`: generation has not produced a downloadable
  `<video>` yet, or the latest result is rendered outside a video element.
- `download error: ERR:http-401`: the media redirect is not fetchable through
  `page.context().request`; the CLI should fall back to the edit-page Download
  button.

Do not export cookies as a workaround. The intended auth boundary is the live
Chrome session plus Playwright's authenticated page context.
