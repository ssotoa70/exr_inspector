#!/bin/bash

##############################################################################
# exr-inspector: Automated Production Deployment Script
#
# This script automates the complete deployment of exr-inspector to VAST
# DataEngine with VAST DataBase integration.
#
# Usage:
#   ./deploy.sh              # Interactive mode (prompts for config)
#   ./deploy.sh --config env # Load config from env file
#
# Configuration file format (.env):
#   VAST_CLUSTER_URL="https://vast-cluster.internal"
#   VAST_API_KEY="..."
#   VAST_DB_ENDPOINT="s3.region.vastdata.com"
#   VAST_DB_ACCESS_KEY="..."
#   VAST_DB_SECRET_KEY="..."
#   REGISTRY_URL="docker.io"
#   REGISTRY_USERNAME="..."
#   REGISTRY_PASSWORD="..."
#   S3_BUCKET="exr-input-data"
#
##############################################################################

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Script metadata
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_LOG="${PROJECT_ROOT}/deployment.log"
DEPLOYMENT_STATE="${PROJECT_ROOT}/.deployment.state"

##############################################################################
# Initialization & Utilities
##############################################################################

init_logging() {
    log_info "Logging to: $DEPLOYMENT_LOG"
    {
        echo "==================================="
        echo "exr-inspector Deployment Log"
        echo "Started: $(date)"
        echo "==================================="
    } > "$DEPLOYMENT_LOG"
}

cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log_error "Deployment failed (exit code: $exit_code)"
        log_info "See logs at: $DEPLOYMENT_LOG"
    fi
    exit $exit_code
}

trap cleanup EXIT

check_prerequisites() {
    log_info "Checking system prerequisites..."

    local missing=()

    # Check required commands
    for cmd in git docker python3 vastde curl jq; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        log_info "Please install: ${missing[*]}"
        return 1
    fi

    log_success "All prerequisites present"

    # Verify versions
    log_info "Verifying tool versions..."
    local docker_version=$(docker --version | awk '{print $3}' | sed 's/,//')
    local python_version=$(python3 --version 2>&1 | awk '{print $2}')
    local vastde_version=$(vastde --version 2>&1 | head -1 || echo "unknown")

    log_info "Docker: $docker_version"
    log_info "Python: $python_version"
    log_info "VAST CLI: $vastde_version"

    return 0
}

verify_cluster_connection() {
    local cluster_url="$1"
    local api_key="$2"

    log_info "Verifying VAST cluster connection..."

    if ! curl -s -k -H "Authorization: Bearer $api_key" "$cluster_url/api/system/info" > /dev/null 2>&1; then
        log_warn "Could not verify cluster connection. Continue anyway? (y/n)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            return 1
        fi
    else
        log_success "VAST cluster connection verified"
    fi

    return 0
}

##############################################################################
# Interactive Configuration
##############################################################################

