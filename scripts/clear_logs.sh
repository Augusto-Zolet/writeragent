#!/bin/bash
# Clear all WriterAgent log files in every known location.
# Filenames: writeragent_debug.log, writeragent_agent.log (see core/logging.py).

LO="${HOME}/.config/libreoffice"
rm -f \
  "${HOME}/writeragent_debug.log" \
  "${HOME}/writeragent_agent.log" \
  "${LO}/4/user/writeragent_debug.log" \
  "${LO}/4/user/writeragent_agent.log" \
  "${LO}/4/user/config/writeragent_debug.log" \
  "${LO}/4/user/config/writeragent_agent.log" \
  "${LO}/24/user/writeragent_debug.log" \
  "${LO}/24/user/writeragent_agent.log" \
  "${LO}/24/user/config/writeragent_debug.log" \
  "${LO}/24/user/config/writeragent_agent.log"
echo "Logs deleted."
