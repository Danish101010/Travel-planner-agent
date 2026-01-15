#!/usr/bin/env bash
# Loads API keys from api-keys into the current shell session.
# Supports ordered values or KEY=VALUE entries (same rules as PowerShell script).
# Usage: source ./load-api-keys.sh

set -euo pipefail
shopt -s extglob

api_file="api-keys"

if [[ ! -f "$api_file" ]]; then
  echo "api-keys file not found in the current directory." >&2
  return 1 2>/dev/null || exit 1
fi

mapfile -t raw_lines < "$api_file" || true
if [[ ${#raw_lines[@]} -eq 0 ]]; then
  echo "api-keys file is empty." >&2
  return 1 2>/dev/null || exit 1
fi

lines=()
for line in "${raw_lines[@]}"; do
  trimmed="${line##+([[:space:]])}"
  trimmed="${trimmed%%+([[:space:]])}"
  [[ -z "$trimmed" ]] && continue
  [[ "$trimmed" == \#* ]] && continue
  lines+=("$trimmed")
 done

if [[ ${#lines[@]} -lt 2 ]]; then
  echo "api-keys must contain at least two values (Tavily, Google)." >&2
  return 1 2>/dev/null || exit 1
fi

ordered_values=()
for entry in "${lines[@]}"; do
  if [[ "$entry" =~ ^[A-Za-z0-9_]+\s*= ]]; then
    key="${entry%%=*}"
    value="${entry#*=}"
    key="${key//[[:space:]]/}"
    value="${value##+([[:space:]])}"
    value="${value%%+([[:space:]])}"
    export "$key=$value"
  else
    ordered_values+=("$entry")
  fi
 done

ordered_index=0
get_next_ordered_value() {
  if [[ $ordered_index -ge ${#ordered_values[@]} ]]; then
    echo ""
    return 0
  fi
  local value="${ordered_values[$ordered_index]}"
  ordered_index=$((ordered_index + 1))
  echo "$value"
}

resolve_value() {
  local name="$1"
  local required="$2"
  local current="${!name-}"
  if [[ -n "$current" ]]; then
    echo "$current"
    return 0
  fi
  local value
  value="$(get_next_ordered_value)"
  if [[ "$required" == "true" && -z "$value" ]]; then
    echo "Missing value for $name in api-keys." >&2
    return 1
  fi
  echo "$value"
}

key_plan=(
  "TAVILY_API_KEY:true:Research agent (Tavily)"
  "GOOGLE_API_KEY:true:Gemma itinerary model"
  "GEOAPIFY_API_KEY:false:Autocomplete & POIs"
  "TRAVELPAYOUTS_TOKEN:false:TravelPayouts fares"
  "IRCTC_RAPIDAPI_KEY:false:Indian Rail fares"
  "IRCTC_RAPIDAPI_HOST:false:RapidAPI host override"
)

for entry in "${key_plan[@]}"; do
  IFS=':' read -r name required description <<< "$entry"
  value="$(resolve_value "$name" "$required")" || { return 1 2>/dev/null || exit 1; }
  if [[ -n "$value" ]]; then
    export "$name=$value"
  fi
 done

echo "Environment variables set for this shell session:"
for entry in "${key_plan[@]}"; do
  IFS=':' read -r name required description <<< "$entry"
  current="${!name-}"
  if [[ -n "$current" ]]; then
    echo "  $name (length): ${#current} - $description"
  elif [[ "$required" == "true" ]]; then
    echo "  $name: NOT SET (required)"
  else
    echo "  $name: not set ($description disabled)"
  fi
 done

echo "Run your app in this same terminal (e.g., 'python api.py')."
