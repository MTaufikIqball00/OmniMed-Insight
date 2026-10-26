#!/usr/bin/env bash
# =============================================================================
# OmniMed Insight (XAI) — Local Development Orchestrator (Linux / macOS)
# Note: Created as cross-platform companion to run-local.ps1.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

SERVICES="${1:-all}"
LOG_DIR="$REPO_ROOT/logs"
PID_FILE="$REPO_ROOT/.omnimed-launcher.pids"
mkdir -p "$LOG_DIR"

if [[ ! -f .env ]]; then
  echo "[Config] Initializing .env from .env.example..."
  SEC_HEX="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 64)"
  TOK_HEX="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 64)"
  sed -e "s/<GENERATE_AT_LEAST_32_BYTE_HEX_SECRET>/$SEC_HEX/g" \
      -e "s/<GENERATE_AT_LEAST_32_BYTE_INTERNAL_TOKEN>/$TOK_HEX/g" \
      -e "s/<SET_INITIAL_ADMIN_PASSWORD_ON_FIRST_RUN>/OmniMed!Admin#2026/g" \
      .env.example > .env
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

BIND_HOST="${BIND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"
RUST_BACKEND_PORT="${RUST_BACKEND_PORT:-8100}"
PYTHON_AI_PORT="${PYTHON_AI_PORT:-8200}"

echo "=== OmniMed Insight (XAI) Configuration Validated (Secrets Redacted) ==="
echo "  BIND_HOST         = $BIND_HOST"
echo "  FRONTEND_PORT     = $FRONTEND_PORT"
echo "  RUST_BACKEND_PORT = $RUST_BACKEND_PORT"
echo "  PYTHON_AI_PORT    = $PYTHON_AI_PORT"

check_port() {
  local port="$1"
  local name="$2"
  if lsof -iTCP:"$port" -sTCP:LISTEN -Pn >/dev/null 2>&1; then
    echo "[CONFLICT] Port $port ($name) is already in use:"
    lsof -iTCP:"$port" -sTCP:LISTEN -Pn
    exit 1
  else
    echo "[FREE] Port $port ($name)"
  fi
}

check_port "$FRONTEND_PORT" "Frontend"
check_port "$RUST_BACKEND_PORT" "Rust Backend"
check_port "$PYTHON_AI_PORT" "Python AI Service"

STARTED_PIDS=()
cleanup() {
  echo ""
  echo "[Launcher] Stopping child processes..."
  for pid in "${STARTED_PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

wait_http() {
  local name="$1"
  local url="$2"
  local max_wait="$3"
  local elapsed=0
  while (( elapsed < max_wait )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "  [READY] $name healthy at $url"
      return 0
    fi
    sleep 1
    ((elapsed++))
  done
  echo "  [FAILED] $name did not become healthy at $url within ${max_wait}s"
  exit 1
}

if [[ "$SERVICES" == "all" || "$SERVICES" == *"ai"* ]]; then
  (cd "$REPO_ROOT/ai-service-python" && python3 -m uvicorn app.main:app --host "$BIND_HOST" --port "$PYTHON_AI_PORT" >"$LOG_DIR/ai-service.log" 2>&1) &
  STARTED_PIDS+=($!)
  wait_http "Python AI Service" "http://$BIND_HOST:$PYTHON_AI_PORT/health" 45
fi

if [[ "$SERVICES" == "all" || "$SERVICES" == *"backend"* ]]; then
  cargo build --manifest-path "$REPO_ROOT/backend-rust/Cargo.toml"
  "$REPO_ROOT/backend-rust/target/debug/omnimed-backend-rust" >"$LOG_DIR/backend-rust.log" 2>&1 &
  STARTED_PIDS+=($!)
  wait_http "Rust Backend" "http://$BIND_HOST:$RUST_BACKEND_PORT/health" 30
fi

if [[ "$SERVICES" == "all" || "$SERVICES" == *"frontend"* ]]; then
  (cd "$REPO_ROOT/frontend" && npm install --no-audit --no-fund && npm run dev >"$LOG_DIR/frontend.log" 2>&1) &
  STARTED_PIDS+=($!)
  wait_http "Next.js Frontend" "http://$BIND_HOST:$FRONTEND_PORT" 60
fi

echo "=== All selected services are running. Press Ctrl+C to stop. ==="
wait
