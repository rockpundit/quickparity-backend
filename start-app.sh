#!/bin/bash

# Function to kill processes on exit
cleanup() {
    echo ""
    echo "🛑 Stopping QuickParity Control Plane..."
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID
    fi
    exit
}

# Trap Control+C (SIGINT)
trap cleanup INT

echo "🚀 Starting QuickParity Control Plane..."

# 1. Start Backend
echo "🔹 Starting Backend (FastAPI)..."
# Check if venv exists
if [ -d "venv" ]; then
    PYTHON_CMD="venv/bin/python"
else
    PYTHON_CMD="python3"
    echo "⚠️  Virtual environment not found, trying system python."
fi

$PYTHON_CMD -m uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "✅ Backend started with PID $BACKEND_PID"

# 2. Start Frontend
echo "🔹 Starting Frontend (Next.js)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
echo "✅ Frontend started with PID $FRONTEND_PID"

# Wait for both processes to keep script running
wait $BACKEND_PID $FRONTEND_PID
