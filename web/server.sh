#!/bin/bash

# Memory Recall Web Frontend Launcher
# Usage: ./start.sh [port]

PORT=${1:-3000}

echo "🚀 Starting Memory Recall Web Frontend..."
echo "📁 Web directory: $(pwd)"
echo "🌐 Server: http://localhost:$PORT"
echo "📡 API: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start Python HTTP server
python3 -m http.server $PORT
