# 🎵 LyricLift

A clean, simple web app that extracts spoken words and lyrics from any video or audio URL (YouTube, Facebook, Instagram, Vimeo, etc.) or uploaded audio files, with optional timestamps.

## Features

✨ **Multiple Input Methods**
- Paste URLs from YouTube, Facebook, Instagram, Vimeo, and other platforms
- Upload local audio/video files (MP3, MP4, M4A, WAV, MOV, WEBM)

📝 **Output Formats**
- **With Timestamps (SRT)** - Standard SubRip format with timing information
- **Plain Text** - Clean text transcription without timestamps

⚡ **Background Processing**
- Uses OpenAI Whisper (tiny model) for accurate transcription
- Automatic audio download and extraction via yt-dlp
- Jobs run asynchronously; the browser polls for status while processing

💾 **Easy Export**
- Copy to clipboard with one click
- Download the result as an .srt or .txt file (generated client-side from the returned text)

🔒 **Privacy-Focused**
- Stateless processing - no database
- Automatic cleanup of temporary files
- All processing happens on your server

## Tech Stack

- **Frontend**: Vanilla JavaScript, HTML5, CSS3 (`index.html` + `assets/`)
- **Backend**: Python 3 + Flask (`app.py`), served by gunicorn behind nginx
- **Audio Processing**: yt-dlp (for URL downloads) + OpenAI Whisper (for transcription)
- **JS runtime**: deno or node (required by yt-dlp for modern YouTube extraction)
- **No Database**: Completely stateless; job state is small JSON files in `tmp/`

## Project Structure

```
LyricLift/
├── app.py                 # Flask backend (routes, yt-dlp + Whisper orchestration)
├── index.html             # Main UI (served by Flask at /)
├── assets/
│   ├── css/style.css      # Styling
│   ├── js/app.js          # Frontend logic
│   └── images/            # Favicon + social preview referenced by index.html
├── tmp/                   # Temporary storage for uploads + job status (auto-cleanup)
├── requirements.txt       # Python dependencies
├── lyriclift-flask.conf   # Nginx configuration (proxies to Flask on :5000)
├── lyriclift.service      # systemd unit (gunicorn)
├── DEPLOY_FLASK.md        # Deployment guide
└── README.md              # This file
```

## Development

### Local Testing

```bash
cd /Users/chipmcallister/Projects/LyricLift
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install yt-dlp openai-whisper   # processing tools (not in requirements.txt)
python app.py
```

Open http://127.0.0.1:5000 in your browser.

> **YouTube note:** yt-dlp needs a JavaScript runtime to solve YouTube's player
> challenges. Install `deno` (recommended) or `node` and make sure it is on the
> PATH of the process running `app.py`. The app auto-detects deno → node → bun,
> or you can force one with `LYRICLIFT_JS_RUNTIME=deno`.

### Requirements

- Python 3.8+
- Flask + Werkzeug + gunicorn (`pip install -r requirements.txt`)
- yt-dlp (`pip install yt-dlp`)
- OpenAI Whisper (`pip install openai-whisper`)
- ffmpeg (used by yt-dlp/Whisper for audio extraction)
- A JS runtime on PATH: `deno`, `node`, or `bun`
- Writable `tmp/` directory

## How It Works

1. **Submit** — the browser POSTs a URL or file to `/extract`. Flask validates it,
   creates a job ID, writes an initial status file, and starts a background thread,
   returning `202 { jobId, status: "processing" }` immediately.
2. **URL download** — if a URL was given, `yt-dlp` downloads the audio (m4a),
   passing `--js-runtimes <detected runtime>` so YouTube extraction works.
3. **Transcription** — Whisper processes the audio:
   - Model: `tiny` (lightweight, fast)
   - Language: English
   - Output format: SRT (with timestamps) or TXT (plain text)
4. **Polling** — the browser polls `GET /status/<jobId>` every few seconds. Each
   response reports `queued` / `downloading` / `transcribing` / `done` / `error`.
5. **Result** — on `done`, the status payload includes the transcribed `text` and a
   suggested `filename`. The UI shows the text and offers copy/download.
6. **Cleanup** — the source audio and Whisper output for a job are deleted as soon
   as the job finishes; leftover job files are swept after their TTL.

