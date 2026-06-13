# 🎵 LyricLift

A clean, simple web app that extracts spoken words and lyrics from any video or audio URL (YouTube, Facebook, Instagram, Vimeo, etc.) or uploaded audio files, with optional timestamps.

## Features

✨ **Multiple Input Methods**
- Paste URLs from YouTube, Facebook, Instagram, Vimeo, and other platforms
- Upload local audio/video files (MP3, MP4, M4A, WAV, MOV, WEBM)

📝 **Output Formats**
- **With Timestamps (SRT)** - Standard SubRip format with timing information
- **Plain Text** - Clean text transcription without timestamps

⚡ **Lightning-Fast Processing**
- Uses OpenAI Whisper (tiny model) for accurate transcription
- Automatic audio download and extraction via yt-dlp
- Processing typically completes in 1-5 minutes depending on file length

💾 **Easy Export**
- Copy to clipboard with one click
- Download as .srt or .txt file
- Clean, readable formatting

🔒 **Privacy-Focused**
- Stateless processing - no database
- Automatic cleanup of temporary files after 1 hour
- All processing happens on your server

## Tech Stack

- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Backend**: PHP 8+
- **Audio Processing**: yt-dlp (for URL downloads) + OpenAI Whisper (for transcription)
- **Server**: Nginx + PHP-FPM
- **No Database**: Completely stateless

## Project Structure

```
LyricLift/
├── index.php              # Main UI
├── extract.php            # Backend processor (yt-dlp + Whisper)
├── download.php           # File download handler
├── tmp/                   # Temporary storage (auto-cleanup)
├── assets/
│   ├── css/style.css      # Styling
│   └── js/app.js          # Frontend logic
├── lyriclift.conf         # Nginx configuration
├── DEPLOYMENT.md          # Deployment guide
└── README.md              # This file
```

## Development

### Local Testing

```bash
cd /Users/chipmcallister/Projects/LyricLift
php -S localhost:8000
```

Open http://localhost:8000 in your browser.

### Requirements

- PHP 8.0+ with `shell_exec` enabled
- Python 3.7+
- yt-dlp (installed: `pip3 install yt-dlp`)
- OpenAI Whisper (installed: `pip3 install openai-whisper`)
- Writable tmp/ directory (775 permissions)

## How It Works

1. **URL Processing**: When a URL is provided, `extract.php` uses `yt-dlp` to download the audio
2. **File Upload**: Uploaded files are moved to the temporary directory with a unique job ID
3. **Transcription**: Whisper processes the audio with:
   - Model: `tiny` (lightweight, fast)
   - Language: English
   - Output format: SRT (with timestamps) or TXT (plain text)
4. **Response**: Results returned as JSON with formatted text
5. **Cleanup**: Temporary files older than 1 hour are automatically deleted

## Configuration

### PHP Settings (in extract.php)

```php
ini_set('max_execution_time', 300);    // 5 minutes
ini_set('memory_limit', '256M');       // Max memory
```

### Whisper Command

```bash
PYTHONHTTPSVERIFY=0 python3 -m whisper \
  --model tiny \
  --language English \
  --output_format srt|txt
```

### Nginx Limits

- **Max upload size**: 100MB (`client_max_body_size 100M`)
- **PHP-FPM timeout**: 300 seconds (`fastcgi_read_timeout 300`)
- **Socket**: `/var/run/php/php8.2-fpm.sock` (adjust for your version)

## Supported Input Formats

### URLs
- YouTube
- Facebook
- Instagram
- Vimeo
- TikTok
- Twitter/X
- Twitch
- Dailymotion
- And 1000+ other sites supported by yt-dlp

### File Uploads
- MP3 (`.mp3`)
- MP4 (`.mp4`)
- M4A (`.m4a`)
- WAV (`.wav`)
- MOV (`.mov`)
- WebM (`.webm`)

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

The app handles common errors gracefully:

- Invalid URLs → "Failed to download audio. Please check the URL and try again."
- Unsupported file types → "Invalid file type. Supported: MP3, MP4, M4A, WAV, MOV, WEBM"
- File too large → "File too large. Maximum size: 1GB"
- Transcription failed → "Transcription failed. Please try again or upload a different file."

Users always get clear feedback.

## Security

- ✅ File upload validation (extension and size checks)
- ✅ Command injection prevention (proper escaping with `escapeshellarg()`)
- ✅ Nginx prevents direct access to tmp/ directory
- ✅ Automatic cleanup of old files
- ✅ No database queries (no SQL injection risk)
- ✅ HTTPS enforced via Certbot after deployment

## Performance

**Processing Time Estimates** (Tiny Model on CPU):
- 1 minute audio → ~30-60 seconds
- 5 minutes audio → ~2-3 minutes
- 30 minutes audio → ~10-15 minutes
- 1 hour audio → ~20-30 minutes

Times vary by server CPU. GPU would be 5-10x faster if available.

## Deployment

See `DEPLOYMENT.md` for complete server setup instructions including:
- SSH into empire-command
- Install dependencies
- Deploy files
- Configure Nginx
- Set up SSL with Certbot

Quick summary:
```bash
# From your local machine
rsync -avz --exclude='tmp/*' \
  /Users/chipmcallister/Projects/LyricLift/ \
  root@64.227.108.128:/var/www/html/LyricLift/

# On the server
ssh root@64.227.108.128
cp /var/www/html/LyricLift/lyriclift.conf /etc/nginx/sites-available/lyriclift
ln -s /etc/nginx/sites-available/lyriclift /etc/nginx/sites-enabled/lyriclift
nginx -t
systemctl reload nginx
certbot --nginx -d lyriclift.peoplestar.com --non-interactive --agree-tos -m mcallpl@gmail.com
systemctl reload nginx
```

## Troubleshooting

### Whisper SSL Error
```bash
# Set in extract.php (already done)
PYTHONHTTPSVERIFY=0
```

### Permission Denied on tmp/
```bash
chmod 775 /var/www/html/LyricLift/tmp
chown www-data:www-data /var/www/html/LyricLift/tmp
```

### PHP-FPM 502 Bad Gateway
- Check `systemctl status php8.2-fpm`
- Verify socket path in nginx config
- Check `/var/log/nginx/lyriclift_error.log`

### Long Transcriptions Timeout
- Increase `fastcgi_read_timeout` in nginx (currently 300 seconds)
- Ensure sufficient free disk space in tmp/

## API

### extract.php

**Request (POST)**
```
Form data:
- url (optional): YouTube/Vimeo/etc URL
- file (optional): Uploaded audio/video file
- format (required): "srt" or "txt"
```

**Response (JSON)**
```json
{
  "success": true,
  "jobId": "job_666c1a1d45e7e_a1b2c3d4",
  "filename": "transcription_2026-06-12_10-30-45.srt",
  "text": "Transcribed text here..."
}
```

### download.php

**Request (GET)**
```
?file=transcription_2026-06-12_10-30-45.srt&job=job_666c1a1d45e7e_a1b2c3d4
```

Returns the transcription file for download.

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## License

Built for personal use. Modify as needed.

## Credits

Built with:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Media download
- [OpenAI Whisper](https://github.com/openai/whisper) - Audio transcription
- Vanilla JavaScript - No frameworks
- PHP - Server-side processing

## Support

For issues or questions:
1. Check `DEPLOYMENT.md` troubleshooting section
2. Review nginx/PHP logs
3. Test yt-dlp and Whisper independently
4. Verify all dependencies are installed
