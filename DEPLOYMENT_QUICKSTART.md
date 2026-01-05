# 🚀 Deployment Quick Start

## For This PR (Software Update System)

This is a **major update** (5,000+ lines changed). Use the safe deployment script.

### On Your Raspberry Pi:

```bash
# 1. SSH to Pi
ssh pi@your-pi-ip

# 2. Navigate to tau directory
cd /opt/tau-daemon

# 3. Pull the deploy-safe.sh script
git fetch origin
git checkout origin/claude/implement-software-update-160r1 -- deploy-safe.sh
chmod +x deploy-safe.sh

# 4. Run safe deployment
sudo ./deploy-safe.sh
```

**The script will:**
- ✅ Automatically backup current system
- ✅ Deploy the update
- ✅ Verify it works
- ✅ Auto-rollback if anything fails

### If Something Goes Wrong:

```bash
# Rollback to backup
sudo ./deploy-safe.sh --rollback
```

That's it! Full documentation: [docs/SAFE_DEPLOYMENT.md](docs/SAFE_DEPLOYMENT.md)

---

## Regular Deployments (After This PR)

Once this PR is merged and deployed, you can use the new **built-in software update UI**:

1. Open web UI: `http://your-pi-ip/`
2. Go to **Settings** → **Software Updates**
3. Click **"Check for Updates"**
4. Click **"Apply Update"**

The system will:
- Download update from GitHub Releases
- Create automatic backup
- Install update
- Auto-rollback if it fails

---

## Emergency Contacts

**If deployment fails and rollback doesn't work:**

1. List available backups:
   ```bash
   sudo ./deploy-safe.sh --list-backups
   ```

2. Rollback to specific backup:
   ```bash
   sudo ./deploy-safe.sh --rollback-to BACKUP_ID
   ```

3. Check logs:
   ```bash
   sudo journalctl -u tau-daemon -n 100
   ```

4. Contact: *[Your contact info here]*

---

## Pre-Deployment Checklist

- [ ] Verified current system is working: `curl http://localhost:8000/health`
- [ ] Checked disk space: `df -h` (need 500MB+ free)
- [ ] Planned deployment during low-usage time
- [ ] Have backup Pi access (keyboard/monitor) if SSH breaks
- [ ] Read full guide: [docs/SAFE_DEPLOYMENT.md](docs/SAFE_DEPLOYMENT.md)

---

## Monitoring During Deployment

Open a second SSH session and watch logs:
```bash
sudo journalctl -u tau-daemon -f
```

This lets you see what's happening in real-time.