## Configuration

Environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `LYRICLIFT_PROCESSING_TIMEOUT_SECONDS` | `0` (no timeout) | Max seconds for the Whisper subprocess |
| `LYRICLIFT_JS_RUNTIME` | auto-detect | Force a specific yt-dlp JS runtime (`deno`/`node`/`bun`) |

Limits (in `app.py`):

- **Max upload size**: 100MB (`MAX_UPLOAD_BYTES`)
- **Job TTL**: 6 hours (`JOB_TTL_SECONDS`)

### Whisper Command

```bash
XDG_CACHE_HOME=<cache> python3 -m whisper <audio> \
  --model tiny \
  --language English \
  --output_format srt|txt \
  --device cpu \
  --no_speech_threshold 0.1
```

### Nginx Limits

- **Max upload size**: 100MB (`client_max_body_size 100M`)
- **Proxy timeout**: 600 seconds (`proxy_read_timeout`)
- **Upstream**: Flask/gunicorn on `127.0.0.1:5000`

## Supported Input Formats

### URLs
- YouTube, Facebook, Instagram, Vimeo, TikTok, Twitter/X, Twitch, Dailymotion,
  and the 1000+ other sites supported by yt-dlp.

### File Uploads
- MP3, MP4, M4A, WAV, MOV, WebM

## Output Formats

### SRT (SubRip with Timestamps)
```
1
00:00:00,000 --> 00:00:05,000
The beginning of the speech

2
00:00:05,000 --> 00:00:10,000
More text continues here
```

### TXT (Plain Text)
```
The beginning of the speech
More text continues here
...
```

## Error Handling

The app returns clear JSON errors for common cases:

- No input → "No URL or file provided"
- Invalid URL → "Invalid URL"
- Unsupported file type → "Invalid file type. Supported: MP3, MP4, M4A, WAV, MOV, WEBM"
- File too large → "File too large. Maximum 100MB."
- Download failure → "Failed to download audio…" (mentions the missing JS runtime if that's the cause)
- No speech → "No speech detected in audio."

## API

### `POST /extract`

Form data:
- `url` (optional): a video/audio URL
- `file` (optional): an uploaded audio/video file
- `format` (required): `"srt"` or `"txt"`

Provide **either** a URL or a file, not both.

Response (`202`):
```json
{ "success": true, "status": "processing", "jobId": "job_20260701123045_abcdef0123" }
```

### `GET /status/<jobId>`

Returns the current job state:
```json
{ "status": "done", "success": true, "text": "…", "filename": "transcription_….srt" }
```
`status` is one of `queued`, `downloading`, `transcribing`, `done`, `error`.

There is no server-side download endpoint: the transcription `text` is returned
in the `/status` payload, and the browser saves it to a file client-side.

## Deployment

See **`DEPLOY_FLASK.md`** for full server setup (systemd + gunicorn + nginx + SSL).

Quick update after a code change:
```bash
rsync -avz --exclude='tmp/*' --exclude='.cache/*' \
  /Users/chipmcallister/Projects/LyricLift/ \
  root@64.227.108.128:/var/www/html/LyricLift/
ssh root@64.227.108.128 systemctl restart lyriclift
```

## Troubleshooting

### YouTube returns "Video unavailable" / download fails
Install a JS runtime on the server and ensure it's on the service PATH:
```bash
curl -fsSL https://deno.land/install.sh | sh   # or: apt install nodejs
```

### Whisper model download fails with an SSL error
Pre-bake the model into the deploy (`~/.cache/whisper/tiny.pt` or the app's
`.cache/whisper/`) so it never has to download at runtime, or fix the system CA
bundle. Do **not** rely on `PYTHONHTTPSVERIFY=0` — it does not reliably bypass
the error.

### 502 Bad Gateway from nginx
- Check the service: `systemctl status lyriclift`
- Confirm gunicorn is listening: `netstat -tlnp | grep 5000`
- Check logs: `journalctl -u lyriclift -n 50`

## Credits

Built with:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Media download
- [OpenAI Whisper](https://github.com/openai/whisper) - Audio transcription
- Flask - Backend
- Vanilla JavaScript - No frontend frameworks
