# Plan: Replace `VideoGeneratorGeminiOmniCLI` with a Cookie-Auth Gemini Video Generator

**Audience**: a Codex agent that will implement this end-to-end.
**Goal**: make `pipelines/script2video_pipeline.py` actually produce videos by replacing the hanging CLI-driven backend with a Python client that calls the Gemini consumer web backend directly using browser cookies — modeled on `teng-lin/notebooklm-py`.

---

## 1. Problem Statement

`tools/video_generator_gemini_omni_cli.py` shells out to the `gemini` CLI with a natural-language prompt ("Use Gemini app Gemini Omni video generation…"). The CLI tries to satisfy that prompt by driving a browser session against the Gemini web app. In practice each invocation hangs for the full `timeout_seconds=3600` and the pipeline crashes with `subprocess.TimeoutExpired`. The CLI has no native video-generation command (`gemini --help` confirms: only generic agent flags exist).

Result: ViMax never gets past the first transition video in `Idea2VideoPipeline`. Story / script / character portraits / storyboard / shot 0 first_frame are produced (caching works), then everything stops.

We must replace the video backend with one that talks to a real Gemini video API the same way `teng-lin/notebooklm-py` talks to NotebookLM — cookie jar + CSRF token + `batchexecute` RPC.

---

## 2. Evidence Gathered

### 2.1 Confirmed via `claude-in-chrome` against logged-in https://gemini.google.com/app

| Item | Value (truncated) | Source |
|---|---|---|
| Login cookies present | `SID`, `APISID`, `SAPISID`, `__Secure-1PAPISID`, `__Secure-3PAPISID`, `SIDCC` | `document.cookie` |
| CSRF token | `WIZ_global_data['SNlM0e']` → `AOOh0PGh7gyz_akWlgEs...:1` | inline script |
| Session id | `WIZ_global_data['FdrFJe']` → `-6642074934320192117...` | inline script |
| RPC base URL | `https://geminiweb-pa.clients6.google.com` (keys `GK6dn`, `HUGLxb`, `ZT1yof`) | `WIZ_global_data` |
| Build id | `WIZ_global_data['cfb2h']` → `boq_assistant-bard-web-server_...` | `WIZ_global_data` |
| Inline Google API keys | several `AIzaSy...` strings (`VVlN6d`, `d2zJAe`, `i1PRRd`, `nPMdNb`) | `WIZ_global_data` |

`SNlM0e` and `FdrFJe` are the same field names `teng-lin/notebooklm-py` extracts from the NotebookLM homepage — so the consumer Google web app family shares the same auth shape.

### 2.2 Critical UI finding — desktop vs mobile divergence

The Gemini **mobile app** for this account shows a `+` menu containing **동영상 만들기 (아이디어 실현하기)** (the desired Veo-backed video tool).

The Gemini **desktop web** for the same account, in two different connected Chrome instances ("AIDT" and "Browser 2"), shows the following `+` menu **only** — no video option:

```
파일 업로드
Drive에서 파일 추가
업로드 더보기            ▶
이미지 만들기  [신규]
Canvas
도구 더보기              ▶   (→ Deep Research / 음악 만들기 / 가이드 학습 / 개인 인텔리전스)
```

So on this account/plan, the web UI does not surface the video tool. The mobile UI does. Implication: **either** (a) reverse-engineer the mobile app's HTTPS traffic, or (b) find an account/plan/region whose web UI does surface video and capture the requests there.

### 2.3 NotebookLM precedent

`teng-lin/notebooklm-py` confirms the pattern works for a Google consumer surface:

- Auth: cookies (`SID, HSID, SSID, APISID, SAPISID, __Secure-1PSID, __Secure-1PSIDTS`) + per-session `SNlM0e` + `FdrFJe`, optionally imported from a browser cookie store (`--browser-cookies chrome|firefox|safari|brave|arc|edge`) or captured via Playwright login.
- Transport: `httpx.AsyncClient` against `notebooklm.google.com`, no `google-genai` SDK, middleware chain handles `SAPISIDHASH` signing and 401/CSRF refresh.
- Surfaces include `generate_video()` / `generate_cinematic_video()` (Veo-backed inside NotebookLM).

The same library cannot be reused as-is because (i) it targets NotebookLM, not the Gemini app, and (ii) ViMax needs short reference-image-conditioned clips per shot, not a notebook-wide video overview.

