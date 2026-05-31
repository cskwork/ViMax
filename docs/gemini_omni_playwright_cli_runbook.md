# Gemini Omni Video Generation via Playwright Agent CLI

Repeatable procedure for generating a video with **Gemini Omni** (Veo-backed) by
driving the user's already-logged-in Chrome through the **Playwright Agent CLI**
(`npx @playwright/cli@latest`). No MCP server, no API key, no Claude Code restart.

**Status: VERIFIED end-to-end on 2026-05-31** against
`https://gemini.google.com/u/1/app?hl=ko` (account that exposes the
`동영상 만들기` tool on desktop web). A text prompt produced a valid MP4
(`h264`, 1280x720, 10.0s, ~5.6 MB) downloaded to disk through the authenticated
session — no API key, no MCP server, no Claude Code restart.

---

## 0. Why CLI, not MCP

The Playwright Agent CLI exposes the same browser-control commands as
`@playwright/mcp`, but as plain terminal commands. That means an agent can call
them through Bash directly — no `.mcp.json`, no server registration, no restart.
It attaches to a real Chrome session (extension or CDP), so Google login, cookies,
and the `/u/1` account context are reused as-is.

> Source of truth: https://playwright.dev/agent-cli/cli-command
> Browser-extension config: https://playwright.dev/mcp/configuration/browser-extension

## 1. Prerequisites (one-time)

- Chrome running, signed into the Google account whose Gemini desktop web shows
  `동영상 만들기` in the `+` (업로드 및 도구) menu. The verified account is `/u/1`.
- The Gemini app open in a tab: `https://gemini.google.com/u/1/app?hl=ko`.
- One attach transport available:
  - **Extension** (interactive): the Playwright browser extension installed; user
    clicks Connect in the extension popup. `attach --extension=chrome`.
  - **CDP** (non-interactive, used here): Chrome reachable over the DevTools
    protocol. `attach --cdp=chrome`. This is what worked unattended.

All commands below assume this env prefix (avoids npm cache permission issues):

```bash
export PWCLI="npm_config_cache=/private/tmp/npm-cache npx @playwright/cli@latest"
SESSION=gemini
```

State files (`.playwright-cli/*.yml`, `*.log`) are written to the CWD; keep them
untracked.

## 2. Attach + locate the Gemini tab

```bash
eval $PWCLI attach --cdp=chrome --session=$SESSION      # creates session, lists tabs
eval $PWCLI -s=$SESSION tab-list                        # find the Gemini tab index
eval $PWCLI -s=$SESSION tab-select <index>              # select gemini.google.com/u/1/app
eval $PWCLI -s=$SESSION eval '"location.href"'          # confirm it is the /u/1 app
```

## 3. Enable Gemini Omni video mode

Refs (`e123`) come from the latest `snapshot`; they change every snapshot, so
re-snapshot and re-read the ref before each click.

```bash
eval $PWCLI -s=$SESSION snapshot                        # find "업로드 및 도구" button ref
eval $PWCLI -s=$SESSION click <ref:업로드 및 도구>       # opens the + / tools menu
eval $PWCLI -s=$SESSION snapshot                        # find "동영상 만들기" menuitem ref
eval $PWCLI -s=$SESSION click <ref:동영상 만들기>        # toggles video (Omni) mode
```

