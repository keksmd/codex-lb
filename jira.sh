#!/usr/bin/env bash
set -euo pipefail

JIRA_BASE="https://192.168.214.2:8443"
JIRA_USER="a.markov-buturskiy"
JIRA_PASS="patay228"

# Твои проекты
PROJECTS="SES,XFIVE,AF,ROOT"

# Примерное окно аварии
FROM="2026-03-12 05:00"
TO="2026-03-12 05:30"
FILTER_BY_WINDOW=false

# Кто был assignee/closer при аварийном закрытии
MY_JIRA_USERNAME="a.markov-buturskiy"

# dry-run сначала true
DRY_RUN=true
CACHE_ENABLED=true
CACHE_TTL_SECONDS=300
CACHE_DIR="${HOME}/.cache/jira.sh"
ISSUE_CACHE_DIR="${CACHE_DIR}/issue-history"

api() {
  curl -sk -u "$JIRA_USER:$JIRA_PASS" -H 'Content-Type: application/json' "$@"
}

cache_key_for_jql() {
  local key_source="$1"
  printf '%s' "$key_source" | shasum -a 256 | awk '{print $1}'
}

cache_fresh() {
  local path="$1"
  local now modified age
  now="$(date +%s)"
  modified="$(stat -f %m "$path" 2>/dev/null || echo 0)"
  age=$((now - modified))
  if (( age <= CACHE_TTL_SECONDS )); then
    return 0
  fi
  return 1
}

cache_age_seconds() {
  local path="$1"
  local now modified
  now="$(date +%s)"
  modified="$(stat -f %m "$path" 2>/dev/null || echo 0)"
  echo $((now - modified))
}

get_issue_snapshot_cached() {
  local issue="$1"
  local out_file="$2"
  local issue_cache_file
  issue_cache_file="${ISSUE_CACHE_DIR}/${issue}.json"

  if [[ "$CACHE_ENABLED" == "true" && -f "$issue_cache_file" ]] && cache_fresh "$issue_cache_file"; then
    cp "$issue_cache_file" "$out_file"
    return 0
  fi

  api "${JIRA_BASE}/rest/api/2/issue/${issue}?expand=changelog&fields=comment,status,assignee" > "$out_file"
  if [[ "$CACHE_ENABLED" == "true" ]]; then
    mkdir -p "$ISSUE_CACHE_DIR"
    cp "$out_file" "$issue_cache_file"
  fi
  return 1
}

issue_has_exact_ci_comment() {
  local issue_json="$1"
  if jq -e 'any(.fields.comment.comments[]?; ((.body // "") | gsub("\r"; "") | gsub("^\\s+|\\s+$"; "")) == "CI")' "$issue_json" >/dev/null; then
    return 0
  fi
  return 1
}

count_exact_ci_comments() {
  local issue_json="$1"
  jq -r '[.fields.comment.comments[]? | select(((.body // "") | gsub("\r"; "") | gsub("^\\s+|\\s+$"; "")) == "CI")] | length' "$issue_json"
}

echo "Fetching affected issues by JQL..."
SEARCH_JSON="$(mktemp)"
JQL='comment ~ "CI"'
if [[ "$FILTER_BY_WINDOW" == "true" ]]; then
  JQL="${JQL} AND updated >= \"${FROM}\" AND updated <= \"${TO}\""
fi

CACHE_KEY="$(cache_key_for_jql "${JIRA_BASE}|${JQL}")"
SEARCH_CACHE_FILE="${CACHE_DIR}/search-${CACHE_KEY}.json"
SEARCH_CACHE_HIT=false

if [[ "$CACHE_ENABLED" == "true" && -f "$SEARCH_CACHE_FILE" ]] && cache_fresh "$SEARCH_CACHE_FILE"; then
  cp "$SEARCH_CACHE_FILE" "$SEARCH_JSON"
  SEARCH_CACHE_HIT=true
else
  api \
    --get \
    --data-urlencode "jql=${JQL}" \
    --data-urlencode "maxResults=1000" \
    --data-urlencode "fields=key,status,assignee" \
    "${JIRA_BASE}/rest/api/2/search" > "$SEARCH_JSON"
  if [[ "$CACHE_ENABLED" == "true" ]]; then
    mkdir -p "$CACHE_DIR"
    cp "$SEARCH_JSON" "$SEARCH_CACHE_FILE"
  fi
fi