---

## 3. Codex Investigation Tasks (do these before coding)

These are the open unknowns. Codex should resolve them and update this doc.

### 3.1 Get a real captured request that creates a video

Pick **one** path:

**Path A — mobile app capture (preferred if user can run mitmproxy)**
1. Install mitmproxy on the dev Mac, trust the CA on the Android device, point the device's Wi-Fi proxy at the Mac.
2. In Gemini Android app: open `+` → 동영상 만들기 → submit any short prompt (and a single reference image).
3. Save the full `batchexecute` (or grpc) request: URL, headers (including `Authorization`, `X-Goog-*`), POST body. Save the polling/response cycle that returns the MP4 URL.

**Path B — web account with video enabled**
1. Identify whether any Google account the user has (Workspace Labs, Gemini Advanced trial, AI Pro/Ultra) surfaces 동영상 만들기 in the desktop `+` menu.
2. With `claude-in-chrome` (or DevTools Network panel), open `+ → 동영상 만들기`, submit, capture the same network artifacts as Path A.

**Path C — Veo via `aistudio.google.com`**
1. Same as B but on `https://aistudio.google.com`. Often AI Studio surfaces Veo before the consumer Gemini app does. Note that AI Studio also uses cookie auth (no API key) when accessed via the web UI — endpoints differ but the cookie shape is the same.

Whichever path, the output of step 3.1 is a saved HAR or `.json` payload checked into `docs/captures/` (gitignored if it contains tokens).

### 3.2 Identify the RPC ID and payload shape

Google `batchexecute` requests look like:
```
POST https://{host}/$rpc/google.internal.assistant.bard.v1.BardService/...
or
POST https://{host}/_/{module}/data/batchexecute?rpcids=XXXXXX&...&at=<SNlM0e>
form body: f.req=[[[<rpcid>,<args-json-string>,null,"<reqid>"]]]
```

Codex must extract:
- exact host (likely `geminiweb-pa.clients6.google.com` based on §2.1, or `bard-pa.googleapis.com`)
- exact path (most likely `/_/BardChatUi/data/batchexecute`)
- the **video-generation rpcid** (a 6-letter token like `MkEWBc`, `SuwYMc`, etc.)
- the JSON-stringified args layout: where prompt text, reference image bytes/IDs, aspect ratio, duration, model name go
- polling RPC ids if generation is async (download URL arrives later)

### 3.3 Reference image handling

Gemini's web image upload normally goes through a separate `uploads.clients6.google.com` POST that returns an opaque upload token used in the subsequent generate call. Codex must capture:
- upload endpoint + headers
- response shape (likely `{"upload_id": "...", "size": ...}`)
- how the generate request references the uploaded token (probably an entry inside `args[0][...]`)

### 3.4 Output retrieval

The MP4 URL is usually a signed `https://lh3.googleusercontent.com/...` or `https://video.bard.google.com/...`. Verify:
- whether the URL is returned synchronously in the generate response or via a poll
- whether the cookies are required to download (likely yes for signed URLs)
- whether the file is already MP4 H.264 or needs a container fix

### 3.5 Rate limits, quotas, model selection

From the captured payload, identify:
- the model id string for the video tool (e.g. `veo-3-image-to-video` / `veo-2-fast` etc.)
- any client-side limits hinted at (max duration, max ref images, aspect ratio whitelist)

---

## 4. Implementation Plan

Produce these files. Keep changes minimal and surgical — do not refactor unrelated code.

### 4.1 New package `tools/gemini_web/`

```
tools/gemini_web/__init__.py
tools/gemini_web/auth.py             # AuthSnapshot, cookie loading, SNlM0e/FdrFJe scraping
tools/gemini_web/sapisid.py          # SAPISIDHASH header builder (sha1 of ts + sapisid + origin)
tools/gemini_web/transport.py        # httpx.AsyncClient wrapper, retries, CSRF refresh middleware
tools/gemini_web/uploads.py          # upload_image() → upload_token
tools/gemini_web/video.py            # generate_video(prompt, ref_image_paths, aspect, duration, model) → mp4 bytes
tools/gemini_web/cli.py              # `python -m tools.gemini_web login` (Playwright login + cookie dump)
```

