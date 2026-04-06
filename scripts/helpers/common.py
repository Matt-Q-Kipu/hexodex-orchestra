import os
import click
import requests
from dotenv import load_dotenv

# ENVIRONMENT VARIABLES
load_dotenv()
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

# CLOSED STATUS VALUES (case-insensitive)
CLOSED_STATUSES = {s.casefold() for s in {
    "Closed",
    "Done"
}}

def escape_jql_value(value: str) -> str:
    """Escape a value for safe interpolation into JQL queries."""
    return value.replace('"', '\\"')

def jira_search(jql, fields=None, expand=None, max_results=100, auth=None, base_url=None, headers=None):
    if not base_url or not auth:
        raise ValueError("jira_search requires base_url and auth")

    url = f"{base_url}/rest/api/3/search/jql"
    headers = headers or {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    body = {
        "jql": jql,
        "maxResults": max_results,
    }
    if fields:
        body["fields"] = fields
    if expand:
        body["expand"] = expand if isinstance(expand, str) else ",".join(expand)

    all_issues = []
    while True:
        resp = requests.post(url, headers=headers, auth=auth, json=body)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        if not issues:
            break
        all_issues.extend(issues)

        next_token = data.get("nextPageToken")
        if not next_token:
            break
        body["nextPageToken"] = next_token

    return all_issues


# ── Slack Web API helpers (direct HTTP via requests, no SDK) ──────────

SLACK_API_BASE = "https://slack.com/api"


class SlackApiError(Exception):
    """Raised when a Slack Web API call returns ok=false."""
    def __init__(self, error):
        self.error = error
        super().__init__(error)


def _slack_headers(token):
    return {"Authorization": f"Bearer {token}"}


def slack_post_message(token, channel, text):
    headers = {**_slack_headers(token), "Content-Type": "application/json"}
    resp = requests.post(
        f"{SLACK_API_BASE}/chat.postMessage",
        headers=headers,
        json={"channel": channel, "text": text},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise SlackApiError(data.get("error", "unknown_error"))
    return data


def slack_upload_file(token, channel, file_path, title=None, initial_comment=None):
    headers = _slack_headers(token)
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    # Step 1: Get an upload URL from Slack
    resp = requests.get(
        f"{SLACK_API_BASE}/files.getUploadURLExternal",
        headers=headers,
        params={"filename": filename, "length": file_size},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise SlackApiError(data.get("error", "unknown_error"))
    upload_url = data["upload_url"]
    file_id = data["file_id"]

    # Step 2: Upload the file to the provided URL
    with open(file_path, "rb") as f:
        resp = requests.post(upload_url, files={"file": (filename, f)})
    resp.raise_for_status()

    # Step 3: Complete the upload and share to the channel
    complete_payload = {
        "files": [{"id": file_id, "title": title or filename}],
        "channel_id": channel,
    }
    if initial_comment:
        complete_payload["initial_comment"] = initial_comment
    resp = requests.post(
        f"{SLACK_API_BASE}/files.completeUploadExternal",
        headers={**headers, "Content-Type": "application/json"},
        json=complete_payload,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise SlackApiError(data.get("error", "unknown_error"))
    return data
