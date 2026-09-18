#!/usr/bin/env python3
from flask import Flask, request, jsonify
import subprocess
import os
import re
import json
import shutil
import ssl
import hashlib
import urllib.request
import threading
import uuid
from datetime import datetime, timezone

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
from ck1pw.door import register_ck1pw
register_ck1pw(app)
from ck1pw.gate import register_gate
register_gate(app)
# Upload ceiling. Raised from 100MB on 2026-09-17: a 69-minute Zoom
# "Complete_Audio.m4a" is 123MB and was rejected by nginx with a 413 before the
# app ever saw it. nginx's client_max_body_size must be raised to match (see
# lyriclift-flask.conf) -- nginx rejects first, so the Flask limit alone is not
# enough. Override with LYRICLIFT_MAX_UPLOAD_MB.
MAX_UPLOAD_MB = int(os.environ.get('LYRICLIFT_MAX_UPLOAD_MB', '1024'))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
# Long recordings can take hours on the small CPU-only production server.
# A value of 0 disables the Whisper subprocess timeout.
PROCESSING_TIMEOUT_SECONDS = int(os.environ.get('LYRICLIFT_PROCESSING_TIMEOUT_SECONDS', '0'))
JOB_TTL_SECONDS = 6 * 60 * 60

WHISPER_MODEL = 'tiny'
# Whisper model download URLs (from openai-whisper's own registry). The sha256
# checksum is the hex string embedded in the URL path; we verify against it.
WHISPER_MODEL_URLS = {
    'tiny': 'https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt',
}
# Where the app keeps caches (Whisper model, etc.), next to app.py.
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')

# Optional cookies file for yt-dlp. Cloud/VPS IPs are frequently blocked by
# YouTube's bot check ("Sign in to confirm you're not a bot" / HTTP 429);
# supplying cookies exported from a logged-in session is the standard workaround.
# Drop a Netscape-format cookies.txt at this path (or set LYRICLIFT_YTDLP_COOKIES)
# and it's used automatically. If the file is absent, downloads run without it.
YTDLP_COOKIES_FILE = os.environ.get(
    'LYRICLIFT_YTDLP_COOKIES',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'youtube_cookies.txt')
)

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES
app.config['UPLOAD_FOLDER'] = 'tmp'

