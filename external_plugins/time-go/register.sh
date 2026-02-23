#!/usr/bin/env bash
# Register the Time (Go) plugin with HomeClaw Core.
# Run: ./register.sh   (or bash register.sh)
# Requires: Core running (default http://127.0.0.1:9000), curl

CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
PLUGIN_BASE="${PLUGIN_BASE:-http://127.0.0.1:3112}"

curl -s -X POST "${CORE_URL}/api/plugins/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"plugin_id\": \"time-go\",
    \"name\": \"Time Plugin (Go)\",
    \"description\": \"Get current time or list timezones. Use when the user asks what time it is, or the time in a city/country.\",
    \"description_long\": \"Returns current date and time; optional timezone and format (12h/24h). Can list common timezones.\",
    \"health_check_url\": \"${PLUGIN_BASE}/health\",
    \"type\": \"http\",
    \"config\": {
      \"base_url\": \"${PLUGIN_BASE}\",
      \"path\": \"run\",
      \"timeout_sec\": 10
    },
    \"capabilities\": [
      {
        \"id\": \"get_time\",
        \"name\": \"Get current time\",
        \"description\": \"Returns current time; optional timezone and format.\",
        \"parameters\": [
          {\"name\": \"timezone\", \"type\": \"string\", \"required\": false, \"description\": \"IANA timezone, e.g. America/New_York, Asia/Tokyo.\"},
          {\"name\": \"format\", \"type\": \"string\", \"required\": false, \"description\": \"24h (default) or 12h.\"}
        ],
        \"output_description\": \"date and time string\",
        \"post_process\": true,
        \"post_process_prompt\": \"Turn this raw time string into one short, friendly sentence (e.g. 'It is 3:45 PM in New York.').\",
        \"method\": \"POST\",
        \"path\": \"/run\"
      },
      {
        \"id\": \"list_timezones\",
        \"name\": \"List common timezones\",
        \"description\": \"Returns a list of common IANA timezone names.\",
        \"parameters\": [],
        \"post_process\": false,
        \"method\": \"POST\",
        \"path\": \"/run\"
      }
    ]
  }"

echo ""
