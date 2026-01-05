# Software Update System Specification

## Lighting Control System — OTA Update Architecture

**Version:** 1.0  
**Target Platform:** Raspberry Pi (Custom OS Distribution)  
**Update Source:** GitHub Releases

---

## 1. Executive Summary

This specification defines an over-the-air (OTA) update system for the lighting control software deployed on Raspberry Pi devices. The system prioritizes reliability, atomic updates, and safe rollback capabilities—critical requirements for embedded systems controlling physical lighting infrastructure.

---

## 2. Design Decision: GitHub Releases vs. Git State

### Recommendation: Use GitHub Releases

| Factor | Releases | Git State (branch tracking) |
|--------|----------|----------------------------|
| **Stability** | Explicit production-ready markers | Risk of deploying untested commits |
| **Versioning** | Semantic versioning (v1.2.3) | Commit hashes only |
| **Changelog** | Built-in release notes | Must parse commit messages |
| **Reproducibility** | Tags are immutable | Branch HEAD changes constantly |
| **Rollback** | Clear version targets | Complex state management |
| **Pre-built assets** | Can attach binaries/packages | Must build on device or fetch raw |
| **API support** | First-class GitHub API | Requires more git operations |

### Rationale

For an embedded lighting controller, **predictability and reliability outweigh bleeding-edge updates**. A failed update to a lighting system could leave a space in darkness. GitHub Releases provide:

1. **Human-verified checkpoints** — Someone explicitly marked this as ready
2. **Clear rollback targets** — "Roll back to v2.1.0" is unambiguous
3. **Changelog transparency** — Users see exactly what changed before updating
4. **Asset flexibility** — Attach pre-built `.deb` packages, reducing on-device build requirements

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi Device                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Update     │    │   Version    │    │   Rollback   │       │
│  │   Daemon     │◄──►│   Manager    │◄──►│   Manager    │       │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘       │
│         │                   │                                    │
│         ▼                   ▼                                    │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │   GitHub     │    │   Local      │                           │
│  │   Client     │    │   State DB   │                           │
│  └──────┬───────┘    └──────────────┘                           │
│         │                                                        │
└─────────┼────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────┐
│   GitHub Releases   │
│   API / Assets      │
└─────────────────────┘
```

### Components

| Component | Responsibility |
|-----------|----------------|
| **Update Daemon** | Scheduled checks, download orchestration |
| **Version Manager** | Current version tracking, comparison logic |
| **Rollback Manager** | Backup creation, restoration, cleanup |
| **GitHub Client** | API communication, asset downloads |
| **Local State DB** | SQLite store for versions, history, config |

---

## 4. Data Model

### 4.1 Local State Database

```sql
-- Current installation state
CREATE TABLE installation (
    id INTEGER PRIMARY KEY DEFAULT 1,
    current_version TEXT NOT NULL,
    installed_at TIMESTAMP NOT NULL,
    install_method TEXT CHECK(install_method IN ('fresh', 'update', 'rollback')),
    commit_sha TEXT,
    CHECK (id = 1)  -- Singleton table
);

-- Version history for rollback
CREATE TABLE version_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    installed_at TIMESTAMP NOT NULL,
    uninstalled_at TIMESTAMP,
    backup_path TEXT,
    backup_valid BOOLEAN DEFAULT TRUE,
    release_notes TEXT,
    commit_sha TEXT
);

-- Available releases cache
CREATE TABLE available_releases (
    version TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL,
    published_at TIMESTAMP NOT NULL,
    release_notes TEXT,
    asset_url TEXT,
    asset_checksum TEXT,
    prerelease BOOLEAN DEFAULT FALSE,
    checked_at TIMESTAMP NOT NULL
);

-- Update check log
CREATE TABLE update_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TIMESTAMP NOT NULL,
    source TEXT CHECK(source IN ('manual', 'scheduled')),
    result TEXT CHECK(result IN ('up_to_date', 'update_available', 'error')),
    latest_version TEXT,
    error_message TEXT
);

-- Configuration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Default configuration
INSERT INTO config (key, value) VALUES
    ('auto_check_enabled', 'true'),
    ('check_interval_hours', '24'),
    ('include_prereleases', 'false'),
    ('max_backups', '3'),
    ('github_repo', 'your-username/lighting-control'),
    ('update_channel', 'stable');
```

### 4.2 GitHub Release Structure (Expected)

Each GitHub release should follow this convention:

```
Tag: v1.2.3
Title: Version 1.2.3 — Descriptive Name

