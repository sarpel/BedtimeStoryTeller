#!/bin/bash
# Quick fix for the indentation error and service startup

echo "🔧 Applying immediate fix for service startup issue..."

# Stop the failing service
sudo systemctl stop storyteller

# Copy the simple service file
sudo cp scripts/storyteller-simple.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the simple service
sudo systemctl enable storyteller-simple

# Start the simple service
sudo systemctl start storyteller-simple

# Check status
echo "Service status:"
sudo systemctl status storyteller-simple --no-pager

echo ""
echo "Recent logs:"
sudo journalctl -u storyteller-simple -n 10 --no-pager

echo ""
echo "✅ Simple service should now be running!"
echo "Monitor with: sudo journalctl -u storyteller-simple -f"
echo "Test with: curl http://localhost:5000/api/status"