if jq -e '(.errorMessages // []) | length > 0' "$SEARCH_JSON" >/dev/null; then
  echo "Jira search returned errors:" >&2
  jq -r '.errorMessages[]' "$SEARCH_JSON" >&2
  rm -f "$SEARCH_JSON"
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo
  echo "DRY_RUN=true: reporting affected issues only (no Jira mutations)."
  echo "Projects used: ALL"
  echo "Filter by window: ${FILTER_BY_WINDOW}"
  if [[ "$SEARCH_CACHE_HIT" == "true" ]]; then
    echo "Search cache: hit ($(cache_age_seconds "$SEARCH_CACHE_FILE")s old)"
  else
    echo "Search cache: miss"
  fi
  mapfile -t CANDIDATE_ISSUES < <(jq -r '(.issues // [])[]?.key' "$SEARCH_JSON")
  CANDIDATE_COUNT="${#CANDIDATE_ISSUES[@]}"
  AFFECTED_ISSUES=()
  PLAN_ROWS=()
  ISSUE_CACHE_HITS=0
  ISSUE_CACHE_MISSES=0
  for issue in "${CANDIDATE_ISSUES[@]}"; do
    ISSUE_JSON="$(mktemp)"
    if get_issue_snapshot_cached "$issue" "$ISSUE_JSON"; then
      ISSUE_CACHE_HITS=$((ISSUE_CACHE_HITS + 1))
    else
      ISSUE_CACHE_MISSES=$((ISSUE_CACHE_MISSES + 1))
    fi

    if issue_has_exact_ci_comment "$ISSUE_JSON"; then
      AFFECTED_ISSUES+=("$issue")
      CI_COMMENT_COUNT="$(count_exact_ci_comments "$ISSUE_JSON")"

      CUR_STATUS=$(jq -r '.fields.status.name // empty' "$ISSUE_JSON")

      if [[ "$FILTER_BY_WINDOW" == "true" ]]; then
        LAST_STATUS_EVENT=$(jq -c --arg FROM "$FROM" --arg TO "$TO" '
          .changelog.histories
          | map(select(.created >= $FROM and .created <= $TO))
          | map(select(any(.items[]?; .field=="status")))
          | sort_by(.created)
          | last
        ' "$ISSUE_JSON")
      else
        LAST_STATUS_EVENT=$(jq -c '
          .changelog.histories
          | map(select(any(.items[]?; .field=="status")))
          | sort_by(.created)
          | last
        ' "$ISSUE_JSON")
      fi

      LAST_CLOSER=""
      PREV_STATUS=""
      PREV_ASSIGNEE=""
      if [[ "$LAST_STATUS_EVENT" != "null" && -n "$LAST_STATUS_EVENT" ]]; then
        LAST_CLOSER=$(echo "$LAST_STATUS_EVENT" | jq -r '.author.name // .author.key // .author.displayName // empty')
        PREV_STATUS=$(echo "$LAST_STATUS_EVENT" | jq -r '.items[] | select(.field=="status") | .fromString // empty')
        PREV_ASSIGNEE=$(jq -r --arg EVENT_CREATED "$(echo "$LAST_STATUS_EVENT" | jq -r '.created')" '
          .changelog.histories
          | map(select(.created <= $EVENT_CREATED))
          | map(select(any(.items[]?; .field=="assignee")))
          | sort_by(.created)
          | last
          | .items[]?
          | select(.field=="assignee")
          | .from // empty
        ' "$ISSUE_JSON")
      fi

      DO_ROLLBACK=false
      TARGET_TRANSITION_NAME=""
      if [[ -n "${LAST_CLOSER}" && "${LAST_CLOSER}" == "${MY_JIRA_USERNAME}" ]]; then
        DO_ROLLBACK=true
        TARGET_TRANSITION_NAME="Reopen Issue"
      fi

      PLAN_ROWS+=("${issue}|status=${CUR_STATUS:-<empty>}|rollback=${DO_ROLLBACK}|transition=${TARGET_TRANSITION_NAME:-<none>}|restore_assignee=${PREV_ASSIGNEE:-<none>}|delete_ci_comments=${CI_COMMENT_COUNT}|closed_by=${LAST_CLOSER:-<unknown>}")
    fi
    rm -f "$ISSUE_JSON"
  done

  AFFECTED_COUNT="${#AFFECTED_ISSUES[@]}"
  echo "Candidate issues by JQL: ${CANDIDATE_COUNT}"
  echo "Issue history cache: hit=${ISSUE_CACHE_HITS}, miss=${ISSUE_CACHE_MISSES}"
  echo "Affected issues count (exact CI comment): ${AFFECTED_COUNT}"
  if (( AFFECTED_COUNT > 0 )); then
    printf '%s\n' "${AFFECTED_ISSUES[@]}"
  fi
  if (( ${#PLAN_ROWS[@]} > 0 )); then
    echo
    echo "Plan preview (read-only):"
    printf '%s\n' "${PLAN_ROWS[@]}"
  fi
  rm -f "$SEARCH_JSON"
  exit 0
fi

jq -r '.issues[].key' "$SEARCH_JSON" | while read -r ISSUE; do
  echo
  echo "==== $ISSUE ===="

  ISSUE_JSON="$(mktemp)"
  api "${JIRA_BASE}/rest/api/2/issue/${ISSUE}?expand=changelog" > "$ISSUE_JSON"

  CUR_STATUS=$(jq -r '.fields.status.name' "$ISSUE_JSON")
  CUR_ASSIGNEE=$(jq -r '.fields.assignee.name // .fields.assignee.key // .fields.assignee.displayName // empty' "$ISSUE_JSON")

  # Последнее изменение статуса в окне аварии
  LAST_STATUS_EVENT=$(jq -c --arg FROM "$FROM" --arg TO "$TO" '
    .changelog.histories
    | map(select(.created >= $FROM and .created <= $TO))
    | map(select(any(.items[]?; .field=="status")))
    | sort_by(.created)
    | last
  ' "$ISSUE_JSON")

  if [[ "$LAST_STATUS_EVENT" == "null" || -z "$LAST_STATUS_EVENT" ]]; then
    echo "No status change in target window, only deleting CI comments"
    LAST_CLOSER=""
    PREV_STATUS=""
    PREV_ASSIGNEE=""
  else
    LAST_CLOSER=$(echo "$LAST_STATUS_EVENT" | jq -r '.author.name // .author.key // .author.displayName // empty')
    PREV_STATUS=$(echo "$LAST_STATUS_EVENT" | jq -r '.items[] | select(.field=="status") | .fromString // empty')

    # Ищем assignee ДО этого события
    PREV_ASSIGNEE=$(jq -r --arg EVENT_CREATED "$(echo "$LAST_STATUS_EVENT" | jq -r '.created')" '
      .changelog.histories
      | map(select(.created <= $EVENT_CREATED))
      | map(select(any(.items[]?; .field=="assignee")))
      | sort_by(.created)
      | last
      | .items[]?
      | select(.field=="assignee")
      | .from // empty
    ' "$ISSUE_JSON")
  fi

  echo "Current status:   ${CUR_STATUS}"
  echo "Current assignee: ${CUR_ASSIGNEE:-<empty>}"
  echo "Closed by:        ${LAST_CLOSER:-<unknown>}"
  echo "Prev status:      ${PREV_STATUS:-<unknown>}"
  echo "Prev assignee:    ${PREV_ASSIGNEE:-<unknown>}"

  DO_ROLLBACK=false
  TARGET_TRANSITION_NAME=""

  if [[ -n "${LAST_CLOSER}" && "${LAST_CLOSER}" == "${MY_JIRA_USERNAME}" ]]; then
    DO_ROLLBACK=true
    TARGET_TRANSITION_NAME="Reopen Issue"
  fi

  echo "Rollback:         ${DO_ROLLBACK}"
  echo "Transition:       ${TARGET_TRANSITION_NAME:-<none>}"

  if [[ "$DRY_RUN" == "false" ]]; then
    if [[ "$DO_ROLLBACK" == "true" && -n "$TARGET_TRANSITION_NAME" ]]; then
      TRANSITIONS_JSON="$(mktemp)"
      api "${JIRA_BASE}/rest/api/2/issue/${ISSUE}/transitions" > "$TRANSITIONS_JSON"

      TRANSITION_ID=$(jq -r --arg NAME "$TARGET_TRANSITION_NAME" '
        .transitions[] | select(.name == $NAME) | .id
      ' "$TRANSITIONS_JSON" | head -n1)

      if [[ -n "${TRANSITION_ID}" && "${TRANSITION_ID}" != "null" ]]; then
        echo "Applying transition ${TARGET_TRANSITION_NAME} (${TRANSITION_ID})"
        api -X POST \
          --data "{\"transition\":{\"id\":\"${TRANSITION_ID}\"}}" \
          "${JIRA_BASE}/rest/api/2/issue/${ISSUE}/transitions" >/dev/null
      else
        echo "No transition found: ${TARGET_TRANSITION_NAME}"
      fi

      rm -f "$TRANSITIONS_JSON"

      if [[ -n "${PREV_ASSIGNEE}" ]]; then
        echo "Restoring assignee to ${PREV_ASSIGNEE}"
        api -X PUT \
          --data "{\"name\":\"${PREV_ASSIGNEE}\"}" \
          "${JIRA_BASE}/rest/api/2/issue/${ISSUE}/assignee" >/dev/null || true
      fi
    fi

    COMMENTS_JSON="$(mktemp)"
    api "${JIRA_BASE}/rest/api/2/issue/${ISSUE}/comment" > "$COMMENTS_JSON"

    jq -r '
      .comments[]
      | select(.body == "CI")
      | .id
    ' "$COMMENTS_JSON" | while read -r COMMENT_ID; do
      echo "Deleting comment ${COMMENT_ID}"
      api -X DELETE "${JIRA_BASE}/rest/api/2/issue/${ISSUE}/comment/${COMMENT_ID}" >/dev/null || true
    done

    rm -f "$COMMENTS_JSON"
  fi

  rm -f "$ISSUE_JSON"
done

rm -f "$SEARCH_JSON"
echo
echo "Done."
