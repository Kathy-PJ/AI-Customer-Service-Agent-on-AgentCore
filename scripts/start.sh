#!/bin/sh
# Start Bedrock cache proxy sidecar + Python agent
#
# The proxy intercepts Claude Code CLI's Bedrock API calls and injects
# cache_control markers with 1h TTL for prompt caching.

set -e

# Start proxy in background
echo "Starting Bedrock cache proxy (TTL=${CACHE_TTL:-1h})..."
bedrock-effort-proxy &
PROXY_PID=$!

# Wait for proxy to be ready
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf http://127.0.0.1:8888/health > /dev/null 2>&1; then
        echo "Proxy ready (pid=$PROXY_PID)"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "WARNING: Proxy not responding after 10s, starting agent anyway"
    fi
    sleep 1
done

# Start agent (foreground)
echo "Starting agent..."
exec python -m agent.runtime
