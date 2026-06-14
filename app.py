#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import subprocess
import os
import re
import json
import threading
import uuid
from datetime import datetime, timezone

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
PROCESSING_TIMEOUT_SECONDS = 3600
JOB_TTL_SECONDS = 6 * 60 * 60

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES
app.config['UPLOAD_FOLDER'] = 'tmp'

ALLOWED_EXTENSIONS = {'mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

def remove_if_exists(path):
    if path and os.path.exists(path):
        os.remove(path)

def cleanup_old_jobs():
    cutoff = datetime.now(timezone.utc).timestamp() - JOB_TTL_SECONDS
    for name in os.listdir(app.config['UPLOAD_FOLDER']):
        path = os.path.join(app.config['UPLOAD_FOLDER'], name)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            remove_if_exists(path)

def run_transcription_job(job_id, audio_path, url, format_type):
    output_format = 'srt' if format_type == 'srt' else 'txt'
    output_ext = output_format
    output_path = os.path.splitext(audio_path)[0] + f'.{output_ext}'

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
                url
            ]
            result = subprocess.run(
                download_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0 or not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                write_job_status(
                    job_id,
                    success=False,
                    status='error',
                    error='Failed to download audio. Check the URL and try again.'
                )
                return

        if os.path.getsize(audio_path) > MAX_UPLOAD_BYTES:
            write_job_status(
                job_id,
                success=False,
                status='error',
                error='File too large. Maximum 100MB.'
            )
            return

        cache_dir = os.path.join(os.getcwd(), '.cache')
        os.makedirs(cache_dir, exist_ok=True)

        write_job_status(
            job_id,
            success=True,
            status='transcribing',
            message='Transcribing audio...'
        )

        env = os.environ.copy()
        env['XDG_CACHE_HOME'] = cache_dir
        env['PYTHONHTTPSVERIFY'] = '0'
        whisper_cmd = [
            'python3', '-m', 'whisper',
            audio_path,
            '--model', 'tiny',
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
            timeout=PROCESSING_TIMEOUT_SECONDS,
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
        write_job_status(
            job_id,
            success=False,
            status='error',
            error='Processing timeout. This file took too long to transcribe.'
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
        remove_if_exists(audio_path)
        remove_if_exists(output_path)

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
    return open('index.php').read()

@app.route('/extract', methods=['POST'])
def extract():
    """Process audio/video and extract transcription"""
    try:
        cleanup_old_jobs()

        url = request.form.get('url', '').strip()
        format_type = request.form.get('format', 'srt')

        if format_type not in ['srt', 'txt']:
            return jsonify({'success': False, 'error': 'Invalid format'}), 400

        job_id = make_job_id()

        # Handle file upload
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']

            if not allowed_file(file.filename):
                return jsonify({'success': False, 'error': 'Invalid file type. Supported: MP3, MP4, M4A, WAV, MOV, WEBM'}), 400

            original_filename = secure_filename(file.filename)
            ext = original_filename.rsplit('.', 1)[1].lower()
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}.{ext}')
            file.save(audio_path)

            if os.path.getsize(audio_path) > MAX_UPLOAD_BYTES:
                remove_if_exists(audio_path)
                return jsonify({'success': False, 'error': 'File too large. Maximum 100MB.'}), 400

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
    return jsonify({'success': False, 'error': 'File too large. Maximum 100MB.'}), 413

@app.route('/download/<path:filename>', methods=['GET'])
def download(filename):
    """Download transcription file"""
    try:
        from flask import send_file
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404

        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
