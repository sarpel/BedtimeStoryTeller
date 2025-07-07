#!/bin/bash
# Bedtime Storyteller Setup Script
# Automated installation and configuration for Raspberry Pi

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="BedtimeStoryTeller"
SERVICE_NAME="storyteller"

# Detect current user or use fallback
if [ -n "$SUDO_USER" ]; then
    TARGET_USER="$SUDO_USER"
else
    TARGET_USER="$(whoami)"
    if [ "$TARGET_USER" = "root" ]; then
        TARGET_USER="pi"  # Fallback for root execution
    fi
fi

TARGET_HOME="$(eval echo ~$TARGET_USER)"
INSTALL_DIR="${TARGET_HOME}/${PROJECT_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
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

detect_pi_model() {
    local model=""
    if [ -f /proc/device-tree/model ]; then
        model=$(cat /proc/device-tree/model)
    elif [ -f /proc/cpuinfo ]; then
        model=$(grep "Model" /proc/cpuinfo | cut -d: -f2 | xargs)
    fi
    
    if [[ $model == *"Pi Zero 2"* ]]; then
        echo "pi_zero_2w"
    elif [[ $model == *"Pi 5"* ]]; then
        echo "pi_5"
    elif [[ $model == *"Pi 4"* ]]; then
        echo "pi_4"
    else
        echo "unknown"
    fi
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        
        # Check for DietPi specifically first
        if [ -f /boot/dietpi/.version ] || [ -f /DietPi/dietpi/.version ] || [[ "$PRETTY_NAME" == *"DietPi"* ]]; then
            echo "dietpi"
            return
        fi
        
        case "$ID" in
            "dietpi")
                echo "dietpi"
                ;;
            "raspbian"|"debian")
                # Double-check it's not DietPi masquerading as Debian
                if [[ "$PRETTY_NAME" == *"DietPi"* ]] || [[ "$NAME" == *"DietPi"* ]]; then
                    echo "dietpi"
                else
                    echo "raspios"
                fi
                ;;
            "ubuntu")
                echo "ubuntu"
                ;;
            *)
                # Check if it's DietPi with a different ID
                if [[ "$PRETTY_NAME" == *"DietPi"* ]] || [[ "$NAME" == *"DietPi"* ]]; then
                    echo "dietpi"
                else
                    echo "$ID"
                fi
                ;;
        esac
    else
        echo "unknown"
    fi
}

install_system_packages() {
    log_info "Installing system packages..."
    
    local os_type=$(detect_os)
    
    apt-get update
    
    # Base packages for all systems
    local base_packages="python3 python3-pip python3-venv python3-dev git curl wget build-essential libasound2-dev portaudio19-dev libssl-dev libffi-dev sqlite3 systemd"
    
    # OS-specific packages
    case "$os_type" in
        "dietpi")
            log_info "Installing packages for DietPi..."
            apt-get install -y $base_packages
            # DietPi is minimal, avoid unnecessary packages
            ;;
        "raspios")
            log_info "Installing packages for Raspberry Pi OS..."
            apt-get install -y $base_packages nginx
            ;;
        *)
            log_info "Installing packages for $os_type..."
            apt-get install -y $base_packages
            ;;
    esac
    
    # Pi-specific packages
    local pi_model=$(detect_pi_model)
    if [[ $pi_model == "pi_zero_2w" || $pi_model == "pi_4" || $pi_model == "pi_5" ]]; then
        log_info "Installing Raspberry Pi specific packages..."
        apt-get install -y \
            raspberrypi-kernel-headers \
            raspi-config \
            rpi.gpio-common
    fi
    
    log_success "System packages installed"
}

setup_audio() {
    log_info "Configuring audio system..."
    
    local pi_model=$(detect_pi_model)
    
    if [[ $pi_model == "pi_zero_2w" ]]; then
        log_info "Configuring IQAudio Codec for Pi Zero 2W..."
        
        # Enable I2C and SPI
        raspi-config nonint do_i2c 0
        raspi-config nonint do_spi 0
        
        # Add IQAudio overlay to config.txt (check both possible locations)
        local config_file=""
        if [ -f "/boot/firmware/config.txt" ]; then
            config_file="/boot/firmware/config.txt"
        elif [ -f "/boot/config.txt" ]; then
            config_file="/boot/config.txt"
        else
            log_error "Could not find config.txt file"
            return 1
        fi
        
        if ! grep -q "dtoverlay=iqaudio-codec" "$config_file"; then
            echo "dtoverlay=iqaudio-codec" >> "$config_file"
            log_info "Added IQAudio overlay to $config_file"
        fi
        
    elif [[ $pi_model == "pi_5" ]]; then
        log_info "Configuring USB Audio for Pi 5..."
        # USB audio should work out of the box
        
    else
        log_warning "Unknown Pi model, using default audio configuration"
    fi
    
    # Ensure audio group permissions
    usermod -a -G audio $TARGET_USER
    
    log_success "Audio system configured"
}

setup_gpio() {
    log_info "Configuring GPIO access..."
    
    # Add user to gpio group
    usermod -a -G gpio $TARGET_USER
    
    # Set GPIO permissions
    if [ -f /dev/gpiomem ]; then
        chown root:gpio /dev/gpiomem
        chmod g+rw /dev/gpiomem
    fi
    
    log_success "GPIO access configured"
}

