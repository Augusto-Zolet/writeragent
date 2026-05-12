#!/usr/bin/env bash
# Render the Grammar Realtime Flow diagram to PNG
# Requires: mmdc (Mermaid CLI) - install via: npm install -g @mermaid-js/mermaid-cli

OUTPUT_FILE="${1:-Showcase/grammar_realtime_flow.png}"
WIDTH="${2:-2400}"
HEIGHT="${3:-1800}"

# Generate Mermaid, clean it up for mmdc, then render to PNG
python scripts/generate_grammar_realtime_flow_diagram.py mermaid 2>/dev/null \
    | sed 's/&quot;/\x27/g' \
    | sed 's/<br>//g' \
    | sed "s/&#39;/'/g" \
    | sed 's/&#34;/"/g' \
    | sed 's/--- \([^|]*\) -->/-- \1 -->/g' \
    | sed 's/---$/--/g' \
    | sed 's/User types LO calls doProofreading/User types, LO calls doProofreading/g' \
    | mmdc -i - -o "$OUTPUT_FILE" -w "$WIDTH" -H "$HEIGHT" --backgroundColor transparent

echo "Generated: $OUTPUT_FILE ($WIDTH x $HEIGHT)"
