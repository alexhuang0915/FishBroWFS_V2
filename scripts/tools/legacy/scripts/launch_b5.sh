#!/bin/bash
# Launch B5 Audit Console (Streamlit)

set -e

# Change to repo root
cd "$(dirname "$0")/.."

# Start Streamlit app
streamlit run ui/app_streamlit.py --server.port 8502