`auth.py` responsibilities:
- Load cookies from one of: a `storage_state.json` written by the login command, a `--browser-cookies` import (reuse `browser_cookie3` or the same approach as notebooklm-py), or env vars.
- Validate `MINIMUM_REQUIRED_COOKIES = {SID, HSID, SSID, APISID, SAPISID, __Secure-1PSID, __Secure-1PSIDTS}`.
- GET `https://gemini.google.com/app`, parse `WIZ_global_data` from the HTML to extract `SNlM0e` and `FdrFJe`.

`sapisid.py`:
```
def sapisidhash(sapisid: str, origin: str = "https://gemini.google.com") -> str:
    ts = str(int(time.time()))
    sha = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{sha}"
```
Header: `Authorization: SAPISIDHASH ...`. Also send `X-Origin: https://gemini.google.com` and `Origin: https://gemini.google.com`.

`transport.py`:
- Single `httpx.AsyncClient(http2=True, timeout=httpx.Timeout(300.0))`.
- Method `post_batchexecute(rpcid, args)` that builds the form body, signs with SAPISIDHASH, parses Google's `)]}'` prefix + chunked envelope, returns the inner JSON.
- 401/`SNlM0e` mismatch → refresh tokens via `auth.refresh()` and retry once.
- Exponential backoff (3 attempts) on 5xx and `httpx.ReadTimeout`.

`uploads.py`:
- Implements whatever upload endpoint §3.3 reveals. Wrap as `async def upload_image(path: Path) -> str` returning the upload token.

`video.py`:
- `async def generate_video(prompt, reference_image_paths, aspect_ratio, duration_seconds, model=None) -> bytes`.
- Steps: upload each ref image → call the video-generation rpcid with composed args → poll until ready → download MP4 bytes via signed URL (still over the same client so cookies are sent).
- Convert `aspect_ratio` ViMax style ("16:9") to whatever the wire format expects.

### 4.2 New adapter `tools/video_generator_gemini_web.py`

Implements the same interface as the existing `VideoGeneratorGeminiOmniCLI`:

```
class VideoGeneratorGeminiWeb:
    def __init__(self, *, cookie_source: str, model: str | None = None,
                 work_dir: str = ".working_dir/gemini_web_video_gen",
                 timeout_seconds: int = 600,
                 rate_limiter: RateLimiter | None = None): ...

    async def generate_single_video(self, prompt: str,
                                    reference_image_paths: list[str],
                                    resolution: str = "1080p",
                                    aspect_ratio: str = "16:9",
                                    duration: int = 8) -> VideoOutput:
        # acquire rate limit slot
        # call tools.gemini_web.video.generate_video(...)
        # write MP4 under work_dir
        # return VideoOutput(fmt="bytes", ext="mp4", data=<bytes>)
```

Keep `VideoOutput` contract identical to the CLI version so `Script2VideoPipeline` is unchanged.

### 4.3 Config wiring

Edit `configs/idea2video.yaml` and `configs/script2video.yaml`:

```yaml
video_generator:
  class_path: tools.VideoGeneratorGeminiWeb
  init_args:
    cookie_source: storage_state.json   # or "browser:chrome"
    work_dir: .working_dir/gemini_web_video_gen
    timeout_seconds: 600
  max_requests_per_minute: 4
  max_requests_per_day: 100   # tune after quota observation
```

Export the new class in `tools/__init__.py` next to the existing image/video generators.

### 4.4 Login helper

`python -m tools.gemini_web login` should:
1. Launch Playwright Chromium with a persistent user data dir under `.working_dir/gemini_web_auth/`.
2. Navigate to `https://accounts.google.com/`, wait up to 5 minutes for the user to finish login.
3. Visit `https://gemini.google.com/app` once to make sure the per-app cookies (`SIDCC` etc.) are set.
4. Dump `storage_state.json` next to the user data dir.
5. Print the file path and a one-line "ready" message.

Document in `readme.md` (English + Korean): run `python -m tools.gemini_web login` once before running `main_idea2video.py`.

### 4.5 Tests

Add `tests/test_gemini_web_video.py`:
- A unit test that mocks the `httpx.AsyncClient` and asserts the SAPISIDHASH header is built correctly for a fixed timestamp + dummy sapisid.
- A unit test that asserts `batchexecute` body parsing rejects bodies without the `)]}'` prefix.
- An **opt-in** integration test (marked `@pytest.mark.live`) that, when `GEMINI_WEB_LIVE=1`, generates an 8-second video from a single reference image and verifies the returned MP4 starts with `ftyp` and is ≥ 50 KB.