Assets:
  - lighting-control-1.2.3-armhf.deb    (Raspberry Pi package)
  - lighting-control-1.2.3-armhf.deb.sha256
  - CHANGELOG.md                         (Optional, inline preferred)

Body (Release Notes):
  ## What's New
  - Added DALI DT8 Tc color temperature presets
  - Improved DMX512 packet timing accuracy
  
  ## Bug Fixes
  - Fixed OLA reconnection after USB adapter hot-plug
  - Resolved memory leak in long-running scene sequences
  
  ## Breaking Changes
  - None
  
  ## Upgrade Notes
  - Run database migration: `lighting-ctl migrate`
```

---

## 5. Core Workflows

### 5.1 Check for Updates

```
┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│ Trigger │────►│ Fetch       │────►│ Compare    │────►│ Notify   │
│ (manual/│     │ Releases    │     │ Versions   │     │ User/Log │
│ scheduled)    │ from GitHub │     │            │     │          │
└─────────┘     └─────────────┘     └────────────┘     └──────────┘
```

**Algorithm:**

```python
def check_for_updates(source: str = 'manual') -> UpdateCheckResult:
    try:
        # 1. Fetch releases from GitHub API
        releases = github_client.get_releases(
            repo=config['github_repo'],
            include_prereleases=config['include_prereleases']
        )
        
        # 2. Filter to valid releases (has required assets)
        valid_releases = [r for r in releases if has_valid_assets(r)]
        
        # 3. Cache releases locally
        cache_releases(valid_releases)
        
        # 4. Get current version
        current = get_current_version()
        
        # 5. Find latest applicable release
        latest = get_latest_release(valid_releases)
        
        # 6. Compare using semantic versioning
        if semver.compare(latest.version, current) > 0:
            result = UpdateCheckResult(
                status='update_available',
                current_version=current,
                latest_version=latest.version,
                release_notes=latest.body,
                published_at=latest.published_at
            )
        else:
            result = UpdateCheckResult(status='up_to_date')
        
        # 7. Log check
        log_update_check(source, result)
        
        return result
        
    except GitHubAPIError as e:
        log_update_check(source, 'error', str(e))
        raise
```

### 5.2 Apply Update

```
┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
│Download│──►│Verify  │──►│Backup  │──►│Stop    │──►│Install │──►│Start   │
│Asset   │   │Checksum│   │Current │   │Services│   │New     │   │Services│
└────────┘   └────────┘   └────────┘   └────────┘   └────────┘   └────────┘
                                            │                         │
                                            │      ┌────────┐         │
                                            └─────►│Rollback│◄────────┘
                                              fail │if fail │    fail
                                                   └────────┘
```

**Algorithm:**

```python
def apply_update(target_version: str) -> UpdateResult:
    release = get_cached_release(target_version)
    current_version = get_current_version()
    
    # 1. Download asset
    asset_path = download_asset(
        url=release.asset_url,
        expected_checksum=release.asset_checksum
    )
    
    # 2. Verify checksum
    if not verify_checksum(asset_path, release.asset_checksum):
        raise ChecksumMismatchError()
    
    # 3. Create backup of current installation
    backup_path = create_backup(current_version)
    
    try:
        # 4. Stop lighting services
        stop_services(['lighting-control', 'lighting-web'])
        
        # 5. Install new version
        install_package(asset_path)
        
        # 6. Run migrations if needed
        run_post_install_hooks(target_version)
        
        # 7. Start services
        start_services(['lighting-control', 'lighting-web'])
        
        # 8. Verify installation
        if not verify_installation(target_version):
            raise InstallationVerificationError()
        
        # 9. Update state
        update_installation_record(
            version=target_version,
            method='update',
            commit_sha=release.commit_sha
        )
        
        # 10. Prune old backups
        prune_old_backups(keep=config['max_backups'])
        
        return UpdateResult(success=True, version=target_version)
        
    except Exception as e:
        # Automatic rollback on failure
        rollback_to_backup(backup_path)
        start_services(['lighting-control', 'lighting-web'])
        raise UpdateFailedError(f"Update failed, rolled back: {e}")