create_user_and_directories() {
    log_info "Setting up user and directories..."
    
    # Ensure user exists
    if ! id "$TARGET_USER" &>/dev/null; then
        useradd -m -s /bin/bash $TARGET_USER
        log_info "Created user: $TARGET_USER"
    fi
    
    # Create directories
    mkdir -p $INSTALL_DIR
    mkdir -p $LOG_DIR
    
    # Set ownership
    chown -R $TARGET_USER:$TARGET_USER $INSTALL_DIR
    chown -R $TARGET_USER:$TARGET_USER $LOG_DIR
    
    log_success "Directories created"
}

install_python_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Switch to user account for venv creation
    sudo -u $TARGET_USER bash << EOF
cd $INSTALL_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
EOF
    
    log_success "Python dependencies installed"
}

configure_environment() {
    log_info "Configuring environment..."
    
    # Copy environment template
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        if [ -f "$INSTALL_DIR/.env.example" ]; then
            sudo -u $TARGET_USER cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
            log_info "Created .env file from template"
        else
            log_error ".env.example file not found. Please ensure it exists in the project."
            return 1
        fi
    else
        log_warning ".env file already exists, skipping"
    fi
    
    # Set basic configuration based on detected hardware
    local pi_model=$(detect_pi_model)
    sudo -u $TARGET_USER bash << EOF
cd $INSTALL_DIR
sed -i "s/PI_MODEL=.*/PI_MODEL=$pi_model/" .env
EOF
    
    log_success "Environment configured"
}

install_systemd_service() {
    log_info "Installing systemd service..."
    
    # Copy service file
    cp "$INSTALL_DIR/scripts/storyteller.service" "/etc/systemd/system/"
    
    # Update service file with correct paths
    sed -i "s|/home/pi/bedtime-storyteller|$INSTALL_DIR|g" "/etc/systemd/system/storyteller.service"
    sed -i "s|/home/pi/BedtimeStoryTeller|$INSTALL_DIR|g" "/etc/systemd/system/storyteller.service"
    sed -i "s|User=pi|User=$TARGET_USER|g" "/etc/systemd/system/storyteller.service"
    sed -i "s|Group=pi|Group=$TARGET_USER|g" "/etc/systemd/system/storyteller.service"
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable storyteller
    
    log_success "Systemd service installed"
}

setup_nginx() {
    local os_type=$(detect_os)
    
    # Only install nginx on full systems, not on DietPi
    if [[ "$os_type" == "dietpi" ]]; then
        log_info "Skipping nginx setup on DietPi (using direct port access)"
        return 0
    fi
    
    log_info "Configuring nginx reverse proxy..."
    
    # Create nginx configuration
    cat > /etc/nginx/sites-available/storyteller << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /ws {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
    
    # Enable site and restart nginx
    ln -sf /etc/nginx/sites-available/storyteller /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    systemctl enable nginx
    systemctl restart nginx
    
    log_success "Nginx configured"
}

run_initial_tests() {
    log_info "Running initial system tests..."
    
    # Test Python installation
    sudo -u $TARGET_USER bash << 'EOF'
cd $INSTALL_DIR
source venv/bin/activate
python -c "import storyteller; print('Import successful')" || echo "Import failed (expected without dependencies)"
EOF
    
    # Test service file
    systemctl status storyteller --no-pager || true
    
    log_success "Initial tests completed"
}

display_next_steps() {
    log_success "Installation completed successfully!"
    echo
    echo -e "${BLUE}Next Steps:${NC}"
    echo -e "1. Edit the configuration file:"
    echo -e "   ${YELLOW}sudo nano $INSTALL_DIR/.env${NC}"
    echo
    echo -e "2. Add your API keys:"
    echo -e "   - ${YELLOW}OPENAI_API_KEY${NC} (required)"
    echo -e "   - ${YELLOW}PORCUPINE_ACCESS_KEY${NC} (required for wake word)"
    echo
    echo -e "3. Start the service:"
    echo -e "   ${YELLOW}sudo systemctl start storyteller${NC}"
    echo
    echo -e "4. Check service status:"
    echo -e "   ${YELLOW}sudo systemctl status storyteller${NC}"
    echo
    echo -e "5. View logs:"
    echo -e "   ${YELLOW}sudo journalctl -u storyteller -f${NC}"
    echo
    echo -e "6. Access web interface:"
    echo -e "   ${YELLOW}http://$(hostname -I | awk '{print $1}')/${NC}"
    echo
    echo -e "7. Test the system:"
    echo -e "   ${YELLOW}sudo -u $TARGET_USER $INSTALL_DIR/venv/bin/python -m storyteller.main test${NC}"
    echo
    if [[ $(detect_pi_model) == "pi_zero_2w" ]]; then
        echo -e "${YELLOW}Note: Pi Zero 2W detected. A reboot is recommended to apply audio configuration.${NC}"
    fi
}

main() {
    log_info "Starting Bedtime Storyteller installation..."
    echo
    
    # Debug OS detection
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        log_info "OS Debug - ID: $ID, NAME: $NAME, PRETTY_NAME: $PRETTY_NAME"
    fi
    
    log_info "Detected OS: $(detect_os)"
    log_info "Detected Pi Model: $(detect_pi_model)"
    echo
    
    check_root
    install_system_packages
    setup_audio
    setup_gpio
    create_user_and_directories
    
    # Copy source files if not already present
    if [ ! -f "$INSTALL_DIR/storyteller/main.py" ]; then
        log_error "Source files not found in $INSTALL_DIR"
        log_error "Please copy the project files to $INSTALL_DIR first"
        exit 1
    fi
    
    install_python_dependencies
    configure_environment
    install_systemd_service
    setup_nginx
    run_initial_tests
    display_next_steps
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi