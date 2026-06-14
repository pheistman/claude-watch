#!/usr/bin/env python3
"""Transcribe a video via Groq, OpenAI, AssemblyAI, or Deepgram.

Strategy: extract audio, upload to whichever provider is available and best-suited.
Returns segments in the same shape as transcribe.parse_vtt so the rest of the
pipeline (filter_range, format_transcript) doesn't care where the transcript came from.

Auto-selection (no --provider flag) is based on extracted audio file size:
  audio ≤ 24 MB  → Groq → AssemblyAI → Deepgram → OpenAI
  audio > 24 MB  → AssemblyAI → Deepgram → Groq → OpenAI
  (24 MB is the threshold because Groq/OpenAI Whisper reject uploads over 25 MB with HTTP 413)

Pure stdlib — no pip dependencies.
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import uuid
from pathlib import Path
from urllib.request import Request, urlopen


# ── Groq / OpenAI (Whisper protocol) ─────────────────────────────────────────
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL    = "whisper-large-v3"

OPENAI_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_MODEL    = "whisper-1"

# ── AssemblyAI ────────────────────────────────────────────────────────────────
ASSEMBLYAI_UPLOAD_ENDPOINT     = "https://api.assemblyai.com/v2/upload"
ASSEMBLYAI_TRANSCRIPT_ENDPOINT = "https://api.assemblyai.com/v2/transcript"
ASSEMBLYAI_POLL_INTERVAL_S     = 5
ASSEMBLYAI_LOG_EVERY           = 6   # print progress every N poll ticks

# ── Deepgram ──────────────────────────────────────────────────────────────────
DEEPGRAM_ENDPOINT = "https://api.deepgram.com/v1/listen"
DEEPGRAM_PARAMS   = "model=nova-2&punctuate=true&utterances=true"

# ── Provider → env-var name ───────────────────────────────────────────────────
_KEY_NAMES: dict[str, str] = {
    "groq":       "GROQ_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "assemblyai": "ASSEMBLYAI_API_KEY",
    "deepgram":   "DEEPGRAM_API_KEY",
}

# Above this file size, Groq/OpenAI Whisper return HTTP 413 — prefer async providers
_WHISPER_MAX_BYTES = 24 * 1024 * 1024   # 24 MB (Whisper limit is 25 MB)


# ─────────────────────────────────────────────────────────────────────────────
# Key loading
# ─────────────────────────────────────────────────────────────────────────────

def _dotenv_paths() -> list[Path]:
    return [
        Path.home() / ".config" / "watch" / ".env",
        Path.cwd() / ".env",
    ]


def _load_single_key(env_var: str) -> str | None:
    """Read one key from environment or dotenv files."""
    value = os.environ.get(env_var)
    if value and value.strip():
        return value.strip()
    for path in _dotenv_paths():
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() != env_var:
                    continue
                v = v.strip()
                if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
                    v = v[1:-1]
                return v or None
        except OSError:
            continue
    return None


def load_api_key(
    preferred: str | None = None,
    file_size_bytes: int | None = None,
) -> tuple[str, str] | tuple[None, None]:
    """Return (provider_name, api_key).

    When preferred is set, only that provider is tried.
    When preferred is None, auto-selects based on audio file size:
      ≤ 24 MB  → groq → assemblyai → deepgram → openai
      > 24 MB  → assemblyai → deepgram → groq → openai
    """
    if preferred is not None:
        if preferred not in _KEY_NAMES:
            raise SystemExit(
                f"Unknown provider '{preferred}'. "
                f"Choose from: {', '.join(_KEY_NAMES)}"
            )
        key = _load_single_key(_KEY_NAMES[preferred])
        return (preferred, key) if key else (None, None)

    if file_size_bytes is not None and file_size_bytes > _WHISPER_MAX_BYTES:
        order = ["assemblyai", "deepgram", "groq", "openai"]
    else:
        order = ["groq", "assemblyai", "deepgram", "openai"]

    for provider in order:
        key = _load_single_key(_KEY_NAMES[provider])
        if key:
            return provider, key

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Audio extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_audio(video_path: str, out_path: Path) -> Path:
    """Extract mono 16kHz 64kbps mp3 — ~480 kB/min, fits any provider limit."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is not installed. Install with: brew install ffmpeg")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(Path(video_path).resolve()),
        "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        str(out_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg audio extraction failed: {result.stderr.strip()}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise SystemExit("ffmpeg produced no audio — video may have no audio track")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Groq / OpenAI (Whisper protocol) — multipart upload
