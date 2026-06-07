#!/usr/bin/env bash
# ============================================================
# FundAI Docs — dev tooling (all commands run in Docker)
#
#   ./dev/tools.sh up              Start PdfDing + Postgres + Docling
#   ./dev/tools.sh down            Stop app stack
#   ./dev/tools.sh shell           Interactive dev toolbox
#   ./dev/tools.sh install         poetry install (inside container)
#   ./dev/tools.sh build           Rebuild dev image
#   ./dev/tools.sh test            Run pytest suite
#   ./dev/tools.sh drive-test      Test Google Drive folder access
#   ./dev/tools.sh migrate         Run Django migrations (dev DB)
# ============================================================
set -euo pipefail

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$DEV_DIR")"
COMPOSE_FILE="$DEV_DIR/docker-compose.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ACTION="${1:-help}"
shift || true

_compose() {
    local env_args=()
    if [ -f "$DEV_DIR/.env" ]; then
        env_args=(--env-file "$DEV_DIR/.env")
    fi
    docker compose "${env_args[@]}" -f "$COMPOSE_FILE" "$@"
}

_ensure_env() {
    if [ ! -f "$DEV_DIR/.env" ]; then
        if [ -f "$REPO_DIR/.env.tools" ]; then
            echo -e "${YELLOW}Migrating $REPO_DIR/.env.tools → $DEV_DIR/.env${NC}"
            cp "$REPO_DIR/.env.tools" "$DEV_DIR/.env"
        else
            echo -e "${YELLOW}Creating $DEV_DIR/.env from example${NC}"
            cp "$DEV_DIR/.env.example" "$DEV_DIR/.env"
            echo -e "${RED}Edit dev/.env and set GOOGLE_DRIVE_FOLDER_ID${NC}"
        fi
    fi
}

_ensure_secrets() {
    local key="$DEV_DIR/secrets/google-drive-service-account.json"
    local legacy="$REPO_DIR/secrets/google-drive-service-account.json"
    mkdir -p "$DEV_DIR/secrets"
    if [ ! -f "$key" ] && [ -f "$legacy" ]; then
        echo -e "${YELLOW}Copying service account key to dev/secrets/${NC}"
        cp "$legacy" "$key"
    fi
}

_check_drive_prereqs() {
    _ensure_env
    _ensure_secrets
    # shellcheck source=/dev/null
    source "$DEV_DIR/.env"

    local key_file="${GOOGLE_DRIVE_KEY_FILE:-$DEV_DIR/secrets/google-drive-service-account.json}"
    if [ ! -f "$key_file" ]; then
        echo -e "${RED}ERROR: Service account key not found${NC}"
        echo "  Place JSON at: $DEV_DIR/secrets/google-drive-service-account.json"
        exit 1
    fi
    echo -e "${CYAN}Prerequisites OK${NC}"
    echo "  Key:    $key_file"
    if [ -n "${GOOGLE_DRIVE_FOLDER_ID:-}" ]; then
        echo "  Scope:  folder $GOOGLE_DRIVE_FOLDER_ID"
    else
        echo "  Scope:  all folders shared with the service account"
    fi
    echo ""
}

case "$ACTION" in
    up|start)
        _ensure_env
        _ensure_secrets
        echo -e "${GREEN}━━━ Starting docs app stack ━━━${NC}"
        _compose --profile app up -d
        echo ""
        echo "  PdfDing:  http://localhost:8001"
        echo "  Docling:  http://localhost:5001"
        echo "  Postgres: localhost:5433"
        ;;

    down|stop)
        _compose --profile app down
        ;;

    logs)
        _compose --profile app logs -f "${1:-pdfding}"
        ;;

    shell|bash)
        _ensure_env
        echo -e "${GREEN}━━━ Dev toolbox shell ━━━${NC}"
        _compose --profile tools run --rm toolbox bash
        ;;

    install)
        echo -e "${CYAN}Installing Python dependencies (Poetry, in container)…${NC}"
        _compose --profile tools run --rm toolbox poetry install --no-root --with dev
        echo -e "${GREEN}Done.${NC}"
        ;;

    build)
        echo -e "${CYAN}Rebuilding dev image…${NC}"
        _compose --profile tools build --no-cache toolbox
        echo -e "${GREEN}Done.${NC}"
        ;;

    test)
        _ensure_env
        echo -e "${GREEN}━━━ Running pytest (Docker) ━━━${NC}"
        _compose --profile tools run --rm test "$@"
        ;;

    drive-test|drive)
        _check_drive_prereqs
        echo -e "${GREEN}━━━ Google Drive folder test (Docker) ━━━${NC}"
        _compose --profile tools run --rm drive-test "$@"
        ;;

    migrate)
        _ensure_env
        echo -e "${GREEN}━━━ Django migrate (dev DB) ━━━${NC}"
        _compose up -d db
        _compose --profile tools run --rm migrate
        ;;

    check)
        _ensure_env
        _ensure_secrets
        _check_drive_prereqs 2>/dev/null || true
        echo -e "${CYAN}Dev folder check:${NC}"
        [ -f "$DEV_DIR/.env" ] && echo -e "  ${GREEN}✓${NC} dev/.env" || echo -e "  ${RED}✕${NC} dev/.env"
        [ -f "$DEV_DIR/secrets/google-drive-service-account.json" ] && echo -e "  ${GREEN}✓${NC} dev/secrets/key" || echo -e "  ${RED}✕${NC} dev/secrets/key"
        ;;

    help|--help|-h|"")
        echo "Usage: ./dev/tools.sh <command> [args]"
        echo ""
        echo "App stack:"
        echo "  up                 Start PdfDing + Postgres + Docling"
        echo "  down               Stop app stack"
        echo "  logs [service]     Follow logs (default: pdfding)"
        echo "  migrate            Run Django migrations against dev DB"
        echo ""
        echo "Toolbox (no host pip install):"
        echo "  shell              Interactive dev container"
        echo "  install            poetry install --with dev"
        echo "  build              Rebuild dev Docker image"
        echo "  test [pytest args] Run pytest suite"
        echo "  drive-test [opts]  Test Google Drive folder (--pdf-only)"
        echo "  check              Verify dev/.env and secrets"
        echo ""
        echo "Setup:"
        echo "  cp dev/.env.example dev/.env"
        echo "  cp /path/to/key.json dev/secrets/google-drive-service-account.json"
        echo "  ./dev/tools.sh build && ./dev/tools.sh drive-test"
        ;;

    *)
        echo -e "${RED}Unknown command: $ACTION${NC}"
        echo "Run ./dev/tools.sh help"
        exit 1
        ;;
esac
