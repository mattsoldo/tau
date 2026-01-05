# Safe Deployment Guide

This guide explains how to safely deploy updates to your Tau Lighting Control system with automatic backups and rollback capability.

## Overview

The `deploy-safe.sh` script provides enhanced safety features:

- ✅ **Automatic Backups**: Creates backups of code and database before every deployment
- ✅ **Automatic Rollback**: Rolls back automatically if deployment fails
- ✅ **Manual Rollback**: Easy rollback to any previous backup
- ✅ **Health Checks**: Verifies services are working after deployment
- ✅ **Backup Management**: Automatically keeps last 5 backups, removes older ones

## Quick Start

### 1. Deploy with Safety

```bash
# SSH to your Raspberry Pi
ssh pi@your-pi-ip

# Navigate to Tau directory
cd /opt/tau-daemon

# Run safe deployment
sudo ./deploy-safe.sh
```

This will:
1. Create automatic backup of current state
2. Pull latest code from git
3. Update dependencies
4. Run database migrations
5. Rebuild frontend
6. Restart services
7. Verify everything is working
8. **If anything fails**: Automatically rollback to backup

### 2. List Available Backups

```bash
sudo ./deploy-safe.sh --list-backups
```

Example output:
```
Available Backups
=========================================

ID                  COMMIT    DATE/TIME           STATUS
─────────────────────────────────────────────────────────────────
20260105-143022     3401b00   2026-01-05 14:30:22 ✓ Valid
20260105-120033     0625411   2026-01-05 12:00:33 ✓ Valid
20260104-180015     61c2afa   2026-01-04 18:00:15 ✓ Valid

Latest backup: 20260105-143022
```

### 3. Manual Rollback

```bash
# Rollback to most recent backup
sudo ./deploy-safe.sh --rollback

# Rollback to specific backup
sudo ./deploy-safe.sh --rollback-to 20260105-120033
```

## Command Reference

```bash
# Normal deployment (with automatic backup)
sudo ./deploy-safe.sh

# Force rebuild even if already up to date
sudo ./deploy-safe.sh --force

# List all available backups
sudo ./deploy-safe.sh --list-backups

# Rollback to latest backup
sudo ./deploy-safe.sh --rollback

# Rollback to specific backup ID
sudo ./deploy-safe.sh --rollback-to 20260105-143022

# Show help
sudo ./deploy-safe.sh --help
```

## What Gets Backed Up

### Code Backup
- All source code in `/opt/tau-daemon`
- Configuration files
- Git history
- **Excludes**: Dependencies (node_modules, .venv), build artifacts (.next, out)

### Database Backup
- Full PostgreSQL database dump
- All tables, data, and schema
- Can be restored independently

## Backup Storage

- **Location**: `/opt/tau-backups/`
- **Retention**: Last 5 backups automatically kept
- **Naming**: `backup-YYYYMMDD-HHMMSS`

### Backup Files
```
/opt/tau-backups/
├── code-20260105-143022.tar.gz     # Code backup
├── db-20260105-143022.sql          # Database backup
├── backup-20260105-143022.meta     # Metadata (commit hash, timestamp)
└── latest-backup.meta              # Symlink to latest backup
```

## Deployment Workflow

```
┌─────────────────────────────────────┐
│  1. Create Backup                   │
│     - Save code snapshot            │
│     - Save database dump            │
│     - Record git commit             │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  2. Run Deployment                  │
│     - Pull latest code              │
│     - Update dependencies           │
│     - Run migrations                │
│     - Build frontend                │
│     - Restart services              │
└─────────────┬───────────────────────┘
              │
              ▼
        ┌─────┴─────┐
        │  Success? │
        └─────┬─────┘
              │
      ┌───────┴───────┐
      │               │
     Yes             No
      │               │
      ▼               ▼
┌──────────┐    ┌──────────────────┐
│ Complete │    │ Auto Rollback    │
│          │    │ - Restore code   │
│          │    │ - Restore DB     │
│          │    │ - Restart        │
└──────────┘    └──────────────────┘
```

## Troubleshooting

### Deployment Failed - What Happens?

The script will **automatically rollback** if:
- Git pull fails
- Dependencies fail to install
- Database migration fails
- Frontend build fails
- Services fail to start
- Health checks fail

You'll see:
```
❌ DEPLOYMENT FAILED
⚠ Initiating automatic rollback...
```

### Manual Recovery

If you need to manually recover:

```bash
# 1. Check what backups exist
sudo ./deploy-safe.sh --list-backups

# 2. Rollback to specific backup
sudo ./deploy-safe.sh --rollback-to 20260105-120033

# 3. Verify services
sudo systemctl status tau-daemon
curl http://localhost:8000/health
```

### Check Logs After Rollback