# ─────────────────────────────────────────────────────────────────────────────

def _build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----WatchBoundary{uuid.uuid4().hex}"
    eol = b"\r\n"
    buf = io.BytesIO()

    for name, value in fields.items():
        buf.write(f"--{boundary}".encode()); buf.write(eol)
        buf.write(f'Content-Disposition: form-data; name="{name}"'.encode()); buf.write(eol)
        buf.write(eol)
        buf.write(str(value).encode()); buf.write(eol)

    mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    buf.write(f"--{boundary}".encode()); buf.write(eol)
    buf.write(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"'.encode()
    )
    buf.write(eol)
    buf.write(f"Content-Type: {mimetype}".encode()); buf.write(eol)
    buf.write(eol)
    buf.write(file_path.read_bytes())
    buf.write(eol)
    buf.write(f"--{boundary}--".encode()); buf.write(eol)

    return buf.getvalue(), boundary


MAX_ATTEMPTS    = 4
MAX_429_RETRIES = 2
RETRY_BASE_DELAY = 2.0


def _post_whisper(endpoint: str, api_key: str, model: str, audio_path: Path) -> dict:
    fields = {"model": model, "response_format": "verbose_json", "temperature": "0"}
    body, boundary = _build_multipart(fields, audio_path)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "watch-skill/1.0 (+claude-code; python-urllib)",
    }
    ctx = ssl.create_default_context()
    rate_limit_hits = 0
    last_exc: Exception | None = None
    last_detail = ""

    for attempt in range(MAX_ATTEMPTS):
        request = Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=300, context=ctx) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            last_exc, last_detail = exc, detail
            if 400 <= exc.code < 500 and exc.code != 429:
                raise SystemExit(f"Whisper request failed: {exc}{detail}")
            if exc.code == 429:
                rate_limit_hits += 1
                if rate_limit_hits >= MAX_429_RETRIES:
                    raise SystemExit(f"Whisper rate limit: {exc}{detail}")
                delay = _retry_after(exc) or RETRY_BASE_DELAY * (2 ** attempt) + 1
            else:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
            if attempt < MAX_ATTEMPTS - 1:
                print(
                    f"[watch] whisper HTTP {exc.code} — retrying in {delay:.1f}s "
                    f"(attempt {attempt + 2}/{MAX_ATTEMPTS})",
                    file=sys.stderr,
                )
                time.sleep(delay)
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
            last_exc, last_detail = exc, ""
            if attempt < MAX_ATTEMPTS - 1:
                delay = RETRY_BASE_DELAY * (attempt + 1)
                print(
                    f"[watch] whisper network error ({type(exc).__name__}: {exc}) — "
                    f"retrying in {delay:.1f}s (attempt {attempt + 2}/{MAX_ATTEMPTS})",
                    file=sys.stderr,
                )
                time.sleep(delay)
            continue
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Whisper returned non-JSON response: {exc}: {payload[:200]}")

    raise SystemExit(
        f"Whisper request failed after {MAX_ATTEMPTS} attempts: {last_exc}{last_detail}"
    )


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read()
    except Exception:
        return ""
    if not body:
        return ""
    try:
        return f" — {body.decode('utf-8', errors='replace')[:400]}"
    except Exception:
        return ""


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    header = exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _segments_from_whisper_response(data: dict) -> list[dict]:
    """Convert Whisper verbose_json into {start, end, text} segments."""
    out: list[dict] = []
    for seg in data.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "start": round(float(seg.get("start") or 0.0), 2),
            "end":   round(float(seg.get("end")   or 0.0), 2),
            "text":  text,
        })
    if not out:
        full = (data.get("text") or "").strip()
        if full:
            out.append({"start": 0.0, "end": 0.0, "text": full})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# AssemblyAI — async upload → submit → poll
