#!/usr/bin/env bash
# File: build.sh

# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt 