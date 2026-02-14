#!/bin/bash
cd /home/rpi/ai-engine/design-library-indexer
/home/rpi/ai-engine/venv/bin/python run_indexer.py search "$@"
