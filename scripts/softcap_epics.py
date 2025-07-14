import click
import requests
import pandas as pd
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import os
import threading
import time
import sys
from contextlib import contextmanager

@contextmanager
def spinner(message="Processing"):
    stop_spinner = False

    def spin():
        for c in "|/-\\":
            while not stop_spinner:
                for c in "|/-\\":
                    sys.stdout.write(f"\r{message} {c}")
                    sys.stdout.flush()
                    time.sleep(0.1)

    thread = threading.Thread(target=spin)
    thread.start()

    try:
        yield
    finally:
        stop_spinner = True
        thread.join()
        sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")  # clear line


# Load .env secrets
load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
START_DATE_FIELD = "customfield_11801"
END_DATE_FIELD = "customfield_11827"
POD_FIELD = "customfield_11913"

@click.command()
@click.argument('project_key')
@click.option('--month', type=click.Choice(['this', 'last'], case_sensitive=False), default='this',
              help='Which month to search (this or last)')

def fetch_epics(project_key, month):
    """Fetch Epics that changed into or out of 'In Progress' during the given month."""
    if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN]):
        click.echo("Missing environment variables. Check your .env file.")
        return

    if month.lower() == 'last':
        date_range = 'DURING(startOfMonth(-1), startOfMonth())'
    else:
        date_range = 'AFTER startOfMonth()'
    month_range_jql = date_range

    jql = (
        f'project = "{project_key}" AND issuetype = Epic AND '
        f'status WAS "In Progress" {date_range}'
    )

    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
    params = {
        "jql": jql,
        "maxResults": 200,
        "fields": f"summary,status,{START_DATE_FIELD},{END_DATE_FIELD},{POD_FIELD}"
    }

    try:
        response = requests.get(url, headers=headers, auth=auth, params=params)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error fetching epics: {e}")
        return

    issues = response.json().get("issues", [])
    if not issues:
        click.echo("No 'In Progress' epics found for that month.")
        return

    records = []
    for issue in issues:
        key = issue["key"]
        summary = issue["fields"]["summary"]
        status = issue["fields"]["status"]["name"]
        start_date = issue["fields"].get(START_DATE_FIELD, "N/A")
        end_date = issue["fields"].get(END_DATE_FIELD, "N/A")
        pod_field = issue["fields"].get(POD_FIELD)
        pod = pod_field["value"] if pod_field and isinstance(pod_field, dict) else "N/A"
        total_children, done_children = get_child_stats(key, auth, headers, month_range_jql)

        with spinner(f"querying children of {key}"):
            total_children, done_children = get_child_stats(key, auth, headers, month_range_jql)

        if done_children and isinstance(done_children, int) and done_children > 0:
            records.append({
                "Key": key,
                "Summary": summary,
                "Status": status,
                "Start Date": start_date,
                "Done Date" : end_date,
                "Total Tickets": total_children,
                "Total Tickets Complete": done_children,
                "Team" : pod
            })

    df = pd.DataFrame(records)
    pd.set_option('display.max_rows', None)
    df.rename(columns={col: f"[{col}]" for col in df.columns}, inplace=True)
    click.echo(df.to_string(index=False))


def get_child_stats(epic_key, auth, headers, month_range_jql):
    """Returns (total_children, done_children)"""
    base_url = f"{JIRA_BASE_URL}/rest/api/3/search"

    # Count total children
    total_params = {
        "jql": f'"Epic Link" = "{epic_key}"',
        "maxResults": 1
    }

    # Count children moved out of 'In Progress' during timeframe
    done_jql = (
        f'"Epic Link" = "{epic_key}" AND status WAS "In Progress" '
        f'{month_range_jql} AND statusCategory != "In Progress"'
    )
    done_params = {
        "jql": done_jql,
        "maxResults": 1
    }

    try:
        total_resp = requests.get(base_url, headers=headers, auth=auth, params=total_params)
        total_resp.raise_for_status()
        total_count = total_resp.json().get("total", 0)

        done_resp = requests.get(base_url, headers=headers, auth=auth, params=done_params)
        done_resp.raise_for_status()
        done_count = done_resp.json().get("total", 0)

        return total_count, done_count
    except requests.RequestException:
        return "N/A", "N/A"


if __name__ == "__main__":
    fetch_epics()
