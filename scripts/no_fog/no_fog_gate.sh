#!/usr/bin/env bash
# Shell wrapper for No-Fog Gate Automation
#
# This script provides a convenient command-line interface to the no-fog gate,
# handling environment setup and error reporting for CI/pre-commit integration.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/no_fog_gate.py"

# Default arguments
REGENERATE=true
SKIP_TESTS=false
TIMEOUT=30
CHECK_ONLY=false

# Print colored message
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
usage() {
    cat << EOF
No-Fog Gate Automation (Pre-commit + CI Core Contracts)

Usage: $0 [OPTIONS]

Options:
  --no-regenerate    Skip snapshot regeneration (use existing snapshot)
  --skip-tests       Skip running core contract tests
  --check-only       Dry run - only check if gate would pass
  --timeout SECONDS  Maximum time allowed for gate (default: 30)
  --help             Show this help message

Description:
  This gate makes it impossible to commit or merge code that violates core contracts
  or ships an outdated snapshot. It:
  1. Regenerates the full repository snapshot (SYSTEM_FULL_SNAPSHOT/)
  2. Runs core contract tests to ensure no regression
  3. Verifies snapshot is up-to-date with current repository state

Core contract tests:
  - tests/strategy/test_ast_identity.py
  - tests/test_ui_race_condition_headless.py
  - tests/features/test_feature_causality.py
  - tests/features/test_feature_lookahead_rejection.py
  - tests/features/test_feature_window_honesty.py

Exit codes:
  0 - Gate passed successfully
  1 - Gate failed (tests failed or snapshot issues)
  2 - Invalid arguments or setup error
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-regenerate)
                REGENERATE=false
                shift
                ;;
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --check-only)
                CHECK_ONLY=true
                shift
                ;;
            --timeout)
                if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
                    TIMEOUT="$2"
                    shift 2
                else
                    print_error "--timeout requires a value"
                    exit 2
                fi
                ;;
            --help)
                usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                usage
                exit 2
                ;;
            *)
                print_error "Unexpected argument: $1"
                usage
                exit 2
                ;;
        esac
    done
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check Python script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 2
    fi
    
    # Check Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "python3 not found in PATH"
        exit 2
    fi
    
    # Check Python version (>= 3.8)
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ $(echo "$PYTHON_VERSION < 3.8" | bc -l 2>/dev/null || echo "1") == "1" ]]; then
        print_warning "Python $PYTHON_VERSION detected, 3.8+ recommended"
    fi
    
    # Check for pytest
    if ! python3 -m pytest --version &> /dev/null; then
        print_warning "pytest not found, tests may fail"
    fi
    
    print_success "Prerequisites check passed"
}

# Build Python command arguments
build_python_args() {
    local args=()
    
    if [[ "$REGENERATE" == false ]]; then
        args+=("--no-regenerate")
    fi
    
    if [[ "$SKIP_TESTS" == true ]]; then
        args+=("--skip-tests")
    fi
    
    if [[ "$CHECK_ONLY" == true ]]; then
        args+=("--check-only")
    fi
    
    args+=("--timeout" "$TIMEOUT")
    
    echo "${args[@]}"
}

# Main execution
main() {
    parse_args "$@"
    
    print_info "Starting No-Fog Gate"
    print_info "Project root: $PROJECT_ROOT"
    print_info "Python script: $PYTHON_SCRIPT"
    print_info "Arguments: regenerate=$REGENERATE, skip_tests=$SKIP_TESTS, timeout=${TIMEOUT}s"
    
    check_prerequisites
    
    # Change to project root
    cd "$PROJECT_ROOT" || {
        print_error "Failed to change to project root: $PROJECT_ROOT"
        exit 2
    }
    
    # Build and run Python command
    PYTHON_ARGS=$(build_python_args)
    
    print_info "Running: python3 $PYTHON_SCRIPT $PYTHON_ARGS"
    echo ""
    
    # Execute Python script
    if python3 "$PYTHON_SCRIPT" $PYTHON_ARGS; then
        echo ""
        print_success "No-Fog Gate completed successfully"
        exit 0
    else
        EXIT_CODE=$?
        echo ""
        print_error "No-Fog Gate failed with exit code: $EXIT_CODE"
        
        # Provide helpful suggestions based on exit code
        case $EXIT_CODE in
            1)
                print_info "Failure likely due to:"
                print_info "  • Core contract tests failed"
                print_info "  • Snapshot generation failed"
                print_info "  • Snapshot verification failed"
                print_info ""
                print_info "Run with --skip-tests to isolate test failures"
                print_info "Run with --no-regenerate to skip snapshot regeneration"
                ;;
            *)
                print_info "Unknown failure, check the output above"
                ;;
        esac
        
        exit 1
    fi
}

# Run main function with all arguments
main "$@"