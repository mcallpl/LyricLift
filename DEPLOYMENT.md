# LyricLift Deployment Guide

## Project Status
✅ All files created and tested locally
✅ yt-dlp and Whisper verified on development machine
✅ PHP shell_exec functionality confirmed
✅ tmp directory permissions set (775)

## Local Testing

Before deploying, you can test the app locally:

```bash
cd /Users/chipmcallister/Projects/LyricLift
php -S localhost:8000
```

Then open: http://localhost:8000

## Server Setup (empire-command: 64.227.108.128)

### Step 1: SSH into the Server

```bash
ssh root@64.227.108.128
```

### Step 2: Create Directory and Set Permissions

```bash
mkdir -p /var/www/html/LyricLift/tmp
chmod 775 /var/www/html/LyricLift/tmp
chown www-data:www-data /var/www/html/LyricLift
chown www-data:www-data /var/www/html/LyricLift/tmp
chmod 755 /var/www/html/LyricLift
```

### Step 3: Install Python Dependencies

```bash
pip3 install yt-dlp --break-system-packages
pip3 install openai-whisper --break-system-packages
```

### Step 4: Download Whisper Tiny Model (Optional but Recommended)

If SSL is problematic on the server, pre-download the model:

```bash
export PYTHONHTTPSVERIFY=0
python3 -m whisper --model tiny --language English /dev/null 2>&1 || true
```

This will cache the tiny model locally.

### Step 5: Deploy Application Files

From your local machine, run:

```bash
rsync -avz --delete --exclude='tmp/*' /Users/chipmcallister/Projects/LyricLift/ root@64.227.108.128:/var/www/html/LyricLift/
```

Notes:
- `--exclude='tmp/*'` keeps the empty tmp/ directory but excludes temp file contents
- `--delete` removes files on server that don't exist locally (use with caution)

### Step 6: Set Up Nginx Configuration

On the server:

```bash
# Copy nginx config to sites-available
cp /var/www/html/LyricLift/lyriclift.conf /etc/nginx/sites-available/lyriclift

# Symlink to sites-enabled
ln -s /etc/nginx/sites-available/lyriclift /etc/nginx/sites-enabled/lyriclift

# Test nginx configuration
nginx -t

# Reload nginx
systemctl reload nginx
```

### Step 7: Set Up SSL with Certbot

Ensure DNS A record for lyriclift.peoplestar.com → 64.227.108.128 is created and propagated first.

```bash
certbot --nginx -d lyriclift.peoplestar.com --non-interactive --agree-tos -m mcallpl@gmail.com

# Reload nginx after Certbot
systemctl reload nginx
```

Certbot will automatically update the nginx config to use HTTPS and redirect HTTP to HTTPS.

## Verify Deployment

### Check PHP Files

```bash
ls -la /var/www/html/LyricLift/
```

Should show:
- index.php
- extract.php
- download.php
- assets/
- tmp/
- lyriclift.conf

### Check Nginx

```bash
curl -I http://lyriclift.peoplestar.com
```

Should return 200 OK (or redirect to HTTPS after Certbot setup)

### Test with curl

```bash
curl -v http://localhost/index.php
```

### Check PHP-FPM Socket

```bash
ls -la /var/run/php/php8.2-fpm.sock
```

If it's php8.1 instead, update the nginx config accordingly.

## Troubleshooting

### Whisper Fails with SSL Error

If you see SSL errors, set the environment variable:
```bash
export PYTHONHTTPSVERIFY=0
python3 -m whisper ...
```

Or modify extract.php to set it in the command (already done).

### Permission Denied on tmp/

```bash
chmod 775 /var/www/html/LyricLift/tmp
chown www-data:www-data /var/www/html/LyricLift/tmp
```

### Nginx Returns 502 Bad Gateway

- Check PHP-FPM is running: `systemctl status php8.2-fpm`
- Verify socket path in nginx config matches actual socket path
- Check nginx error log: `tail -f /var/log/nginx/lyriclift_error.log`

### Whisper Takes Too Long

The `fastcgi_read_timeout 300` in nginx config allows up to 5 minutes for processing.
Increase if needed, but note that very long files may need even more time.

### File Upload Fails

- Check `client_max_body_size 100M` is set in nginx (allows up to 100MB files)
- Verify `/tmp` on the system has free space for PHP temporary uploads
- Check PHP `upload_max_filesize` and `post_max_size` are set high enough:
  ```bash
  php -i | grep -E "upload_max_filesize|post_max_size"
  ```

## Monitoring

### View Recent Logs

```bash
# Nginx access log
tail -f /var/log/nginx/lyriclift_access.log

# Nginx error log
tail -f /var/log/nginx/lyriclift_error.log

# PHP-FPM log (if configured)
tail -f /var/log/php8.2-fpm.log
```

### Monitor tmp Directory Size

```bash
du -sh /var/www/html/LyricLift/tmp
```

Files older than 1 hour are auto-deleted by extract.php.

## Updating the Application

To push updates:

```bash
rsync -avz --exclude='tmp/*' /Users/chipmcallister/Projects/LyricLift/ root@64.227.108.128:/var/www/html/LyricLift/
systemctl reload nginx
```

No need to reload PHP-FPM for static file or PHP changes (unless modifying php.ini).

## Rollback

If something goes wrong, you can revert to the previous version by keeping backups:

```bash
# Backup before deploy
scp -r root@64.227.108.128:/var/www/html/LyricLift LyricLift_backup_$(date +%Y%m%d_%H%M%S)

# Restore from backup
rsync -avz LyricLift_backup_YYYYMMDD_HHMMSS/ root@64.227.108.128:/var/www/html/LyricLift/
```

## Quick Deploy Checklist

- [ ] DNS A record created (lyriclift.peoplestar.com → 64.227.108.128)
- [ ] Server directories created with correct permissions
- [ ] yt-dlp and whisper installed on server
- [ ] Application files deployed via rsync
- [ ] Nginx config copied and symlinked
- [ ] Nginx test passes (`nginx -t`)
- [ ] Nginx reloaded
- [ ] Certbot SSL certificate provisioned
- [ ] HTTPS working (https://lyriclift.peoplestar.com)
- [ ] Test URL extraction with public YouTube video
- [ ] Test file upload with sample audio file
- [ ] Verify download functionality

## Support

For issues:
1. Check nginx logs: `/var/log/nginx/lyriclift_error.log`
2. Test PHP execution: `php -r "phpinfo();"`
3. Test yt-dlp: `python3 -m yt_dlp --version`
4. Test Whisper: `python3 -m whisper --help`