```bash
# View daemon logs
sudo journalctl -u tau-daemon -n 100 --no-pager

# View deployment logs
ls -lt /var/log/tau/update_*.log
cat /var/log/tau/update_LATEST.log
```

## Best Practices

### Before Major Updates

1. **Verify Current State**
   ```bash
   sudo systemctl status tau-daemon
   curl http://localhost:8000/health
   ```

2. **Note Current Commit**
   ```bash
   cd /opt/tau-daemon
   git log --oneline -1
   ```

3. **Check Disk Space**
   ```bash
   df -h /opt
   ```
   - Need at least 500MB free for backups

### During Deployment

1. **Monitor in Real-Time**
   ```bash
   # In one terminal: run deployment
   sudo ./deploy-safe.sh

   # In another terminal: watch logs
   sudo journalctl -u tau-daemon -f
   ```

2. **Don't Interrupt**
   - Let the script complete
   - If it fails, auto-rollback will handle it

### After Deployment

1. **Verify Services**
   ```bash
   sudo systemctl status tau-daemon nginx postgresql olad
   ```

2. **Test Basic Functions**
   - Open web UI: `http://your-pi-ip/`
   - Test light control
   - Check API: `http://your-pi-ip/api/health`

3. **Keep Backup for 24 Hours**
   - Don't clean backups immediately
   - Monitor for issues
   - Can rollback if problems appear later

## Disk Space Management

Backups are automatically managed, but you can manually clean if needed:

```bash
# Check backup sizes
du -h /opt/tau-backups/*

# Remove specific old backup
sudo rm /opt/tau-backups/code-20260104-120033.tar.gz
sudo rm /opt/tau-backups/db-20260104-120033.sql
sudo rm /opt/tau-backups/backup-20260104-120033.meta

# Or remove all backups (dangerous!)
# sudo rm -rf /opt/tau-backups/*
```

## Emergency Procedures

### Complete System Failure

If the system is completely broken:

```bash
# 1. Boot Pi to recovery mode or SSH in
ssh pi@your-pi-ip

# 2. List backups
sudo ./deploy-safe.sh --list-backups

# 3. Rollback to known-good backup
sudo ./deploy-safe.sh --rollback-to 20260105-120033

# 4. If rollback script is broken, manual restore:
cd /opt
sudo tar -xzf /opt/tau-backups/code-20260105-120033.tar.gz
sudo -u postgres dropdb tau_lighting
sudo -u postgres createdb tau_lighting
sudo -u postgres psql tau_lighting < /opt/tau-backups/db-20260105-120033.sql
sudo systemctl restart tau-daemon nginx
```

### Database Only Restore

```bash
# Restore just the database without touching code
sudo -u postgres dropdb tau_lighting
sudo -u postgres createdb tau_lighting
sudo -u postgres psql tau_lighting < /opt/tau-backups/db-20260105-120033.sql
sudo systemctl restart tau-daemon
```

### Code Only Restore

```bash
# Restore just code without touching database
sudo systemctl stop tau-daemon
cd /opt
sudo rm -rf tau-daemon
sudo tar -xzf /opt/tau-backups/code-20260105-120033.tar.gz
sudo chown -R tau:tau tau-daemon
sudo systemctl start tau-daemon
```

## Comparison: deploy.sh vs deploy-safe.sh

| Feature | deploy.sh | deploy-safe.sh |
|---------|-----------|----------------|
| Automatic backups | ❌ No | ✅ Yes |
| Automatic rollback | ❌ No | ✅ Yes |
| Manual rollback | ❌ Manual | ✅ One command |
| Health checks | ✅ Yes | ✅ Yes |
| Backup management | ❌ No | ✅ Auto-cleanup |
| List backups | ❌ No | ✅ Yes |
| Safety rating | Medium | High |

## When to Use Each Script

### Use `deploy.sh` when:
- Quick updates with minimal changes
- Testing in development
- You've already created backups manually

### Use `deploy-safe.sh` when:
- **Deploying this PR** (5000+ line change!)
- Major version updates
- Production deployments
- Any deployment you're nervous about
- First deployment to a new Pi

## FAQ

**Q: How much disk space do backups use?**
A: Approximately 50-100MB per backup (code ~30MB, database ~20MB, compressed)

**Q: Can I keep more than 5 backups?**
A: Yes, edit `MAX_BACKUPS=5` in the script to increase retention

**Q: What if automatic rollback fails?**
A: The script will show error messages. Use manual recovery procedures above.

**Q: Do I need deploy-safe.sh for every deployment?**
A: Recommended for production. Optional for dev/test environments.

**Q: Can I run this on macOS/Linux dev machine?**
A: No, designed for Raspberry Pi only. It needs systemctl and tau-daemon installation.

**Q: Will this work with the new software update system?**
A: Yes! And it's especially important for this update since it's adding the OTA update feature.