```

### 5.3 Rollback

```python
def rollback(target_version: str = None) -> RollbackResult:
    """
    Roll back to a specific version or the previous version.
    """
    current_version = get_current_version()
    
    # 1. Determine target
    if target_version is None:
        # Get most recent backup
        backup = get_most_recent_backup()
        target_version = backup.version
    else:
        backup = get_backup_for_version(target_version)
    
    if not backup or not backup.backup_valid:
        raise NoValidBackupError(target_version)
    
    # 2. Stop services
    stop_services(['lighting-control', 'lighting-web'])
    
    try:
        # 3. Restore from backup
        restore_from_backup(backup.backup_path)
        
        # 4. Start services
        start_services(['lighting-control', 'lighting-web'])
        
        # 5. Verify
        if not verify_installation(target_version):
            raise RollbackVerificationError()
        
        # 6. Update state
        update_installation_record(
            version=target_version,
            method='rollback'
        )
        
        return RollbackResult(
            success=True,
            from_version=current_version,
            to_version=target_version
        )
        
    except Exception as e:
        # This is bad - manual intervention needed
        log_critical(f"Rollback failed: {e}")
        raise RollbackFailedError("Manual intervention required")
```

---

## 6. Scheduled Update Checks

### Systemd Timer Configuration

```ini
# /etc/systemd/system/lighting-update-check.service
[Unit]
Description=Lighting Control Update Check
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/lighting-ctl update check --source=scheduled
User=lighting
StandardOutput=journal
StandardError=journal
```

```ini
# /etc/systemd/system/lighting-update-check.timer
[Unit]
Description=Daily check for lighting control updates

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
```

### Notification Behavior

When a scheduled check finds an update:

1. **Log to system journal** — Always
2. **Update local state** — Mark update available in DB
3. **Web UI indicator** — Show badge/banner on next page load
4. **Optional webhook** — POST to configured URL (for fleet management)

**No automatic installation** — Updates require explicit user action.

---

## 7. User Interface Integration

### 7.1 Web UI Components

```
┌─────────────────────────────────────────────────────────────────┐
│  System Settings → Software Updates                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Current Version: v2.1.0                                        │
│  Installed: 2025-01-03 14:32 UTC                                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ✨ Update Available: v2.2.0                                 ││
│  │                                                             ││
│  │ Published: 2025-01-05 09:00 UTC                             ││
│  │                                                             ││
│  │ ## What's New                                               ││
│  │ - DALI DT8 color temperature presets                        ││
│  │ - Improved DMX timing accuracy                              ││
│  │                                                             ││
│  │ ## Bug Fixes                                                ││
│  │ - Fixed OLA reconnection issue                              ││
│  │                                                             ││
│  │ [View Full Release Notes]  [Install Update]                 ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Version History                         [Check for Updates]    │
│                                                                  │
│  │ v2.1.0  │ Installed │ 2025-01-03 │ Current        │         │
│  │ v2.0.1  │ Backup    │ 2024-12-15 │ [Rollback]     │         │
│  │ v2.0.0  │ Backup    │ 2024-12-01 │ [Rollback]     │         │
│  │ v1.9.2  │ Expired   │ 2024-11-20 │ —              │         │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Settings                                                        │
│  ┌──────────────────────────────┬────────────────────────────┐  │
│  │ Automatic update checks      │ [✓] Enabled                │  │
│  │ Check frequency              │ [Daily ▼]                  │  │
│  │ Include pre-releases         │ [ ] Disabled               │  │
│  │ Backups to keep              │ [3 ▼]                      │  │
│  └──────────────────────────────┴────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 CLI Interface

```bash
# Check for updates
$ lighting-ctl update check
Current version: v2.1.0
Latest version:  v2.2.0 (published 2025-01-05)
Status: Update available

# Show release notes
$ lighting-ctl update show v2.2.0
Version: v2.2.0
Published: 2025-01-05 09:00 UTC

## What's New
- DALI DT8 color temperature presets
- Improved DMX timing accuracy

## Bug Fixes
- Fixed OLA reconnection issue

# Apply update
$ lighting-ctl update apply v2.2.0
Downloading lighting-control-2.2.0-armhf.deb... done
Verifying checksum... OK
Creating backup of v2.1.0... done
Stopping services... done
Installing v2.2.0... done
Starting services... done
Verifying installation... OK

Update complete: v2.1.0 → v2.2.0

# Rollback
$ lighting-ctl update rollback
Available backups:
  1. v2.1.0 (2025-01-03)
  2. v2.0.1 (2024-12-15)

Rollback to [1]: 1
Stopping services... done
Restoring v2.1.0... done
Starting services... done

Rollback complete: v2.2.0 → v2.1.0

# List history
$ lighting-ctl update history
VERSION   STATUS     INSTALLED            NOTES
v2.2.0    current    2025-01-05 10:15    —
v2.1.0    backup     2025-01-03 14:32    Rollback available
v2.0.1    backup     2024-12-15 09:00    Rollback available
v2.0.0    expired    2024-12-01 11:20    No backup
```

---

## 8. Backup Strategy

### What Gets Backed Up

