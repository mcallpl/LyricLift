# LyricLift Flask Deployment Guide

## Deploy to empire-command (64.227.108.128)

### Step 1: SSH into Server
```bash
ssh root@64.227.108.128
```

### Step 2: Deploy Files
```bash
# From your local machine
rsync -avz --delete --exclude='tmp/*' /Users/chipmcallister/Projects/LyricLift/ root@64.227.108.128:/var/www/html/LyricLift/
```

### Step 3: Install Dependencies
```bash
# On the server
cd /var/www/html/LyricLift
pip3 install -r requirements.txt --break-system-packages
# Processing tools (not pinned in requirements.txt):
pip3 install yt-dlp openai-whisper --break-system-packages
apt install -y ffmpeg

# JS runtime for yt-dlp — REQUIRED for YouTube (solves player challenges).
# Prefer apt's nodejs: it installs to /usr/bin, so it's on the www-data PATH the
# gunicorn service uses. (deno works too but its installer drops it in a user dir
# that www-data can't see unless you add it to the service PATH.)
apt install -y nodejs
# The app auto-detects deno/node/bun; override with LYRICLIFT_JS_RUNTIME if needed.
```

### Step 3b: Pre-bake the Whisper model (recommended)
```bash
# Avoids a fragile at-request-time download (the old SSL-failure source).
mkdir -p /var/www/html/LyricLift/.cache/whisper
# Copy tiny.pt from a machine that already has it, e.g.:
#   rsync -avz ~/.cache/whisper/tiny.pt \
#     root@SERVER:/var/www/html/LyricLift/.cache/whisper/
# The app will otherwise download it on first run (needs working CA certs).
```

### Step 3c: (Optional) YouTube cookies — needed for YouTube on a cloud server
```bash
# YouTube blocks datacenter/VPS IPs with a bot check ("Sign in to confirm you're
# not a bot" / HTTP 429). File uploads and most other sites are unaffected, but
# YouTube URLs need cookies from a logged-in session to work from the server.
#
# 1. In a logged-in browser, export cookies for youtube.com in Netscape format
#    (e.g. a "Get cookies.txt" extension).
# 2. Save the file on the server as:
#      /var/www/html/LyricLift/youtube_cookies.txt   (chown www-data)
#    (or set LYRICLIFT_YTDLP_COOKIES=/path/to/cookies.txt in the service.)
# The app auto-detects the file and passes --cookies to yt-dlp. Cookies expire,
# so they need periodic refresh. Consider a residential proxy for a hands-off fix.
```

### Step 4: Retire the old PHP config (one-time migration)
```bash
# The PHP backend has been removed. If this box previously ran the PHP version,
# drop its old nginx site so it can't shadow the Flask one:
rm -f /etc/nginx/sites-enabled/lyriclift /etc/nginx/sites-available/lyriclift
pkill -f "php.*extract.php" 2>/dev/null || true
```

### Step 5: Setup Directories
```bash
# On the server
mkdir -p /var/www/html/LyricLift/.cache
chown www-data:www-data /var/www/html/LyricLift -R
chmod 755 /var/www/html/LyricLift
chmod 775 /var/www/html/LyricLift/tmp
chmod 755 /var/www/html/LyricLift/.cache
```

### Step 6: Install Systemd Service
```bash
# On the server
cp /var/www/html/LyricLift/lyriclift.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable lyriclift
systemctl start lyriclift
systemctl status lyriclift
```

### Step 7: Update Nginx Configuration
```bash
# On the server — install the Flask vhost and enable it.
cp /var/www/html/LyricLift/lyriclift-flask.conf /etc/nginx/sites-available/lyriclift
ln -sf /etc/nginx/sites-available/lyriclift /etc/nginx/sites-enabled/lyriclift

# Test and reload
nginx -t
systemctl reload nginx
```

### Step 8: Verify
```bash
# Check Flask is running
curl http://127.0.0.1:5000/

# Check systemd service
systemctl status lyriclift

# Check logs
journalctl -u lyriclift -f
```

## Testing

Once deployed, test at: **https://lyriclift.peoplestar.com**

1. Upload a test video
2. Select format
3. Click "Extract Words"
4. Should process much faster than PHP version!

## Troubleshooting

### Flask app not starting
```bash
systemctl status lyriclift
journalctl -u lyriclift -n 50
```

### 502 Bad Gateway from Nginx
```bash
# Check Flask is running on port 5000
netstat -tlnp | grep 5000

# Check Nginx error log
tail -50 /var/log/nginx/lyriclift_error.log
```

### Out of memory during transcription
```bash
# Check memory
free -h

# Increase gunicorn workers in lyriclift.service
# Change: --workers 2
# To: --workers 1
```

## Updating Code

To push updates:
```bash
# From local machine
rsync -avz --exclude='tmp/*' /Users/chipmcallister/Projects/LyricLift/ root@64.227.108.128:/var/www/html/LyricLift/

# On server
systemctl restart lyriclift
```

## Performance Notes

- Flask/Python is **much faster** than PHP for this workload
- Whisper still takes 1-2 minutes for a 2-3 minute video (CPU-bound)
- For truly instant results, you'd need GPU or cloud API (different architecture)
- Current setup: fastest possible with local CPU Whisper

## Monitoring

```bash
# Real-time Flask logs
journalctl -u lyriclift -f

# Check process
ps aux | grep gunicorn

# Check disk usage
du -sh /var/www/html/LyricLift/tmp
