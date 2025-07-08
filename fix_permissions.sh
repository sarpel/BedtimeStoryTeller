#!/bin/bash
# Fix permissions for storyteller service

echo "🔧 Fixing storyteller service permissions..."

# Create log directory if it doesn't exist
if [ ! -d "/var/log" ]; then
    sudo mkdir -p /var/log
fi

# Create and set permissions for log file
sudo touch /var/log/storyteller.log
sudo chmod 666 /var/log/storyteller.log

# Alternative: Create log file in /tmp if /var/log doesn't work
if [ ! -w "/var/log" ]; then
    echo "⚠️  /var/log not writable, using /tmp/storyteller.log"
    touch /tmp/storyteller.log
    chmod 666 /tmp/storyteller.log
fi

echo "✅ Permissions fixed"
echo ""
echo "Now try:"
echo "  git pull origin main"
echo "  sudo systemctl restart storyteller"
echo "  sudo journalctl -u storyteller -f"