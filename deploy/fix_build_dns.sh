#!/bin/bash
# Thin wrapper around fix_build_dns.py -- see that file's docstring for
# what this does and why. Run from the repo root:
#   deploy/fix_build_dns.sh

set -eu
cd "$(dirname "$0")/.."
python3 deploy/fix_build_dns.py