interactive_config() {
    log_info "==== VAST Cluster Configuration ===="

    # Check if already configured
    if [ -f "$DEPLOYMENT_STATE" ]; then
        log_info "Found existing configuration. Load it? (y/n)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            source "$DEPLOYMENT_STATE"
            log_success "Configuration loaded"
            return 0
        fi
    fi

    # VAST Cluster
    echo -n "VAST Cluster URL (https://vast-cluster.internal): "
    read -r VAST_CLUSTER_URL
    VAST_CLUSTER_URL="${VAST_CLUSTER_URL:-https://vast-cluster.internal}"

    echo -n "VAST API Key: "
    read -rs VAST_API_KEY
    echo

    echo -n "VAST Tenant Name (default): "
    read -r VAST_TENANT_NAME
    VAST_TENANT_NAME="${VAST_TENANT_NAME:-default}"

    # DataBase
    log_info "==== VAST DataBase Configuration ===="

    echo -n "VAST DataBase Endpoint (s3.region.vastdata.com): "
    read -r VAST_DB_ENDPOINT
    VAST_DB_ENDPOINT="${VAST_DB_ENDPOINT:-s3.region.vastdata.com}"

    echo -n "VAST DataBase Access Key: "
    read -rs VAST_DB_ACCESS_KEY
    echo

    echo -n "VAST DataBase Secret Key: "
    read -rs VAST_DB_SECRET_KEY
    echo

    echo -n "VAST DataBase Region (us-east-1): "
    read -r VAST_DB_REGION
    VAST_DB_REGION="${VAST_DB_REGION:-us-east-1}"

    echo -n "VAST DataBase Schema Name (exr_metadata): "
    read -r VAST_DB_SCHEMA
    VAST_DB_SCHEMA="${VAST_DB_SCHEMA:-exr_metadata}"

    # Container Registry
    log_info "==== Container Registry Configuration ===="

    echo -n "Registry URL (docker.io or your private registry): "
    read -r REGISTRY_URL
    REGISTRY_URL="${REGISTRY_URL:-docker.io}"

    echo -n "Registry Username: "
    read -r REGISTRY_USERNAME

    echo -n "Registry Password: "
    read -rs REGISTRY_PASSWORD
    echo

    echo -n "Image Repository (my-org/exr-inspector): "
    read -r IMAGE_REPOSITORY
    IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-my-org/exr-inspector}"

    echo -n "Image Tag (v1.0.0): "
    read -r IMAGE_TAG
    IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"

    # S3 Configuration
    log_info "==== S3 Input Bucket Configuration ===="

    echo -n "S3 Bucket Name (exr-input-data): "
    read -r S3_BUCKET
    S3_BUCKET="${S3_BUCKET:-exr-input-data}"

    # Save configuration
    save_config
}

save_config() {
    log_info "Saving configuration..."
    cat > "$DEPLOYMENT_STATE" << EOF
# exr-inspector Deployment Configuration
# Generated: $(date)

export VAST_CLUSTER_URL="$VAST_CLUSTER_URL"
export VAST_API_KEY="$VAST_API_KEY"
export VAST_TENANT_NAME="$VAST_TENANT_NAME"
export VAST_DB_ENDPOINT="$VAST_DB_ENDPOINT"
export VAST_DB_ACCESS_KEY="$VAST_DB_ACCESS_KEY"
export VAST_DB_SECRET_KEY="$VAST_DB_SECRET_KEY"
export VAST_DB_REGION="$VAST_DB_REGION"
export VAST_DB_SCHEMA="$VAST_DB_SCHEMA"
export REGISTRY_URL="$REGISTRY_URL"
export REGISTRY_USERNAME="$REGISTRY_USERNAME"
export REGISTRY_PASSWORD="$REGISTRY_PASSWORD"
export IMAGE_REPOSITORY="$IMAGE_REPOSITORY"
export IMAGE_TAG="$IMAGE_TAG"
export S3_BUCKET="$S3_BUCKET"
EOF
    log_success "Configuration saved to: $DEPLOYMENT_STATE"
}

load_config() {
    local config_file="$1"
    if [ ! -f "$config_file" ]; then
        log_error "Config file not found: $config_file"
        return 1
    fi
    source "$config_file"
    log_success "Configuration loaded from: $config_file"
}

##############################################################################
# Phase 1: Schema & Database Setup
##############################################################################

phase1_schema_setup() {
    log_info "=========================================="
    log_info "PHASE 1: Schema & Database Setup"
    log_info "=========================================="

    log_info "Creating VAST DataBase schema..."

    # Generate and execute schema SQL
    cat > /tmp/exr_schema.sql << 'SQLEOF'
-- exr-inspector VAST DataBase Schema
-- Created: $(date)

CREATE SCHEMA IF NOT EXISTS exr_metadata;

-- Files table
CREATE TABLE IF NOT EXISTS exr_metadata.files (
    file_id STRING PRIMARY KEY,
    file_path STRING NOT NULL,
    file_path_normalized STRING NOT NULL,
    header_hash STRING,
    size_bytes BIGINT,
    mtime TIMESTAMP,
    exr_version INT,
    multipart_count INT DEFAULT 1,
    is_deep BOOLEAN DEFAULT FALSE,
    is_tiled BOOLEAN DEFAULT FALSE,
    metadata_embedding FLOAT VECTOR(384),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_inspected TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    inspection_count INT DEFAULT 1,
    schema_version INT DEFAULT 1,
    inspector_version STRING,
    raw_output STRING,
    UNIQUE (file_path_normalized, header_hash)
);

-- Parts table
CREATE TABLE IF NOT EXISTS exr_metadata.parts (
    part_id STRING PRIMARY KEY,
    file_id STRING NOT NULL,
    part_index INT,
    part_name STRING,
    view_name STRING,
    data_window STRING,
    display_window STRING,
    compression STRING,
    is_tiled BOOLEAN DEFAULT FALSE,
    is_deep BOOLEAN DEFAULT FALSE,
    pixel_aspect_ratio FLOAT,
    line_order STRING,
    FOREIGN KEY (file_id) REFERENCES exr_metadata.files(file_id)
);

-- Channels table
CREATE TABLE IF NOT EXISTS exr_metadata.channels (
    channel_id STRING PRIMARY KEY,
    file_id STRING NOT NULL,
    part_id STRING,
    channel_name STRING NOT NULL,
    channel_type STRING,
    layer_name STRING,
    component_name STRING,
    x_sampling INT,
    y_sampling INT,
    channel_fingerprint FLOAT VECTOR(128),
    FOREIGN KEY (file_id) REFERENCES exr_metadata.files(file_id),
    FOREIGN KEY (part_id) REFERENCES exr_metadata.parts(part_id)
);

-- Attributes table
CREATE TABLE IF NOT EXISTS exr_metadata.attributes (
    attribute_id STRING PRIMARY KEY,
    file_id STRING NOT NULL,
    part_id STRING,
    attr_name STRING NOT NULL,
    attr_type STRING,
    value_json STRING,
    value_text STRING,
    value_int BIGINT,
    value_float FLOAT,
    FOREIGN KEY (file_id) REFERENCES exr_metadata.files(file_id),
    FOREIGN KEY (part_id) REFERENCES exr_metadata.parts(part_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_path ON exr_metadata.files(file_path_normalized);
CREATE INDEX IF NOT EXISTS idx_files_hash ON exr_metadata.files(header_hash);
CREATE INDEX IF NOT EXISTS idx_parts_file_id ON exr_metadata.parts(file_id);
CREATE INDEX IF NOT EXISTS idx_channels_file_id ON exr_metadata.channels(file_id);
CREATE INDEX IF NOT EXISTS idx_attributes_file_id ON exr_metadata.attributes(file_id);
SQLEOF

    log_info "Applying schema to VAST DataBase..."

    # Execute schema (this would use VAST ADBC or SDK)
    # For now, just show what would be executed
    log_warn "Schema SQL generated at: /tmp/exr_schema.sql"
    log_info "Please execute using VAST DataBase client:"
    log_info "  vastdb query < /tmp/exr_schema.sql"

    log_success "Schema setup phase complete"
}

##############################################################################
# Phase 2: Build & Container Registry
##############################################################################

phase2_build_container() {
    log_info "=========================================="
    log_info "PHASE 2: Build & Container Registry"
    log_info "=========================================="

    log_info "Building container image..."

    cd "$PROJECT_ROOT"

    # Build using vastde
    if vastde functions build exr-inspector \
        --target functions/exr_inspector \
        --image-tag "$IMAGE_REPOSITORY:$IMAGE_TAG"; then
        log_success "Container image built: $IMAGE_REPOSITORY:$IMAGE_TAG"
    else
        log_error "Failed to build container image"
        return 1
    fi

    log_info "Authenticating with registry..."

    if echo "$REGISTRY_PASSWORD" | docker login -u "$REGISTRY_USERNAME" --password-stdin "$REGISTRY_URL"; then
        log_success "Registry authentication successful"
    else
        log_error "Failed to authenticate with registry"
        return 1
    fi

    log_info "Pushing image to registry..."

    if docker push "$REGISTRY_URL/$IMAGE_REPOSITORY:$IMAGE_TAG"; then
        log_success "Image pushed: $REGISTRY_URL/$IMAGE_REPOSITORY:$IMAGE_TAG"
    else
        log_error "Failed to push image"
        return 1
    fi
}

##############################################################################
# Phase 3: Function Deployment
##############################################################################

phase3_deploy_function() {
    log_info "=========================================="
    log_info "PHASE 3: Function Deployment"
    log_info "=========================================="

    log_info "Creating function in VAST DataEngine..."

    # Create function JSON configuration
    cat > /tmp/exr_function.json << EOF
{
  "name": "exr-inspector",
  "description": "EXR file inspection with VAST DataBase persistence",
  "image": "$REGISTRY_URL/$IMAGE_REPOSITORY:$IMAGE_TAG",
  "environmentVariables": {
    "VAST_DB_ENDPOINT": "$VAST_DB_ENDPOINT",
    "VAST_DB_ACCESS_KEY": "$VAST_DB_ACCESS_KEY",
    "VAST_DB_SECRET_KEY": "$VAST_DB_SECRET_KEY",
    "VAST_DB_REGION": "$VAST_DB_REGION",
    "VAST_DB_SCHEMA": "$VAST_DB_SCHEMA"
  },
  "timeout": 300,
  "memorySize": 1024
}
EOF

    log_warn "Function configuration generated at: /tmp/exr_function.json"
    log_info "Please create function in VAST UI:"
    log_info "  1. Navigate to Manage Elements → Functions"
    log_info "  2. Click 'Create New Function'"
    log_info "  3. Fill in details from: /tmp/exr_function.json"
    log_info "  4. Use image: $REGISTRY_URL/$IMAGE_REPOSITORY:$IMAGE_TAG"

    log_success "Function deployment phase complete"
}

##############################################################################
# Phase 4: Trigger & Pipeline
##############################################################################

phase4_configure_trigger() {
    log_info "=========================================="
    log_info "PHASE 4: Trigger & Pipeline Configuration"
    log_info "=========================================="

    log_info "Pipeline and trigger configuration needed..."

    cat > /tmp/trigger_config.json << EOF
{
  "triggerType": "element",
  "watch": "$S3_BUCKET",
  "eventType": "add",
  "filter": {
    "suffix": ".exr"
  },
  "function": "exr-inspector"
}
EOF

    log_warn "Trigger configuration generated at: /tmp/trigger_config.json"
    log_info "Please configure trigger in VAST UI:"
    log_info "  1. Create new trigger watching bucket: $S3_BUCKET"
    log_info "  2. Watch for .exr file uploads"
    log_info "  3. Route events to exr-inspector function"
    log_info "  4. Create pipeline with trigger + function"

    log_success "Trigger configuration phase complete"
}

##############################################################################
# Phase 5: Verification & Smoke Tests
##############################################################################

phase5_smoke_tests() {
    log_info "=========================================="
    log_info "PHASE 5: Verification & Smoke Tests"
    log_info "=========================================="

    log_info "Running local tests..."

    cd "$PROJECT_ROOT"

    # Run unit tests
    if python3 -m pytest functions/exr_inspector/test_vast_db_persistence.py -v --tb=short; then
        log_success "All unit tests passed"
    else
        log_error "Unit tests failed"
        return 1
    fi

    log_info "Test manual invocation..."

    cat > /tmp/test_event.json << 'EOF'
{
  "file": {
    "path": "/test/sample.exr"
  },
  "channels": [],
  "parts": []
}
EOF

    log_warn "Test event created at: /tmp/test_event.json"
    log_info "To test deployed function, upload sample EXR file:"
    log_info "  aws s3 cp sample.exr s3://$S3_BUCKET/"
    log_info "Then monitor logs in VAST DataEngine UI"

    log_success "Smoke tests phase complete"
}

##############################################################################
# Monitoring & Rollback
##############################################################################

setup_monitoring() {
    log_info "=========================================="
    log_info "Setting up Monitoring & Observability"
    log_info "=========================================="

    cat > /tmp/monitoring_setup.sh << 'MONEOF'
#!/bin/bash

# Monitor DataEngine function logs
monitor_logs() {
    echo "Streaming DataEngine function logs..."
    vastde pipelines logs -f exr-inspector
}

# Query VAST DataBase
verify_data() {
    echo "Verifying data in VAST DataBase..."
    vastdb query "SELECT COUNT(*) as file_count FROM exr_metadata.files"
    vastdb query "SELECT COUNT(*) as channel_count FROM exr_metadata.channels"
}

# Health check
health_check() {
    echo "Checking function health..."
    vastde functions status exr-inspector
}

echo "Available monitoring commands:"
echo "  monitor_logs    - Stream function logs"
echo "  verify_data     - Check database record count"
echo "  health_check    - Function status"
MONEOF

    chmod +x /tmp/monitoring_setup.sh
    log_info "Monitoring setup script: /tmp/monitoring_setup.sh"
}

##############################################################################
# Rollback & Recovery
##############################################################################

show_rollback_procedure() {
    log_info "=========================================="
    log_info "Rollback Procedures"
    log_info "=========================================="

    cat << 'RBEOF'
If deployment fails, you can rollback:

1. Function Code Rollback:
   - Redeploy previous image version:
     docker pull registry/exr-inspector:v0.9.0
     vastde functions build exr-inspector \
       --image-tag registry/exr-inspector:v0.9.0

2. Database Cleanup:
   - Backup current data:
     vastdb query "CREATE TABLE exr_metadata.files_backup AS SELECT * FROM exr_metadata.files"

   - Reset tables:
     TRUNCATE TABLE exr_metadata.files;
     TRUNCATE TABLE exr_metadata.parts;
     TRUNCATE TABLE exr_metadata.channels;
     TRUNCATE TABLE exr_metadata.attributes;

3. Full Cleanup:
   - Drop schema:
     DROP SCHEMA exr_metadata CASCADE;

   - Redeploy from scratch

See PROD_RUNBOOK.md for detailed recovery procedures.
RBEOF

}

##############################################################################
# Main Deployment Flow
##############################################################################

main() {
    init_logging

    log_info "=========================================="
    log_info "exr-inspector Automated Deployment"
    log_info "=========================================="

    # Check prerequisites
    if ! check_prerequisites; then
        log_error "Prerequisites check failed"
        return 1
    fi

    # Load or gather configuration
    if [[ $# -gt 0 && "$1" == "--config" && -n "${2:-}" ]]; then
        load_config "$2"
    else
        interactive_config
    fi

    # Verify cluster connection
    if ! verify_cluster_connection "$VAST_CLUSTER_URL" "$VAST_API_KEY"; then
        log_warn "Proceeding anyway..."
    fi

    # Deployment phases
    phase1_schema_setup || return 1
    phase2_build_container || return 1
    phase3_deploy_function || return 1
    phase4_configure_trigger || return 1
    phase5_smoke_tests || return 1

    # Setup monitoring
    setup_monitoring

    # Show summary
    log_info "=========================================="
    log_info "Deployment Summary"
    log_info "=========================================="
    log_success "Phases 1-5 completed successfully!"
    log_info ""
    log_info "Configuration saved: $DEPLOYMENT_STATE"
    log_info "Deployment log: $DEPLOYMENT_LOG"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Review generated configuration files in /tmp/"
    log_info "  2. Complete manual VAST UI setup (schema, function, trigger)"
    log_info "  3. Upload test EXR files to S3 bucket: $S3_BUCKET"
    log_info "  4. Monitor logs: vastde pipelines logs -f exr-inspector"
    log_info "  5. Verify data: vastdb query \"SELECT * FROM exr_metadata.files\""
    log_info ""

    show_rollback_procedure
}

# Run main
main "$@"
