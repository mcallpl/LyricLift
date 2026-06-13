# LyricLift - Quick Start Guide

## 🚀 Project Completion Summary

LyricLift has been fully built and tested. All files are ready for deployment.

### ✅ What's Included

```
index.php          - Clean UI with dark theme, file upload, URL input
extract.php        - Backend processor (yt-dlp + Whisper)
download.php       - File download handler
assets/css/        - Modern styling with dark mode
assets/js/         - Vanilla JS frontend logic
lyriclift.conf     - Nginx server block configuration
tmp/               - Auto-cleanup temp directory (775 perms)
README.md          - Full documentation
DEPLOYMENT.md      - Server setup guide
```

### 🎯 Features Implemented

✅ URL input for YouTube, Facebook, Instagram, etc.  
✅ File upload with drag & drop (MP3, MP4, M4A, WAV, MOV, WEBM)  
✅ Output format selection (With Timestamps / Plain Text)  
✅ Loading spinner with cycling status messages  
✅ Beautiful results display in textarea  
✅ Copy to clipboard button  
✅ Download as .srt or .txt  
✅ Automatic cleanup of old temp files  
✅ Comprehensive error handling  
✅ Dark mode UI with accent colors  
✅ Responsive design (mobile-friendly)  

### 🔧 Tech Verified

✅ Python 3 installed  
✅ yt-dlp working (v2026.06.09)  
✅ Whisper installed and tested  
✅ PHP shell_exec enabled  
✅ tmp/ directory writable (775)  

---

## 📋 Before You Deploy

### 1. Test Locally (Optional)

```bash
cd /Users/chipmcallister/Projects/LyricLift
php -S localhost:8000
# Open http://localhost:8000 in your browser
```

### 2. Verify DNS

Make sure the A record is created:
```
lyriclift.peoplestar.com  A  64.227.108.128
```

Check with:
```bash
dig lyriclift.peoplestar.com
```

---

## 📤 Deployment (5 Steps)

### Step 1: SSH to Server

```bash
ssh root@64.227.108.128
```

### Step 2: Create Directories & Set Permissions

```bash
mkdir -p /var/www/html/LyricLift/tmp
chmod 775 /var/www/html/LyricLift/tmp
chown www-data:www-data /var/www/html/LyricLift -R
```

### Step 3: Install Python Packages (on server)

```bash
pip3 install yt-dlp openai-whisper --break-system-packages
```

### Step 4: Deploy Files (from your local machine)

```bash
rsync -avz --delete --exclude='tmp/*' \
  /Users/chipmcallister/Projects/LyricLift/ \
  root@64.227.108.128:/var/www/html/LyricLift/
```

### Step 5: Setup Nginx & SSL (on server)

```bash
# Copy nginx config
cp /var/www/html/LyricLift/lyriclift.conf /etc/nginx/sites-available/lyriclift
ln -s /etc/nginx/sites-available/lyriclift /etc/nginx/sites-enabled/lyriclift

# Test and reload
nginx -t
systemctl reload nginx

# Setup SSL (requires DNS to be propagated)
certbot --nginx -d lyriclift.peoplestar.com --non-interactive --agree-tos -m mcallpl@gmail.com

# Reload nginx again
systemctl reload nginx
```

---

## ✨ Done!

Your app is now live at:
- 🌐 https://lyriclift.peoplestar.com

### Test It

1. Paste a YouTube URL (e.g., https://www.youtube.com/watch?v=...)
2. Select "With Timestamps"
3. Click "Extract Words"
4. Wait for processing (1-5 minutes depending on file length)
5. Copy or download the results

---

## 🆘 Common Issues

### Whisper SSL Error
```bash
# Already handled in extract.php with:
PYTHONHTTPSVERIFY=0
```

### Permission Denied on tmp/
```bash
chmod 775 /var/www/html/LyricLift/tmp
chown www-data:www-data /var/www/html/LyricLift/tmp
```

### PHP Returns 502
```bash
# Check PHP-FPM is running
systemctl status php8.2-fpm

# View error log
tail -f /var/log/nginx/lyriclift_error.log
```

### Processing Takes Too Long
- First transcription can take 2-3 min (model loads)
- Subsequent files are faster
- Very long files (1+ hour) need more time
- Can increase `fastcgi_read_timeout` in nginx if needed

---

## 📖 Full Docs

- `README.md` - Complete feature and API documentation
- `DEPLOYMENT.md` - Detailed server setup and troubleshooting

---

## 📊 File Breakdown

### Backend
- **extract.php** (170 lines)
  - Accepts URL or file upload
  - Runs yt-dlp for URL downloads
  - Runs Whisper for transcription
  - Returns JSON with results
  - Auto-cleanup of old files

- **download.php** (35 lines)
  - Serves transcription files for download
  - Validates job ID and filename

### Frontend
- **index.php** (90 lines)
  - HTML structure
  - Form inputs and UI elements

- **assets/js/app.js** (150 lines)
  - File upload/drag-drop handling
  - API calls to extract.php
  - Results display and export
  - Error handling and messages

- **assets/css/style.css** (350 lines)
  - Dark theme with blue accents
  - Responsive layout
  - Loading spinner animation
  - Form styling and states

### Config
- **lyriclift.conf** (30 lines)
  - Nginx server block
  - PHP-FPM configuration
  - Security headers
  - Timeout settings

---

## 💡 Tips

**File Size Limits**
- Max upload: 100MB (configurable in nginx)
- Processing time: ~1sec per 30 seconds of audio
- Very large files may timeout (increase `fastcgi_read_timeout`)

**Monitoring**
```bash
# Watch access log
tail -f /var/log/nginx/lyriclift_access.log

# Check tmp/ size
du -sh /var/www/html/LyricLift/tmp
```

**Updates**
To push code updates:
```bash
rsync -avz --exclude='tmp/*' \
  /Users/chipmcallister/Projects/LyricLift/ \
  root@64.227.108.128:/var/www/html/LyricLift/
systemctl reload nginx
```

---

## 🎉 You're All Set!

Everything is ready to go. Follow the 5 deployment steps above and your app will be live.

Questions? Check DEPLOYMENT.md or README.md.
