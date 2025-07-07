#!/bin/bash
# Bedtime Storyteller Uninstall Script
# Removes all components and configurations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="BedtimeStoryTeller"
SERVICE_NAME="storyteller"
DEFAULT_USER="pi"
DEFAULT_HOME="/home/${DEFAULT_USER}"
INSTALL_DIR="${DEFAULT_HOME}/${PROJECT_NAME}"
LOG_DIR="/var/log/storyteller"

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

confirm_uninstall() {
    echo -e "${RED}WARNING: This will completely remove Bedtime Storyteller and all its data.${NC}"
    echo
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi
}

stop_and_disable_service() {
    log_info "Stopping and disabling service..."
    
    if systemctl is-active --quiet storyteller; then
        systemctl stop storyteller
        log_info "Service stopped"
    fi
    
    if systemctl is-enabled --quiet storyteller; then
        systemctl disable storyteller
        log_info "Service disabled"
    fi
    
    # Remove service file
    if [ -f "/etc/systemd/system/storyteller.service" ]; then
        rm -f "/etc/systemd/system/storyteller.service"
        systemctl daemon-reload
        log_info "Service file removed"
    fi
    
    log_success "Service uninstalled"
}

remove_nginx_config() {
    log_info "Removing nginx configuration..."
    
    # Remove nginx site
    if [ -f "/etc/nginx/sites-enabled/storyteller" ]; then
        rm -f "/etc/nginx/sites-enabled/storyteller"
        log_info "Nginx site disabled"
    fi
    
    if [ -f "/etc/nginx/sites-available/storyteller" ]; then
        rm -f "/etc/nginx/sites-available/storyteller"
        log_info "Nginx site configuration removed"
    fi
    
    # Restart nginx if it's running
    if systemctl is-active --quiet nginx; then
        systemctl restart nginx
        log_info "Nginx restarted"
    fi
    
    log_success "Nginx configuration removed"
}

remove_project_files() {
    log_info "Removing project files..."
    
    if [ -d "$INSTALL_DIR" ]; then
        # Backup important files if user wants to keep them
        read -p "Do you want to backup .env file and logs? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            backup_dir="${DEFAULT_HOME}/storyteller-backup-$(date +%Y%m%d-%H%M%S)"
            mkdir -p "$backup_dir"
            
            if [ -f "$INSTALL_DIR/.env" ]; then
                cp "$INSTALL_DIR/.env" "$backup_dir/"
                log_info "Backed up .env to $backup_dir"
            fi
            
            if [ -f "$INSTALL_DIR/storyteller.db" ]; then
                cp "$INSTALL_DIR/storyteller.db" "$backup_dir/"
                log_info "Backed up database to $backup_dir"
            fi
            
            chown -R $DEFAULT_USER:$DEFAULT_USER "$backup_dir"
        fi
        
        rm -rf "$INSTALL_DIR"
        log_info "Project directory removed"
    fi
    
    if [ -d "$LOG_DIR" ]; then
        rm -rf "$LOG_DIR"
        log_info "Log directory removed"
    fi
    
    log_success "Project files removed"
}

remove_audio_config() {
    log_info "Removing audio configuration..."
    
    # Remove IQAudio overlay from config.txt if it was added
    if [ -f "/boot/config.txt" ]; then
        if grep -q "dtoverlay=iqaudio-codec" /boot/config.txt; then
            read -p "Remove IQAudio overlay from boot config? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sed -i '/dtoverlay=iqaudio-codec/d' /boot/config.txt
                log_info "IQAudio overlay removed from boot config"
                log_warning "Reboot required to apply audio changes"
            fi
        fi
    fi
    
    log_success "Audio configuration cleaned up"
}

remove_user_from_groups() {
    log_info "Removing user from groups..."
    
    # Remove user from audio and gpio groups (only if they were added by our installer)
    if groups $DEFAULT_USER | grep -q '\baudio\b'; then
        read -p "Remove user from audio group? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            gpasswd -d $DEFAULT_USER audio
            log_info "User removed from audio group"
        fi
    fi
    
    if groups $DEFAULT_USER | grep -q '\bgpio\b'; then
        read -p "Remove user from gpio group? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            gpasswd -d $DEFAULT_USER gpio
            log_info "User removed from gpio group"
        fi
    fi
    
    log_success "User group memberships updated"
}

remove_system_packages() {
    log_info "System packages removal..."
    
    read -p "Remove system packages installed for Bedtime Storyteller? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_warning "The following packages will be removed:"
        echo "  - portaudio19-dev"
        echo "  - libasound2-dev"
        echo "  - python3-dev"
        echo "  - build-essential"
        echo
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            apt-get remove -y \
                portaudio19-dev \
                libasound2-dev \
                python3-dev \
                build-essential || true
            
            apt-get autoremove -y || true
            log_info "System packages removed"
        fi
    else
        log_info "System packages kept"
    fi
    
    log_success "Package cleanup completed"
}

cleanup_logs() {
    log_info "Cleaning up logs..."
    
    # Clear journal logs for the service
    journalctl --vacuum-time=1s --unit=storyteller || true
    
    log_success "Logs cleaned up"
}

display_completion() {
    echo
    log_success "Bedtime Storyteller has been completely uninstalled!"
    echo
    echo -e "${BLUE}What was removed:${NC}"
    echo -e "- Systemd service and service file"
    echo -e "- Nginx reverse proxy configuration"
    echo -e "- Project files and virtual environment"
    echo -e "- Log files and directories"
    echo
    
    if [ -d "${DEFAULT_HOME}/storyteller-backup-"* ] 2>/dev/null; then
        echo -e "${YELLOW}Backup files are available in:${NC}"
        ls -d "${DEFAULT_HOME}"/storyteller-backup-* 2>/dev/null || true
        echo
    fi
    
    echo -e "${YELLOW}Note: Some system packages and user group memberships may have been preserved.${NC}"
    echo -e "${YELLOW}Reboot recommended if audio configuration was modified.${NC}"
}

main() {
    log_info "Bedtime Storyteller Uninstall Script"
    echo
    
    check_root
    confirm_uninstall
    
    stop_and_disable_service
    remove_nginx_config
    remove_project_files
    remove_audio_config
    remove_user_from_groups
    remove_system_packages
    cleanup_logs
    
    display_completion
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi