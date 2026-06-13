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

### Step 3: Install Python Dependencies
```bash
# On the server
cd /var/www/html/LyricLift
pip3 install -r requirements.txt --break-system-packages
```

### Step 4: Stop Old PHP Server
```bash
# Kill any old PHP processes for LyricLift
pkill -f "php.*extract.php"
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
# On the server
cp /var/www/html/LyricLift/lyriclift-flask.conf /etc/nginx/sites-available/lyriclift
# Replace old config
rm /etc/nginx/sites-available/lyriclift  # Old PHP version
ln -s /etc/nginx/sites-available/lyriclift.php /etc/nginx/sites-enabled/lyriclift

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