```
/var/lib/lighting-control/
├── backup/
│   ├── v2.1.0_20250103T143200Z/
│   │   ├── manifest.json           # Backup metadata
│   │   ├── app/                    # Application files
│   │   ├── config/                 # Configuration
│   │   ├── database.sqlite         # State database
│   │   └── systemd/                # Service files
│   └── v2.0.1_20241215T090000Z/
│       └── ...
```

### Backup Manifest

```json
{
  "version": "2.1.0",
  "created_at": "2025-01-03T14:32:00Z",
  "commit_sha": "a1b2c3d4e5f6",
  "files": [
    {"path": "app/main.py", "checksum": "sha256:..."},
    {"path": "config/settings.yaml", "checksum": "sha256:..."}
  ],
  "database_schema_version": 15,
  "services": ["lighting-control", "lighting-web"]
}
```

### Retention Policy

- Keep the **N most recent backups** (configurable, default 3)
- Never delete a backup while update/rollback is in progress
- Backups older than retention limit are pruned after successful updates
- Minimum 500MB free space required before creating backup

---

## 9. Security Considerations

### Asset Verification

1. **HTTPS only** — All GitHub API and asset downloads over TLS
2. **Checksum verification** — SHA256 hash checked before installation
3. **Signature verification (optional enhancement)** — GPG-signed releases

```bash
# In release workflow, sign the asset
gpg --armor --detach-sign lighting-control-2.2.0-armhf.deb

# On device, verify before install
gpg --verify lighting-control-2.2.0-armhf.deb.asc
```

### GitHub API Authentication

```python
# Use token for higher rate limits (optional, works without for public repos)
headers = {}
if github_token := config.get('github_token'):
    headers['Authorization'] = f'token {github_token}'

response = requests.get(
    f'https://api.github.com/repos/{repo}/releases',
    headers=headers
)
```

### Permissions

- Update daemon runs as dedicated `lighting` user
- Installation step requires elevated privileges (via polkit or sudo)
- Web UI update actions authenticated against local user system

---

## 10. Error Handling

### Error Categories

| Category | Example | Response |
|----------|---------|----------|
| **Network** | GitHub unreachable | Retry with backoff, log, continue running |
| **Download** | Partial download, timeout | Retry up to 3 times, then fail |
| **Checksum** | Hash mismatch | Abort, delete asset, notify user |
| **Install** | Package conflict | Rollback, notify user |
| **Post-install** | Migration failure | Rollback, notify user |
| **Service** | Won't start after update | Rollback, notify user |

### Automatic Recovery

```python
class UpdateStateMachine:
    states = [
        'idle',
        'checking',
        'downloading', 
        'verifying',
        'backing_up',
        'stopping_services',
        'installing',
        'migrating',
        'starting_services',
        'verifying_install',
        'complete',
        'failed',
        'rolling_back'
    ]
    
    def recover_from_interrupted(self):
        """Called on daemon startup to handle interrupted updates."""
        state = self.load_persisted_state()
        
        if state in ['downloading', 'verifying', 'backing_up']:
            # Safe to restart from beginning
            self.cleanup_partial_download()
            self.transition('idle')
            
        elif state in ['stopping_services', 'installing', 'migrating']:
            # Mid-installation - attempt rollback
            self.transition('rolling_back')
            self.execute_rollback()
            
        elif state == 'starting_services':
            # Try to start services
            if self.start_services():
                self.transition('complete')
            else:
                self.transition('rolling_back')
                self.execute_rollback()
```

---

## 11. GitHub Release Workflow

