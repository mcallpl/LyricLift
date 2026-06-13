#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import subprocess
import os
import re
from pathlib import Path
from datetime import datetime

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max
app.config['UPLOAD_FOLDER'] = 'tmp'

ALLOWED_EXTENSIONS = {'mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def strip_ansi(text):
    """Remove ANSI color codes"""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Serve the main page"""
    return open('index.php').read()

@app.route('/extract', methods=['POST'])
def extract():
    """Process audio/video and extract transcription"""
    try:
        url = request.form.get('url', '').strip()
        format_type = request.form.get('format', 'srt')

        if format_type not in ['srt', 'txt']:
            return jsonify({'success': False, 'error': 'Invalid format'}), 400

        output_format = 'srt' if format_type == 'srt' else 'txt'
        output_ext = output_format
        audio_path = None

        # Handle file upload
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']

            if not allowed_file(file.filename):
                return jsonify({'success': False, 'error': 'Invalid file type. Supported: MP3, MP4, M4A, WAV, MOV, WEBM'}), 400

            filename = secure_filename(file.filename)
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(audio_path)

        # Handle URL download
        elif url:
            if not url.startswith(('http://', 'https://')):
                return jsonify({'success': False, 'error': 'Invalid URL'}), 400

            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], 'download.m4a')

            cmd = f'python3 -m yt_dlp -f bestaudio -x --audio-format m4a --audio-quality 192K -o "{audio_path}" "{url}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)

            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                return jsonify({'success': False, 'error': 'Failed to download audio. Check the URL.'}), 400

        else:
            return jsonify({'success': False, 'error': 'No URL or file provided'}), 400

        # Check file size
        if os.path.getsize(audio_path) > 100 * 1024 * 1024:
            os.remove(audio_path)
            return jsonify({'success': False, 'error': 'File too large. Maximum 100MB.'}), 400

        # Run Whisper using shell for proper environment
        cache_dir = os.path.join(os.getcwd(), '.cache')
        os.makedirs(cache_dir, exist_ok=True)

        # Build command with environment variables
        whisper_cmd = f'''export XDG_CACHE_HOME="{cache_dir}" && export PYTHONHTTPSVERIFY=0 && python3 -m whisper "{audio_path}" --model tiny --language English --output_format {output_format} -o "{app.config['UPLOAD_FOLDER']}" --device cpu --no_speech_threshold 0.1'''

        result = subprocess.run(whisper_cmd, shell=True, capture_output=True, text=True, timeout=900)

        # Check if output was created
        output_path = os.path.splitext(audio_path)[0] + '.' + output_ext

        if not os.path.exists(output_path):
            print(f"Whisper failed - Return code: {result.returncode}")
            print(f"Stdout: {result.stdout[:500]}")
            print(f"Stderr: {result.stderr[:500]}")
            if os.path.exists(audio_path):
                os.remove(audio_path)
            return jsonify({'success': False, 'error': 'Transcription failed. Please try again.'}), 400

        # Read transcription
        with open(output_path, 'r') as f:
            text = f.read()

        text = strip_ansi(text).strip()

        if not text:
            os.remove(audio_path)
            os.remove(output_path)
            return jsonify({'success': False, 'error': 'No speech detected in audio.'}), 400

        # Clean up audio file
        os.remove(audio_path)

        filename = f'transcription_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.{output_ext}'

        return jsonify({
            'success': True,
            'text': text,
            'filename': filename
        })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Processing timeout. File may be too long.'}), 500
    except Exception as e:
        print(f"Exception: {str(e)}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

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
