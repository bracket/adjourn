#!/bin/bash
# Wrapper script to set SWI-Prolog environment variables before running the demo

export LD_LIBRARY_PATH=/snap/swi-prolog/110/usr/lib:/snap/swi-prolog/110/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
export PATH=/snap/swi-prolog/current/usr/bin:$PATH

cd "$(dirname "$0")"
python3 demo.py "$@"
