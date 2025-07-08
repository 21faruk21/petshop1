#!/usr/bin/env bash
# Build script for Render

pip install -r requirements.txt

# Create static/uploads directory
mkdir -p static/uploads

# Set environment variable for Render
export RENDER=true

echo "Build completed successfully!"