---

## 5. Risk Register

| Risk | Mitigation |
|---|---|
| Web UI never exposes the video tool for this account → no captured requests to model from | Path A (mobile capture via mitmproxy) is the fallback; document the mitmproxy bootstrap in `docs/captures/README.md`. |
| `__Secure-1PSIDTS` rotates and breaks the session mid-run | Implement `AuthRefreshMiddleware` that re-scrapes `SNlM0e` from `gemini.google.com/app` on 400-CSRF or 401, retries once. |
| Google changes the RPC id / payload shape | Pin a clear error message ("Gemini web RPC id mismatch — re-capture per §3.1") so a future user knows what broke. |
| Account gets flagged for automation | Throttle: `max_requests_per_minute: 4` default, honor any `Retry-After` header, never parallelize uploads + generates from the same account beyond 2 concurrent. |
| Reference image upload not understood | Build incrementally — first ship `generate_video` without reference images, verify the basic flow, then add upload step. |
| MP4 download requires browser-style range requests | Use `httpx` streaming download, write to disk in 1 MB chunks, verify final size matches `Content-Length`. |

---

## 6. Definition of Done

- `uv run python main_idea2video.py` on the existing Yi Sun-sin run resumes from cached artifacts and produces `.working_dir/idea2video/scene_0/shots/0/transition_video_*.mp4` within 10 minutes.
- It then produces `.working_dir/idea2video/scene_0/final_video.mp4` and ultimately `.working_dir/idea2video/final_video.mp4`.
- Removing the `transition_video_*.mp4` file and re-running causes only that file to be regenerated (the existing `os.path.exists` cache gates still hold).
- `pytest tests/test_gemini_web_video.py -q` is green (unit tests). The live test is skipped by default.
- A short note added to `readme.md` explaining `python -m tools.gemini_web login` and how to switch back to the old CLI backend if needed.

---

## 7. Out of Scope (do not do)

- Touching the script/storyboard/image-generation parts of the pipeline.
- Adding a fallback that synthesizes a fake MP4 from images (the user explicitly rejected this).
- Migrating to the official `google-genai` SDK / Veo public API (would require an API key, which the user does not want).
- Cleaning up unrelated Pyright errors in `script2video_pipeline.py`.

---

## 8. Handoff to Codex

You (Codex) are doing this work. The owner of the repo will only review checkpoints; do not block on them mid-task.

**Operating notes**

- Logged-in browsers exist: account "공유" is signed into Gemini desktop and mobile. Mobile shows 동영상 만들기; desktop on this account does not. The user has access to a second Google account that *might* show it on desktop — confirm by visiting `https://gemini.google.com/u/1/app?hl=ko` and inspecting the `+` menu before assuming the desktop path is dead.
- You may use Playwright (preferred), `browser_cookie3`, or `mitmproxy` (for the mobile-capture fallback). Install whatever you need under the project's `uv` env; do not pollute the system Python.
- Do not commit `storage_state.json`, captured HARs, or any file containing `SID`/`SAPISID` cookies. Add a `.gitignore` entry for `docs/captures/` and `.working_dir/gemini_web_auth/`.

**Execution checkpoints — pause and report progress at each**

1. After §3.1 capture is complete: write `docs/captures/gemini_video_request.md` with redacted request/response, then continue.
2. After `tools/gemini_web/transport.py` returns a parsed `batchexecute` response on a trivial test prompt: run that one test and continue.
3. After `tools/gemini_web/video.py` returns a real MP4 for one shot: drop it under `.working_dir/` and continue.
4. After the new adapter is wired into `configs/idea2video.yaml` and `main_idea2video.py` resumes from the existing Yi Sun-sin cache: stop and report.

**Verification commands you must run before declaring done**

```
uv run pytest tests/test_gemini_web_video.py -q
uv run python main_idea2video.py    # should reach final_video.mp4 without TimeoutExpired
file .working_dir/idea2video/final_video.mp4   # must say "ISO Media, MP4 ..."
```

**If you get blocked**

- Capture step fails on desktop and mobile → write a `BLOCKED.md` note explaining what was attempted (which accounts, which URLs, exact failure mode) and stop. Do not silently fall back to mocks or the public Veo API.
- RPC payload shape changes mid-implementation → re-run §3.1, do not guess.