### Recommended Release Process

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build Debian Package
        run: |
          ./scripts/build-deb.sh
          
      - name: Generate Checksum
        run: |
          sha256sum dist/*.deb > dist/checksums.sha256
          
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            dist/*.deb
            dist/checksums.sha256
          generate_release_notes: true
          draft: true  # Review before publishing
```

### Version Tagging Convention

```bash
# Stable releases
git tag -a v2.2.0 -m "Release 2.2.0: DALI DT8 support"
git push origin v2.2.0

# Pre-releases (for testing)
git tag -a v2.3.0-beta.1 -m "Beta: New scene engine"
git push origin v2.3.0-beta.1
```

---

## 12. Configuration Reference

```yaml
# /etc/lighting-control/update.yaml

# Update source
github:
  repository: "your-username/lighting-control"
  token: null  # Optional, for private repos or higher rate limits

# Behavior
updates:
  auto_check: true
  check_interval_hours: 24
  check_time: "03:00"  # Local time for scheduled checks
  include_prereleases: false

# Backups
backups:
  enabled: true
  max_count: 3
  location: "/var/lib/lighting-control/backup"
  min_free_space_mb: 500

# Notifications
notifications:
  webhook_url: null  # Optional: POST update events here
  
# Advanced
advanced:
  download_timeout_seconds: 300
  verify_after_install: true
  rollback_on_service_failure: true
```

---

## 13. Testing Strategy

### Update System Tests

1. **Unit tests** — Version comparison, checksum verification, state machine
2. **Integration tests** — Mock GitHub API, full update cycle
3. **Hardware-in-loop tests** — Actual Raspberry Pi update/rollback cycles

### Test Scenarios

| Scenario | Expected Outcome |
|----------|------------------|
| Normal update | Install succeeds, services running |
| Network failure during download | Retry, eventually fail gracefully |
| Checksum mismatch | Abort, notify user, no changes |
| Service won't start after update | Automatic rollback |
| Power loss during install | Recovery on next boot |
| Rollback to unavailable version | Clear error message |
| Disk full during backup | Abort before installation |

---

## 14. Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
- [ ] Database schema and migrations
- [ ] GitHub API client with caching
- [ ] Version comparison logic (semver)
- [ ] Basic CLI: `check`, `show`

### Phase 2: Update Mechanism (Week 2-3)
- [ ] Asset download with resume support
- [ ] Checksum verification
- [ ] Backup creation and restoration
- [ ] Package installation hooks
- [ ] CLI: `apply`, `rollback`

### Phase 3: Automation (Week 3-4)
- [ ] Systemd timer for scheduled checks
- [ ] State machine for interrupted recovery
- [ ] Service management integration
- [ ] CLI: `history`, `config`

### Phase 4: UI Integration (Week 4-5)
- [ ] Web UI update settings page
- [ ] Update available notifications
- [ ] Progress indication during updates
- [ ] Release notes rendering

### Phase 5: Hardening (Week 5-6)
- [ ] Error handling edge cases
- [ ] Rate limiting and backoff
- [ ] Disk space checks
- [ ] Comprehensive logging
- [ ] Documentation

---

## 15. Future Enhancements

- **Delta updates** — Only download changed files (reduces bandwidth)
- **A/B partition scheme** — Boot into new version, instant rollback via bootloader
- **Fleet management** — Central dashboard for multiple devices
- **Staged rollouts** — Percentage-based deployment for testing
- **Signed releases** — GPG signature verification for supply chain security

---

## Appendix A: API Reference

### GitHub Releases API

```
GET /repos/{owner}/{repo}/releases
GET /repos/{owner}/{repo}/releases/latest
GET /repos/{owner}/{repo}/releases/tags/{tag}
```

### Internal Update Service API

```
GET  /api/system/update/status        # Current version + available update
POST /api/system/update/check         # Trigger manual check
POST /api/system/update/apply         # Apply specific version
POST /api/system/update/rollback      # Rollback to version
GET  /api/system/update/history       # Version history
GET  /api/system/update/releases      # Cached available releases
```

---

## Appendix B: State Diagram

```
                    ┌──────────────────────────┐
                    │                          │
                    ▼                          │
┌─────────┐    ┌─────────┐    ┌─────────┐     │
│  IDLE   │───►│CHECKING │───►│AVAILABLE│─────┘
└─────────┘    └─────────┘    └────┬────┘  (no update)
     ▲                             │
     │                             ▼ (user triggers)
     │                        ┌─────────┐
     │                        │DOWNLOAD │
     │                        └────┬────┘
     │                             │
     │                             ▼
     │                        ┌─────────┐
     │                        │ VERIFY  │
     │                        └────┬────┘
     │                             │
     │                             ▼
     │                        ┌─────────┐
     │                        │ BACKUP  │
     │                        └────┬────┘
     │                             │
     │         ┌───────────────────┼───────────────────┐
     │         │                   ▼                   │
     │         │              ┌─────────┐              │
     │         │              │ INSTALL │              │
     │         │              └────┬────┘              │
     │         │                   │                   │
     │         │      success      ▼       failure     │
     │         │              ┌─────────┐              │
     │         │              │ VERIFY  │──────────────┤
     │         │              │ INSTALL │              │
     │         │              └────┬────┘              │
     │         │                   │                   │
     │         │                   ▼                   ▼
     │         │              ┌─────────┐        ┌──────────┐
     │         │              │COMPLETE │        │ ROLLBACK │
     │         │              └────┬────┘        └────┬─────┘
     │         │                   │                  │
     └─────────┴───────────────────┴──────────────────┘
```