ALLOWED_EXTENSIONS = {'mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def detect_js_runtime():
    """Return the name of an installed JavaScript runtime for yt-dlp, if any.

    Modern YouTube extraction requires a JS runtime to solve player challenges;
    without one yt-dlp reports "Video unavailable". yt-dlp only auto-enables
    'deno', so if the server has 'node' instead we must pass it explicitly.
    Preference order matches yt-dlp's own recommendation (deno first).
    An operator can override with LYRICLIFT_JS_RUNTIME.
    """
    override = os.environ.get('LYRICLIFT_JS_RUNTIME', '').strip()
    if override:
        return override
    for runtime in ('deno', 'node', 'bun'):
        if shutil.which(runtime):
            return runtime
    return None

def _ca_bundle():
    """Return the path to a CA bundle for TLS verification, preferring certifi.

    Whisper (and many tools) verify TLS against the system trust store, which can
    be incomplete on minimal servers. certifi ships a known-good bundle.
    """
    try:
        import certifi
        return certifi.where()
    except Exception:
        return None

def whisper_cache_dir():
    return os.path.join(CACHE_DIR, 'whisper')

def ensure_whisper_model():
    """Make sure the Whisper model is cached locally before transcription runs.

    Whisper otherwise downloads the model on first use via urllib at request time,
    which is fragile: it was the real cause of the "SSL: CERTIFICATE_VERIFY_FAILED"
    failures that PYTHONHTTPSVERIFY=0 did not fix. We fetch it ahead of time with a
    proper CA bundle and verify its checksum, so the transcription subprocess never
    needs the network. Returns True if the model is present afterwards.

    For production, prefer baking the model file into the deploy so this never has
    to hit the network at all.
    """
    url = WHISPER_MODEL_URLS.get(WHISPER_MODEL)
    if not url:
        return False

    cache_dir = whisper_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    target = os.path.join(cache_dir, os.path.basename(url))
    expected_sha = os.path.basename(os.path.dirname(url))

    if os.path.exists(target) and os.path.getsize(target) > 0:
        return True

    context = ssl.create_default_context(cafile=_ca_bundle())
    # Per-process temp name so two gunicorn workers doing a cold-start download
    # don't write the same file and corrupt each other.
    tmp_target = f'{target}.{os.getpid()}.download'
    try:
        with urllib.request.urlopen(url, context=context, timeout=120) as resp, \
                open(tmp_target, 'wb') as out:
            shutil.copyfileobj(resp, out)

        digest = hashlib.sha256()
        with open(tmp_target, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(chunk)
        if expected_sha and digest.hexdigest() != expected_sha:
            remove_if_exists(tmp_target)
            print(f"Whisper model checksum mismatch for '{WHISPER_MODEL}'")
            return False

        os.replace(tmp_target, target)
        print(f"Whisper model '{WHISPER_MODEL}' cached at {target}")
        return True
    except Exception as e:
        remove_if_exists(tmp_target)
        print(f"Failed to pre-fetch Whisper model '{WHISPER_MODEL}': {e}")
        return os.path.exists(target) and os.path.getsize(target) > 0

def strip_ansi(text):
    """Remove ANSI color codes"""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def make_job_id():
    return f"job_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}"

def is_safe_job_id(job_id):
    return bool(re.fullmatch(r'[A-Za-z0-9_.-]+', job_id or ''))

def job_status_path(job_id):
    return os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}.json')

def write_job_status(job_id, **data):
    payload = {
        'jobId': job_id,
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        **data
    }
    status_path = job_status_path(job_id)
    tmp_path = f'{status_path}.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(payload, f)
    os.replace(tmp_path, status_path)

def read_job_status(job_id):
    with open(job_status_path(job_id), 'r') as f:
        return json.load(f)

def remove_tree_if_exists(path):
    """Delete a directory and everything under it, ignoring absence."""
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Could not remove directory {path}: {e}")


def remove_if_exists(path):
    if path and os.path.exists(path):
        os.remove(path)

def start_job_heartbeat(job_id, interval=300):
    """Keep a running job's status file 'fresh' so the TTL sweeper won't delete it.

    cleanup_old_jobs() removes files by mtime, but a job's status mtime is only
    written at each state transition — so a transcription that runs longer than
    JOB_TTL_SECONDS would otherwise get swept mid-run (breaking /status polling).
    This bumps the status file's mtime periodically while the job is alive; an
    orphaned job (crashed worker) stops heartbeating and ages out normally.
    Returns a threading.Event — call .set() to stop the heartbeat.
    """
    stop = threading.Event()

    def _beat():
        while not stop.wait(interval):
            try:
                os.utime(job_status_path(job_id), None)
            except OSError:
                pass

    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    return stop

# Everything a job can leave behind except its .json status file, which holds the
# delivered text and is what the browser reads. Media is the expensive part: a
# single upload can be hundreds of MB.
JOB_MEDIA_EXTENSIONS = {'mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm', 'opus', 'ogg', 'flac', 'aac', 'part', 'tmp'}
JOB_OUTPUT_EXTENSIONS = {'txt', 'srt', 'vtt', 'tsv', 'json.tmp'}
# A transcript is text; even a multi-hour recording is well under a MB. A status
# file far past this means something is wrong, and it is not worth keeping.
MAX_STATUS_BYTES = 2 * 1024 * 1024


def purge_job_artifacts(job_id, keep_status=True):
    """Delete every file this job created, optionally sparing its status .json.

    Called when a job ends (success or failure) so the disk is reclaimed the
    moment the work is done rather than at the end of the 6h TTL window.
    """
    if not is_safe_job_id(job_id):
        return
    folder = app.config['UPLOAD_FOLDER']
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.startswith('.') or not name.startswith(job_id):
            continue
        if keep_status and name == f'{job_id}.json':
            continue
        target = os.path.join(folder, name)
        if os.path.isdir(target):
            remove_tree_if_exists(target)
        else:
            remove_if_exists(target)


def reclaim_orphaned_jobs():
    """Clear debris left by a job that was killed before its finally block ran.

    A gunicorn restart (a deploy!), an OOM kill, or a crash all terminate the
    worker thread outright, so run_transcription_job's finally never executes
    and its upload -- potentially hundreds of MB -- is stranded in tmp/ forever.
    Runs once at import, when by definition no job of ours is in flight.

    Any job still marked queued/transcribing was interrupted by whatever
    stopped the process. It is rewritten as an explicit error so the browser
    polling /status gets a truthful answer instead of timing out against a
    status that will never change again.
    """
    folder = app.config['UPLOAD_FOLDER']
    try:
        names = os.listdir(folder)
    except OSError:
        return
    freed = 0
    for name in names:
        if name.startswith('.'):
            continue
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            # An orphaned per-job cache directory from a killed job.
            if name.endswith('.cache'):
                remove_tree_if_exists(path)
            continue
        if not os.path.isfile(path):
            continue
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext in JOB_MEDIA_EXTENSIONS or ext in JOB_OUTPUT_EXTENSIONS:
            try:
                freed += os.path.getsize(path)
            except OSError:
                pass
            remove_if_exists(path)
    for name in names:
        if not name.endswith('.json') or name.startswith('.'):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get('status') in ('queued', 'downloading', 'transcribing'):
            job_id = data.get('jobId') or name[:-len('.json')]
            write_job_status(
                job_id,
                success=False,
                status='error',
                error='Processing was interrupted because the server restarted. '
                      'Nothing was lost on your end -- please upload the file again.'
            )
            print(f"Marked interrupted job {job_id} as errored on startup.")
    if freed:
        print(f"Startup reclaim: freed {freed / (1024 * 1024):.1f}MB of orphaned job media.")


def cleanup_old_jobs():
    cutoff = datetime.now(timezone.utc).timestamp() - JOB_TTL_SECONDS
    for name in os.listdir(app.config['UPLOAD_FOLDER']):
        # Never sweep dotfiles like .gitkeep that keep the directory in git.
        if name.startswith('.'):
            continue
        path = os.path.join(app.config['UPLOAD_FOLDER'], name)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            remove_if_exists(path)

def start_cleanup_scheduler(interval_seconds=None):
    """Periodically sweep stale job files even when no new jobs arrive.

    cleanup_old_jobs() was previously only called at the start of /extract, so an
    idle server would keep old job files (which contain transcribed text) past
    their TTL indefinitely. This runs it on a background daemon timer as well.
    """
    if interval_seconds is None:
        # Sweep a few times per TTL window, at least hourly.
        interval_seconds = max(600, min(3600, JOB_TTL_SECONDS // 4))

    def _run():
        try:
            cleanup_old_jobs()
        except Exception as e:
            print(f"Periodic cleanup failed: {e}")
        finally:
            timer = threading.Timer(interval_seconds, _run)
            timer.daemon = True
            timer.start()

    first = threading.Timer(interval_seconds, _run)
    first.daemon = True
    first.start()

def whisper_timeout():
    return PROCESSING_TIMEOUT_SECONDS if PROCESSING_TIMEOUT_SECONDS > 0 else None

def run_transcription_job(job_id, audio_path, url, format_type):
    output_format = 'srt' if format_type == 'srt' else 'txt'
    output_ext = output_format
    output_path = os.path.splitext(audio_path)[0] + f'.{output_ext}'

    heartbeat_stop = start_job_heartbeat(job_id)
    try:
        if url:
            write_job_status(
                job_id,
                success=True,
                status='downloading',
                message='Downloading audio...'
            )
            download_cmd = [
                'python3', '-m', 'yt_dlp',
                '-f', 'bestaudio',
                '-x',
                '--audio-format', 'm4a',
                '--audio-quality', '192K',
                '-o', audio_path,
            ]
            js_runtime = detect_js_runtime()
            if js_runtime:
                download_cmd += ['--js-runtimes', js_runtime]
            cookies_used = os.path.exists(YTDLP_COOKIES_FILE)
            if cookies_used:
                download_cmd += ['--cookies', YTDLP_COOKIES_FILE]
            download_cmd.append(url)
            result = subprocess.run(
                download_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0 or not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                stderr = result.stderr or ''
                bot_blocked = any(s in stderr for s in (
                    'Sign in to confirm', "not a bot", 'HTTP Error 429',
                    '429: Too Many Requests', 'confirm your age'))
                if not js_runtime:
                    error_msg = ('Failed to download audio. No JavaScript runtime '
                                 '(deno/node) is installed, which YouTube now requires. '
                                 'Install one on the server, or check the URL and try again.')
                elif bot_blocked and not cookies_used:
                    error_msg = ('This site blocked the download from our server '
                                 '(bot check / rate limit). YouTube often blocks cloud '
                                 'servers — please upload the audio/video file directly '
                                 'instead.')
                else:
                    error_msg = 'Failed to download audio. Check the URL and try again.'
                print(f"yt-dlp failed for {job_id} (js_runtime={js_runtime}, "
                      f"cookies={cookies_used}) rc={result.returncode}: {stderr[:500]}")
                write_job_status(
                    job_id,
                    success=False,
                    status='error',
                    error=error_msg
                )
                return

        if os.path.getsize(audio_path) > MAX_UPLOAD_BYTES:
            write_job_status(
                job_id,
                success=False,
                status='error',
                error=f'File too large. Maximum {MAX_UPLOAD_MB}MB.'
            )
            return

        cache_dir = CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        # Make sure the speech model is available before we start; this avoids the
        # fragile at-request-time download that caused SSL cert failures.
        if not ensure_whisper_model():
            write_job_status(
                job_id,
                success=False,
                status='error',
                error='Speech recognition model is unavailable on the server. '
                      'Please try again later or contact the administrator.'
            )
            return

        write_job_status(
            job_id,
            success=True,
            status='transcribing',
            message='Transcribing audio... Long recordings can take a while on this server.'
        )

        # Give this job its own disposable cache directory. Whatever whisper,
        # torch, numba or tiktoken decide to cache lands in here and is deleted
        # wholesale when the job ends -- no need to predict their filenames.
        # The MODEL is deliberately NOT in here: it is passed via --model_dir
        # below and lives in the shared, protected .cache/whisper.
        job_scratch = os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}.cache')
        os.makedirs(job_scratch, exist_ok=True)

        env = os.environ.copy()
        env['XDG_CACHE_HOME'] = job_scratch
        # Give the subprocess a good CA bundle instead of disabling verification.
        ca_bundle = _ca_bundle()
        if ca_bundle:
            env['SSL_CERT_FILE'] = ca_bundle
            env['REQUESTS_CA_BUNDLE'] = ca_bundle
        whisper_cmd = [
            'python3', '-m', 'whisper',
            audio_path,
            '--model', WHISPER_MODEL,
            # Explicit, so the disposable XDG_CACHE_HOME above can never send
            # whisper hunting for the model -- or re-downloading it, which fails
            # on a box whose cert chain cannot verify the CDN.
            '--model_dir', whisper_cache_dir(),
            '--language', 'English',
            '--output_format', output_format,
            '-o', app.config['UPLOAD_FOLDER'],
            '--device', 'cpu',
            '--no_speech_threshold', '0.1'
        ]

        result = subprocess.run(
            whisper_cmd,
            capture_output=True,
            text=True,
            timeout=whisper_timeout(),
            env=env
        )

        if not os.path.exists(output_path):
            print(f"Whisper failed for {job_id} - Return code: {result.returncode}")
            print(f"Stdout: {result.stdout[:500]}")
            print(f"Stderr: {result.stderr[:500]}")
            write_job_status(
                job_id,
                success=False,
                status='error',
                error='Transcription failed. Please try a shorter file or a different recording.'
            )
            return

        with open(output_path, 'r') as f:
            text = strip_ansi(f.read()).strip()

        # A transcript is text: ~69 minutes of speech is well under 100KB, so
        # anything near the cap means a runaway (a stuck decode loop repeating a
        # phrase). Truncate rather than write a multi-MB status file the browser
        # then has to poll and parse.
        if len(text.encode('utf-8')) > MAX_STATUS_BYTES:
            text = text.encode('utf-8')[:MAX_STATUS_BYTES].decode('utf-8', 'ignore')
            text += ('\n\n[Transcript truncated at '
                     f'{MAX_STATUS_BYTES // (1024 * 1024)}MB -- the recording produced '
                     'far more text than speech of this length should.]')
            print(f"Job {job_id}: transcript exceeded {MAX_STATUS_BYTES} bytes; truncated.")

        if not text:
            write_job_status(
                job_id,
                success=False,
                status='error',
                error='No speech detected in audio.'
            )
            return

        filename = f'transcription_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.{output_ext}'
        write_job_status(
            job_id,
            success=True,
            status='done',
            text=text,
            filename=filename
        )

    except subprocess.TimeoutExpired:
        timeout_minutes = max(1, PROCESSING_TIMEOUT_SECONDS // 60)
        write_job_status(
            job_id,
            success=False,
            status='error',
            error=f'Processing timeout after {timeout_minutes} minutes. This file took too long to transcribe.'
        )
    except Exception as e:
        print(f"Exception in job {job_id}: {str(e)}")
        write_job_status(
            job_id,
            success=False,
            status='error',
            error=f'Error: {str(e)}'
        )
    finally:
        heartbeat_stop.set()
        remove_if_exists(audio_path)
        remove_if_exists(output_path)
        # Belt and braces: whisper can emit siblings next to the expected output
        # (a second --output_format, a partial write, a .tmp). Sweep anything
        # else carrying this job id, keeping only the .json that holds the
        # delivered text. Nothing here is recoverable once the job has ended.
        purge_job_artifacts(job_id, keep_status=True)
        remove_tree_if_exists(os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}.cache'))

def start_job(job_id, audio_path, url, format_type):
    thread = threading.Thread(
        target=run_transcription_job,
        args=(job_id, audio_path, url, format_type),
        daemon=True
    )
    thread.start()

@app.route('/')
def index():
    """Serve the main page"""
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
    with open(index_path) as f:
        return f.read()

@app.route('/extract', methods=['POST'])
def extract():
    """Process audio/video and extract transcription"""
    try:
        cleanup_old_jobs()

        url = request.form.get('url', '').strip()
        # Default is plain text: the radio in index.html defaults to 'txt', and
        # this fallback matches it so a request that omits the field agrees with
        # what the UI shows. 'srt' remains fully supported.
        format_type = request.form.get('format', 'txt')

        if format_type not in ['srt', 'txt']:
            return jsonify({'success': False, 'error': 'Invalid format'}), 400

        has_file = 'file' in request.files and request.files['file'].filename != ''

        # Reject ambiguous requests that supply both a URL and a file, rather than
        # silently ignoring one of them.
        if url and has_file:
            return jsonify({
                'success': False,
                'error': 'Provide either a URL or a file, not both.'
            }), 400

        job_id = make_job_id()

        # Handle file upload
        if has_file:
            file = request.files['file']

            if not allowed_file(file.filename):
                return jsonify({'success': False, 'error': 'Invalid file type. Supported: MP3, MP4, M4A, WAV, MOV, WEBM'}), 400

            # Take the extension from the original name (allowed_file already
            # verified it's a whitelisted extension). Don't route it through
            # secure_filename: that can strip a non-ASCII basename down to just
            # the extension with no dot (e.g. "Пример.mp3" -> "mp3"), which used
            # to crash here. The saved file is named after the safe job_id anyway.
            ext = file.filename.rsplit('.', 1)[1].lower()
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}.{ext}')
            file.save(audio_path)

            if os.path.getsize(audio_path) > MAX_UPLOAD_BYTES:
                remove_if_exists(audio_path)
                return jsonify({'success': False, 'error': f'File too large. Maximum {MAX_UPLOAD_MB}MB.'}), 400

            write_job_status(
                job_id,
                success=True,
                status='queued',
                message='Queued for transcription...'
            )
            start_job(job_id, audio_path, None, format_type)

        # Handle URL download
        elif url:
            if not url.startswith(('http://', 'https://')):
                return jsonify({'success': False, 'error': 'Invalid URL'}), 400

            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}.m4a')
            write_job_status(
                job_id,
                success=True,
                status='queued',
                message='Queued for download...'
            )
            start_job(job_id, audio_path, url, format_type)

        else:
            return jsonify({'success': False, 'error': 'No URL or file provided'}), 400

        return jsonify({
            'success': True,
            'status': 'processing',
            'jobId': job_id
        }), 202

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Processing timeout. File may be too long.'}), 500
    except Exception as e:
        print(f"Exception: {str(e)}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

@app.route('/status/<job_id>', methods=['GET'])
def status(job_id):
    """Return background transcription status"""
    if not is_safe_job_id(job_id):
        return jsonify({'success': False, 'status': 'error', 'error': 'Invalid job ID'}), 400

    try:
        return jsonify(read_job_status(job_id))
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'status': 'error',
            'error': 'Processing job not found. Please start the extraction again.'
        }), 404
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'error': str(e)}), 500

@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({'success': False, 'error': f'File too large. Maximum {MAX_UPLOAD_MB}MB.'}), 413

# Note: there is intentionally no server-side /download route. The transcription
# text is returned in the /status payload and the browser saves it client-side
# (see the Download button in assets/js/app.js). The generated file in tmp/ is
# deleted as soon as the job finishes, so a server download endpoint could never
# reliably serve it.

# Best-effort model preload at import time so any cert/network problem surfaces in
# the logs at startup instead of on the first user's request. Safe to fail here —
# each job re-checks and reports a clear error if the model is still missing.
try:
    if ensure_whisper_model():
        print("Whisper model ready.")
    else:
        print("WARNING: Whisper model could not be pre-loaded; "
              "transcription will fail until it is available.")
except Exception as _e:
    print(f"WARNING: Whisper model preload raised: {_e}")

# Reclaim anything stranded by a previous process that died mid-job (a deploy
# restart is the common case) before the scheduler's first tick hours from now.
try:
    reclaim_orphaned_jobs()
except Exception as _e:
    print(f"WARNING: startup job reclaim raised: {_e}")

# Sweep stale job files on a background timer so an idle server still cleans up.
start_cleanup_scheduler()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
