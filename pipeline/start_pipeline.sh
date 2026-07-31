#!/bin/bash
echo "🚀 Starting GNTV 24/7 Automated News Pipeline..."

cd "$(dirname "$0")"

# Run the orchestrator
python3 pipeline_orchestrator.py
