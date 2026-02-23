#!/usr/bin/env bash
# Register the Quote (Java) plugin with HomeClaw Core.
# Run: ./register.sh   (or bash register.sh)
# Requires: Core running (default http://127.0.0.1:9000), curl

CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
PLUGIN_BASE="${PLUGIN_BASE:-http://127.0.0.1:3113}"

curl -s -X POST "${CORE_URL}/api/plugins/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"plugin_id\": \"quote-java\",
    \"name\": \"Quote Plugin (Java)\",
    \"description\": \"Get a random inspirational quote, or by topic. Use when the user asks for a quote, motivation, or inspiration.\",
    \"description_long\": \"Returns random quotes; optional topic (motivation, success, dreams) and style (short/long).\",
    \"health_check_url\": \"${PLUGIN_BASE}/health\",
    \"type\": \"http\",
    \"config\": {
      \"base_url\": \"${PLUGIN_BASE}\",
      \"path\": \"run\",
      \"timeout_sec\": 10
    },
    \"capabilities\": [
      {
        \"id\": \"get_quote\",
        \"name\": \"Get random quote\",
        \"description\": \"Returns a random inspirational quote. Core will add a brief reflection (post_process).\",
        \"parameters\": [
          {\"name\": \"style\", \"type\": \"string\", \"required\": false, \"description\": \"Output style: short or long.\"}
        ],
        \"output_description\": \"quote and author string\",
        \"post_process\": true,
        \"post_process_prompt\": \"The user received this quote. Add one short sentence (under 15 words) that reflects why this quote matters. Do not repeat the quote.\",
        \"method\": \"POST\",
        \"path\": \"/run\"
      },
      {
        \"id\": \"get_quote_by_topic\",
        \"name\": \"Get quote by topic\",
        \"description\": \"Returns a random quote filtered by topic (e.g. motivation, success, dreams).\",
        \"parameters\": [
          {\"name\": \"topic\", \"type\": \"string\", \"required\": true, \"description\": \"Topic: motivation, success, innovation, dreams, perseverance.\"},
          {\"name\": \"style\", \"type\": \"string\", \"required\": false, \"description\": \"Output style: short or long.\"}
        ],
        \"post_process\": false,
        \"method\": \"POST\",
        \"path\": \"/run\"
      }
    ]
  }"

echo ""
