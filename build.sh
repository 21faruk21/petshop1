#!/usr/bin/env bash
# Build script for Render

pip install -r requirements.txt

# Create instance directory
mkdir -p instance

# Initialize database
python init_db.py

# Create static/uploads directory
mkdir -p static/uploads