# ─────────────────────────────────────────────────────────────────────────────

def _transcribe_assemblyai(audio_path: Path, api_key: str) -> list[dict]:
    ctx = ssl.create_default_context()
    auth = {"Authorization": api_key}

    # 1. Upload raw audio
    print("[watch] uploading audio to AssemblyAI…", file=sys.stderr)
    data = audio_path.read_bytes()
    req = Request(
        ASSEMBLYAI_UPLOAD_ENDPOINT, data=data,
        headers={**auth, "Content-Type": "application/octet-stream"},
        method="POST",
    )
    with urlopen(req, timeout=300, context=ctx) as resp:
        upload_url = json.loads(resp.read())["upload_url"]

    # 2. Submit transcription job
    payload = json.dumps({"audio_url": upload_url, "language_code": "en"}).encode()
    req = Request(
        ASSEMBLYAI_TRANSCRIPT_ENDPOINT, data=payload,
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=60, context=ctx) as resp:
        job = json.loads(resp.read())
    job_id = job["id"]
    print(f"[watch] AssemblyAI job submitted (id={job_id}), polling…", file=sys.stderr)

    # 3. Poll until complete
    poll_url = f"{ASSEMBLYAI_TRANSCRIPT_ENDPOINT}/{job_id}"
    ticks = 0
    while True:
        time.sleep(ASSEMBLYAI_POLL_INTERVAL_S)
        req = Request(poll_url, headers=auth)
        with urlopen(req, timeout=60, context=ctx) as resp:
            result = json.loads(resp.read())
        status = result["status"]
        if status == "completed":
            break
        if status == "error":
            raise SystemExit(f"AssemblyAI error: {result.get('error', 'unknown')}")
        ticks += 1
        if ticks % ASSEMBLYAI_LOG_EVERY == 0:
            print(f"[watch] still processing ({ticks * ASSEMBLYAI_POLL_INTERVAL_S}s)…", file=sys.stderr)

    # 4. Parse word-level timestamps into segments
    words = result.get("words") or []
    if not words:
        full = (result.get("text") or "").strip()
        return [{"start": 0.0, "end": 0.0, "text": full}] if full else []

    segments = _group_words_into_segments(words, ms=True)
    print(f"[watch] AssemblyAI: {len(segments)} segments", file=sys.stderr)
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# Deepgram — synchronous POST
# ─────────────────────────────────────────────────────────────────────────────

def _transcribe_deepgram(audio_path: Path, api_key: str) -> list[dict]:
    ctx = ssl.create_default_context()
    data = audio_path.read_bytes()
    url = f"{DEEPGRAM_ENDPOINT}?{DEEPGRAM_PARAMS}"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/mpeg",
    }
    print("[watch] transcribing via Deepgram…", file=sys.stderr)
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=300, context=ctx) as resp:
        result = json.loads(resp.read())

    # Prefer utterances (sentence-level) if present
    utterances = (result.get("results") or {}).get("utterances") or []
    if utterances:
        segments = [
            {
                "start": round(float(u["start"]), 2),
                "end":   round(float(u["end"]),   2),
                "text":  u["transcript"].strip(),
            }
            for u in utterances
            if u.get("transcript", "").strip()
        ]
        print(f"[watch] Deepgram: {len(segments)} utterances", file=sys.stderr)
        return segments

    # Fall back to word-level grouping
    words = (
        ((result.get("results") or {}).get("channels") or [{}])[0]
        .get("alternatives", [{}])[0]
        .get("words") or []
    )
    segments = _group_words_into_segments(words, ms=False)
    print(f"[watch] Deepgram: {len(segments)} segments (word-grouped)", file=sys.stderr)
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# Shared word → segment grouping
# ─────────────────────────────────────────────────────────────────────────────

