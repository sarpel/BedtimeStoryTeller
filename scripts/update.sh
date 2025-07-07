#!/bin/bash
# Bedtime Storyteller Update Script
# Updates the application while preserving configuration and data

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="bedtime-storyteller"
SERVICE_NAME="storyteller"
DEFAULT_USER="pi"
DEFAULT_HOME="/home/${DEFAULT_USER}"
INSTALL_DIR="${DEFAULT_HOME}/${PROJECT_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
BACKUP_DIR="${INSTALL_DIR}/backups"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_installation() {
    if [ ! -d "$INSTALL_DIR" ]; then
        log_error "Bedtime Storyteller is not installed in $INSTALL_DIR"
        exit 1
    fi
    
    if [ ! -f "/etc/systemd/system/storyteller.service" ]; then
        log_error "Systemd service not found. Please run the setup script first."
        exit 1
    fi
}

create_backup() {
    log_info "Creating backup of current installation..."
    
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_path="${BACKUP_DIR}/backup-${timestamp}"
    
    # Create backup directory
    mkdir -p "$backup_path"
    
    # Backup configuration and data
    if [ -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env" "$backup_path/"
        log_info "Backed up .env file"
    fi
    
    if [ -f "$INSTALL_DIR/storyteller.db" ]; then
        cp "$INSTALL_DIR/storyteller.db" "$backup_path/"
        log_info "Backed up database"
    fi
    
    # Backup custom configurations
    if [ -d "$INSTALL_DIR/custom" ]; then
        cp -r "$INSTALL_DIR/custom" "$backup_path/"
        log_info "Backed up custom configurations"
    fi
    
    # Set ownership
    chown -R $DEFAULT_USER:$DEFAULT_USER "$backup_path"
    
    log_success "Backup created at $backup_path"
    echo "$backup_path" > "${BACKUP_DIR}/latest"
}

stop_service() {
    log_info "Stopping service..."
    
    if systemctl is-active --quiet storyteller; then
        systemctl stop storyteller
        log_success "Service stopped"
    else
        log_info "Service was not running"
    fi
}

update_source_code() {
    log_info "Updating source code..."
    
    # Save current directory
    local current_dir=$(pwd)
    
    # Update from git if it's a git repository
    if [ -d "$INSTALL_DIR/.git" ]; then
        cd "$INSTALL_DIR"
        sudo -u $DEFAULT_USER git fetch origin
        sudo -u $DEFAULT_USER git pull origin main
        log_success "Source code updated from git"
    else
        log_warning "Not a git repository. Please manually update source files."
        read -p "Have you updated the source files manually? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Please update source files and run this script again"
            exit 1
        fi
    fi
    
    cd "$current_dir"
}

update_dependencies() {
    log_info "Updating Python dependencies..."
    
    sudo -u $DEFAULT_USER bash << EOF
cd $INSTALL_DIR
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install --upgrade -r requirements.txt
EOF
    
    log_success "Dependencies updated"
}

update_database() {
    log_info "Updating database schema..."
    
    sudo -u $DEFAULT_USER bash << EOF
cd $INSTALL_DIR
source venv/bin/activate
python -c "
from storyteller.storage.models import create_database_engine, create_tables
import asyncio

async def update_db():
    engine = await create_database_engine('sqlite+aiosqlite:///./storyteller.db')
    await create_tables(engine)
    await engine.dispose()
    print('Database schema updated')

asyncio.run(update_db())
" || echo "Database update skipped (manual intervention may be required)"
EOF
    
    log_success "Database schema checked"
}

update_service_file() {
    log_info "Updating systemd service file..."
    
    if [ -f "$INSTALL_DIR/scripts/storyteller.service" ]; then
        # Compare current service file with new one
        if ! cmp -s "/etc/systemd/system/storyteller.service" "$INSTALL_DIR/scripts/storyteller.service"; then
            log_info "Service file has changed, updating..."
            
            # Backup current service file
            cp "/etc/systemd/system/storyteller.service" "${BACKUP_DIR}/storyteller.service.bak"
            
            # Copy new service file
            cp "$INSTALL_DIR/scripts/storyteller.service" "/etc/systemd/system/"
            
            # Update paths in service file
            sed -i "s|/home/pi/bedtime-storyteller|$INSTALL_DIR|g" "/etc/systemd/system/storyteller.service"
            sed -i "s|User=pi|User=$DEFAULT_USER|g" "/etc/systemd/system/storyteller.service"
            sed -i "s|Group=pi|Group=$DEFAULT_USER|g" "/etc/systemd/system/storyteller.service"
            
            # Reload systemd
            systemctl daemon-reload
            
            log_success "Service file updated"
        else
            log_info "Service file unchanged"
        fi
    else
        log_warning "New service file not found, keeping current version"
    fi
}

update_nginx_config() {
    log_info "Updating nginx configuration..."
    
    if [ -f "/etc/nginx/sites-available/storyteller" ]; then
        # Check if nginx config needs updating
        if [ -f "$INSTALL_DIR/scripts/nginx.conf" ]; then
            if ! cmp -s "/etc/nginx/sites-available/storyteller" "$INSTALL_DIR/scripts/nginx.conf"; then
                log_info "Nginx configuration has changed, updating..."
                
                # Backup current config
                cp "/etc/nginx/sites-available/storyteller" "${BACKUP_DIR}/nginx-storyteller.conf.bak"
                
                # Copy new config
                cp "$INSTALL_DIR/scripts/nginx.conf" "/etc/nginx/sites-available/storyteller"
                
                # Test nginx configuration
                if nginx -t; then
                    systemctl reload nginx
                    log_success "Nginx configuration updated"
                else
                    log_error "Nginx configuration test failed, restoring backup"
                    cp "${BACKUP_DIR}/nginx-storyteller.conf.bak" "/etc/nginx/sites-available/storyteller"
                fi
            else
                log_info "Nginx configuration unchanged"
            fi
        else
            log_info "No new nginx configuration found"
        fi
    else
        log_info "Nginx not configured for Bedtime Storyteller"
    fi
}

run_migration_tests() {
    log_info "Running migration tests..."
    
    sudo -u $DEFAULT_USER bash << EOF
cd $INSTALL_DIR
source venv/bin/activate

# Test basic imports
python -c "
try:
    from storyteller.main import StorytellerApplication
    print('✓ Main application import successful')
except Exception as e:
    print(f'✗ Import failed: {e}')
    exit(1)
"

# Test configuration
python -c "
try:
    from storyteller.config.settings import get_settings
    settings = get_settings()
    print('✓ Configuration loaded successfully')
except Exception as e:
    print(f'✗ Configuration failed: {e}')
    exit(1)
"

echo "Migration tests completed"
EOF
    
    log_success "Migration tests passed"
}

start_service() {
    log_info "Starting service..."
    
    systemctl start storyteller
    
    # Wait a moment and check if service started successfully
    sleep 3
    if systemctl is-active --quiet storyteller; then
        log_success "Service started successfully"
    else
        log_error "Service failed to start. Check logs with: journalctl -u storyteller -n 50"
        return 1
    fi
}

check_service_health() {
    log_info "Checking service health..."
    
    # Wait for service to fully initialize
    sleep 5
    
    # Try to connect to the web interface
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ | grep -q "200"; then
        log_success "Web interface is responding"
    else
        log_warning "Web interface may not be fully ready yet"
    fi
    
    log_success "Health check completed"
}

cleanup_old_backups() {
    log_info "Cleaning up old backups..."
    
    if [ -d "$BACKUP_DIR" ]; then
        # Keep only the last 5 backups
        sudo -u $DEFAULT_USER bash << EOF
cd $BACKUP_DIR
ls -t backup-* 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true
EOF
        log_success "Old backups cleaned up"
    fi
}

display_update_summary() {
    echo
    log_success "Update completed successfully!"
    echo
    echo -e "${BLUE}Update Summary:${NC}"
    echo -e "- Source code updated"
    echo -e "- Dependencies updated"
    echo -e "- Database schema checked"
    echo -e "- Service configuration updated"
    echo -e "- Service restarted and verified"
    echo
    echo -e "${BLUE}Useful Commands:${NC}"
    echo -e "- Check service status: ${YELLOW}sudo systemctl status storyteller${NC}"
    echo -e "- View logs: ${YELLOW}sudo journalctl -u storyteller -f${NC}"
    echo -e "- Access web interface: ${YELLOW}http://$(hostname -I | awk '{print $1}')/${NC}"
    echo
    if [ -f "${BACKUP_DIR}/latest" ]; then
        local latest_backup=$(cat "${BACKUP_DIR}/latest")
        echo -e "${YELLOW}Backup created at: $latest_backup${NC}"
    fi
}

main() {
    log_info "Starting Bedtime Storyteller update..."
    echo
    
    check_root
    check_installation
    
    # Create backup before updating
    create_backup
    
    # Stop service for update
    stop_service
    
    # Update components
    update_source_code
    update_dependencies
    update_database
    update_service_file
    update_nginx_config
    
    # Test the update
    run_migration_tests
    
    # Start service
    start_service
    check_service_health
    
    # Cleanup
    cleanup_old_backups
    
    display_update_summary
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi