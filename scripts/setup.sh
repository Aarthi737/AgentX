#!/usr/bin/env bash
# ============================================================
# AgentX — Setup & Run Script
# Usage: ./scripts/setup.sh [dev|prod|docker]
# ============================================================
set -e

MODE=${1:-dev}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

print_header() {
  echo ""
  echo "========================================"
  echo " AgentX — $1"
  echo "========================================"
  echo ""
}

check_env() {
  if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "ERROR: .env file not found."
    echo "Copy .env.example to .env and fill in all values:"
    echo "  cp $ROOT_DIR/.env.example $ROOT_DIR/.env"
    exit 1
  fi
  echo "✓ .env file found"
}

setup_backend() {
  print_header "Setting up Backend"
  cd "$ROOT_DIR/backend"

  # Create virtual environment
  if [ ! -d ".venv" ]; then
    python3.11 -m venv .venv
    echo "✓ Virtual environment created"
  fi

  source .venv/bin/activate
  pip install --upgrade pip -q
  pip install -r requirements.txt -q
  echo "✓ Backend dependencies installed"

  # Run migrations
  echo "Running database migrations..."
  alembic upgrade head
  echo "✓ Migrations applied"
}

setup_frontend() {
  print_header "Setting up Frontend"
  cd "$ROOT_DIR/frontend"

  npm install
  echo "✓ Frontend dependencies installed"
}

run_dev() {
  print_header "Starting Development Servers"

  # Backend
  cd "$ROOT_DIR/backend"
  source .venv/bin/activate
  echo "Starting backend on http://localhost:8000 ..."
  uvicorn app:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!

  # Frontend
  cd "$ROOT_DIR/frontend"
  echo "Starting frontend on http://localhost:3000 ..."
  npm run dev &
  FRONTEND_PID=$!

  echo ""
  echo "✓ Backend:  http://localhost:8000"
  echo "✓ Frontend: http://localhost:3000"
  echo "✓ API Docs: http://localhost:8000/docs"
  echo ""
  echo "Press Ctrl+C to stop all servers."

  trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
  wait
}

run_docker() {
  print_header "Starting with Docker Compose"
  cd "$ROOT_DIR"
  docker compose up --build
}

run_tests() {
  print_header "Running Tests"
  cd "$ROOT_DIR/backend"
  source .venv/bin/activate 2>/dev/null || true
  pytest tests/ -v --tb=short
}

case "$MODE" in
  dev)
    check_env
    setup_backend
    setup_frontend
    run_dev
    ;;
  prod|docker)
    check_env
    run_docker
    ;;
  test)
    check_env
    run_tests
    ;;
  setup-only)
    check_env
    setup_backend
    setup_frontend
    ;;
  migrate)
    check_env
    cd "$ROOT_DIR/backend"
    source .venv/bin/activate
    alembic upgrade head
    ;;
  *)
    echo "Usage: $0 [dev|prod|docker|test|setup-only|migrate]"
    exit 1
    ;;
esac