def _group_words_into_segments(words: list[dict], ms: bool = False) -> list[dict]:
    """Group word-level timestamps into ~5-second sentence-like segments.

    AssemblyAI returns ms timestamps (ms=True); Deepgram returns seconds (ms=False).
    """
    scale = 0.001 if ms else 1.0
    segments: list[dict] = []
    group: list[str] = []
    g_start: float | None = None
    g_end: float = 0.0

    for w in words:
        text = (w.get("text") or w.get("word") or "").strip()
        if not text:
            continue
        start = float(w["start"]) * scale
        end   = float(w["end"])   * scale
        if g_start is None:
            g_start = start
        group.append(text)
        g_end = end
        if (g_end - g_start) >= 5.0 or len(group) >= 20:
            segments.append({
                "start": round(g_start, 2),
                "end":   round(g_end, 2),
                "text":  " ".join(group),
            })
            group = []
            g_start = None

    if group and g_start is not None:
        segments.append({
            "start": round(g_start, 2),
            "end":   round(g_end, 2),
            "text":  " ".join(group),
        })
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_video(
    video_path: str,
    audio_out: Path,
    backend: str | None = None,
    api_key: str | None = None,
) -> tuple[list[dict], str]:
    """Extract audio and transcribe with the best available provider.

    Returns (segments, provider_used). Raises SystemExit on failure.
    Provider auto-selection is based on audio file size after extraction.
    """
    print("[watch] extracting audio…", file=sys.stderr)
    audio_path = extract_audio(video_path, audio_out)
    size_bytes = audio_path.stat().st_size
    size_kb = size_bytes / 1024
    print(f"[watch] audio: {size_kb:.0f} kB", file=sys.stderr)

    if backend is None or api_key is None:
        detected_backend, detected_key = load_api_key(
            preferred=backend, file_size_bytes=size_bytes
        )
        backend  = backend  or detected_backend
        api_key  = api_key  or detected_key

    if not backend or not api_key:
        setup_py = Path(__file__).resolve().parent / "setup.py"
        raise SystemExit(
            "No transcription API key available. Set one of: "
            "GROQ_API_KEY, ASSEMBLYAI_API_KEY, DEEPGRAM_API_KEY, or OPENAI_API_KEY "
            "in the environment or in ~/.config/watch/.env. "
            f"Run `python3 {setup_py}` to configure."
        )

    if backend == "groq":
        response  = _post_whisper(GROQ_ENDPOINT, api_key, GROQ_MODEL, audio_path)
        segments  = _segments_from_whisper_response(response)
    elif backend == "openai":
        response  = _post_whisper(OPENAI_ENDPOINT, api_key, OPENAI_MODEL, audio_path)
        segments  = _segments_from_whisper_response(response)
    elif backend == "assemblyai":
        segments  = _transcribe_assemblyai(audio_path, api_key)
    elif backend == "deepgram":
        segments  = _transcribe_deepgram(audio_path, api_key)
    else:
        raise SystemExit(f"Unknown provider: {backend}")

    if not segments:
        raise SystemExit(f"{backend} returned no transcript segments")

    print(f"[watch] transcribed {len(segments)} segments via {backend}", file=sys.stderr)
    return segments, backend


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry (standalone testing)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: whisper.py <video-path> [<audio-out.mp3>] "
            "[--provider groq|openai|assemblyai|deepgram]",
            file=sys.stderr,
        )
        raise SystemExit(2)

    video = sys.argv[1]
    audio_out = (
        Path(sys.argv[2])
        if len(sys.argv) > 2 and not sys.argv[2].startswith("--")
        else Path("audio.mp3")
    )
    provider_override = None
    if "--provider" in sys.argv:
        provider_override = sys.argv[sys.argv.index("--provider") + 1]
    elif "--backend" in sys.argv:   # legacy alias
        provider_override = sys.argv[sys.argv.index("--backend") + 1]

    segs, used = transcribe_video(video, audio_out, backend=provider_override)
    print(json.dumps({"provider": used, "segments": segs}, indent=2))
