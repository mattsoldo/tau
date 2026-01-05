#!/bin/bash -e
# Stage 4, Step 07: Enable services and final configuration

echo "=== Enabling services ==="

on_chroot << EOF
# Enable first-boot service
systemctl enable tau-firstboot.service

# Enable OLA daemon
systemctl enable olad.service

# Configure hostname
echo "tau-controller" > /etc/hostname

# Update /etc/hosts
sed -i 's/raspberrypi/tau-controller/g' /etc/hosts

# Create MOTD (Message of the Day)
cat > /etc/motd << 'MOTD'

  ████████╗ █████╗ ██╗   ██╗
  ╚══██╔══╝██╔══██╗██║   ██║
     ██║   ███████║██║   ██║
     ██║   ██╔══██║██║   ██║
     ██║   ██║  ██║╚██████╔╝
     ╚═╝   ╚═╝  ╚═╝ ╚═════╝

  Tau Lighting Control System

  Commands:
    tau-status    - Show service status
    tau-logs      - View daemon logs
    tau-restart   - Restart all services

  Web Interface: http://tau-controller.local/

MOTD

# Create convenience scripts
cat > /usr/local/bin/tau-status << 'SCRIPT'
#!/bin/bash
echo "=== Tau Services Status ==="
systemctl status tau-daemon --no-pager
echo ""
systemctl status tau-frontend --no-pager
echo ""
systemctl status olad --no-pager
echo ""
systemctl status postgresql --no-pager
echo ""
echo "=== Network Info ==="
hostname -I
SCRIPT
chmod +x /usr/local/bin/tau-status

cat > /usr/local/bin/tau-logs << 'SCRIPT'
#!/bin/bash
journalctl -u tau-daemon -u tau-frontend -f
SCRIPT
chmod +x /usr/local/bin/tau-logs

cat > /usr/local/bin/tau-restart << 'SCRIPT'
#!/bin/bash
echo "Restarting Tau services..."
sudo systemctl restart tau-daemon
sudo systemctl restart tau-frontend
echo "Done. Checking status..."
sleep 2
tau-status
SCRIPT
chmod +x /usr/local/bin/tau-restart

EOF

echo "Services enabled and convenience scripts created"
