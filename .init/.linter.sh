#!/bin/bash
cd /home/kavia/workspace/code-generation/smart-notes-manager-331202-331216/notes_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