First time only, an intro dialog appears: heading `동영상 만들기`, subtitle
`Gemini Omni 사용`, button `사용해 보기`. Click it if present (ignore "ref not
found" — it means the dialog was already dismissed):

```bash
eval $PWCLI -s=$SESSION click <ref:사용해 보기>          # safe to skip if absent
```

After this the composer shows: a `동영상을 설명하세요.` prompt textbox, an
`add_image` button (reference image), and a `가로 모드(16:9)` aspect selector.

## 4. (Optional) attach a reference image

For ViMax per-shot clips conditioned on a first-frame image:

```bash
eval $PWCLI -s=$SESSION click <ref:add_image>
eval $PWCLI -s=$SESSION upload /abs/path/to/first_frame.png
```

If `upload` returns `fileChooser ... Not allowed` under the extension transport,
re-attach via CDP (`attach --cdp=chrome`) and retry — CDP allows file chooser.

## 5. (Optional) set aspect ratio

Default is `가로 모드(16:9)`. To change, click the `crop_16_9` selector and pick.

## 6. Type the prompt and submit

```bash
PROMPT="A serene sunrise over a calm ocean horizon, slow cinematic pan, photorealistic, 8 seconds"
eval $PWCLI -s=$SESSION fill <ref:프롬프트 textbox> "$PROMPT"
eval $PWCLI -s=$SESSION snapshot                        # send button "메시지 보내기" is now enabled
eval $PWCLI -s=$SESSION click <ref:메시지 보내기>
```

The send button (`arrow_upward`) is disabled until the textbox has text. After
submit, a `대답 생성 중지` (stop) button appears = generation in progress.

## 7. Poll until the video is ready

Generation is async (Veo, ~1-3 min). Poll the DOM rather than the snapshot tree:

```bash
for i in $(seq 1 18); do
  eval $PWCLI -s=$SESSION eval '"() => { \
    const gen = document.querySelector(\"[aria-label=\\\"대답 생성 중지\\\"]\") ? 1 : 0; \
    const vids = document.querySelectorAll(\"video\").length; \
    return JSON.stringify({gen, vids}); }"'
  # done when gen==0 and vids>=1
  sleep 20
done
```

## 8. Download the MP4 (verified method)

The result `<video>` src is a signed `https://contribution.usercontent.google.com/download?c=...`
(bard_storage) URL. Two things that do NOT work:

- **In-page `fetch(src)`** → blocked by CORS (cross-origin, no CORS headers).
- **`require('fs')` / `process` / `fetch`-to-disk inside `run-code`** → the
  `run-code` sandbox exposes only the Playwright `page` object and standard JS;
  `require`, `process`, and Node globals are `ReferenceError`.

What DOES work: run a `run-code` script that uses Playwright's
`page.context().request.get(src)` — a Node-side request that carries the browser
context's cookies (so it bypasses CORS and is authenticated) — then return the
bytes as base64 and decode them on disk. Save the JS to a file and run it with
`--filename` (avoids shell-escaping the function).

`download_video_b64.js`:

```js
page => (async () => {
  const src = await page.evaluate(() => {
    const el = document.querySelector('video');
    return el ? (el.currentSrc || el.src) : null;
  });
  if (!src) return 'ERR:no-video';
  const resp = await page.context().request.get(src);
  const buf = await resp.body();
  return buf.toString('base64');     // Buffer instance method works even though Buffer global is sandboxed
})()
```

```bash
# --raw prints only the return value (a JSON-quoted string); redirect to a file
# so the multi-MB base64 never floods the terminal/agent context.
eval $PWCLI -s=$SESSION run-code --filename download_video_b64.js --raw > out.b64.raw
python3 - <<'PY'
raw = open('out.b64.raw','rb').read().strip()
if raw[:1]==b'"' and raw[-1:]==b'"': raw = raw[1:-1]   # strip the JSON quotes --raw adds
import base64; open('gemini_omni_out.mp4','wb').write(base64.b64decode(raw))
PY
file gemini_omni_out.mp4    # -> ISO Media, MP4 Base Media v1
ffprobe -v error -show_entries stream=codec_name,width,height,duration -of default=nw=1 gemini_omni_out.mp4
```

Verified output (2026-05-31): `h264`, `1280x720`, `duration=10.0`, ~5.6 MB.

For ViMax, write the decoded bytes to the shot path the pipeline expects and
return `VideoOutput(fmt="bytes", ext="mp4", data=<decoded bytes>)`.

## 9. Cleanup

```bash
eval $PWCLI -s=$SESSION click <ref:동영상 선택 해제>     # exit video mode (optional)
eval $PWCLI -s=$SESSION detach                          # leave Chrome running
```

---

## Reference: verified menu shape (`/u/1`, 2026-05-31)

`업로드 및 도구` menu contained: 파일 업로드 / Drive에서 파일 추가 / 업로드 더보기 /
이미지 만들기 / **동영상 만들기** / 도구 더보기. The account's sidebar already had
several `동영상 생성` chats, confirming Omni video works on this account/plan.

## Pitfalls

- Refs are per-snapshot. Always snapshot immediately before a click/fill.
- The same Chrome can host multiple CLI sessions (`tistory`, `gemini`); scope each
  with `-s=<name>`.
- `attach --extension` without a value can error `no target specified`; use
  `--extension=chrome`. Extension attach waits for the user to click Connect.
- Do not export cookies/profiles as a workaround; attach to the live session.
