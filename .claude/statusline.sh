#!/bin/bash

# Read JSON input from stdin
input=$(cat)

# Extract data
model=$(echo "$input" | jq -r '.model.display_name')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
input_tokens=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
output_tokens=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')

# Format tokens to human-readable (k for thousands)
format_tokens() {
    local tokens=$1
    if [ "$tokens" -ge 1000 ]; then
        awk "BEGIN {printf \"%.1fk\", $tokens/1000}"
    else
        echo "$tokens"
    fi
}

input_fmt=$(format_tokens "$input_tokens")
output_fmt=$(format_tokens "$output_tokens")

# Build status line
status="$model"

# Add context window usage with progress bar if available
if [ -n "$used_pct" ]; then
    bar_width=20
    filled=$(awk "BEGIN {printf \"%.0f\", $used_pct * $bar_width / 100}")
    empty=$((bar_width - filled))

    bar=""
    for ((i=0; i<filled; i++)); do bar="${bar}█"; done
    for ((i=0; i<empty; i++)); do bar="${bar}░"; done

    status="$status | Context: [$bar] $(printf '%.0f' "$used_pct")%"
fi

# Add token counts
status="$status | In: $input_fmt Out: $output_fmt"

echo "$status"
