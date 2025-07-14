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
        while not stop_spinner:
            for c in "|/-\\":
                styled_msg = click.style(f"{message} {c}", fg="yellow")
                sys.stdout.write(f"\r{styled_msg}")
                sys.stdout.flush()
                time.sleep(0.1)

    thread = threading.Thread(target=spin)
    thread.start()

    try:
        yield
    finally:
        stop_spinner = True
        thread.join()
        sys.stdout.write("\r" + " " * (len(message) + 10) + "\r")  # clear line

load_dotenv()
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
START_DATE_FIELD = "customfield_11801"
END_DATE_FIELD = "customfield_11827"
POD_FIELD = "customfield_11913"
DEFAULT_PROJECTS = [p.strip() for p in os.getenv("DEFAULT_JIRA_PROJECTS", "").split(",") if p.strip()]

@click.command()
@click.option('--month', default='this', help='Choose "this" or "last" for timeframe.')
@click.option('--project', default=None, help='Jira project key (e.g., EMR)')
@click.option('--pod', default=None, help='Filter results by team (e.g., Platform)')


def fetch_epics(month, project, pod):
    start_time = time.time()
    if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN]):
        click.echo("Missing environment variables. Check your .env file.")
        return

    projects = [project] if project else DEFAULT_PROJECTS
    if not projects:
        click.echo("No project specified and DEFAULT_JIRA_PROJECTS is empty.")
        return

    date_range = 'DURING(startOfMonth(-1), startOfMonth())' if month.lower() == 'last' else 'AFTER startOfMonth()'
    month_range_jql = date_range

    project_clause = " OR ".join([f'project = "{p}"' for p in projects])
    jql = f'({project_clause}) AND issuetype = Epic AND status WAS "In Progress" {date_range}'

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
        if response.status_code == 400:
            click.echo("Jira returns 400 - possibly not a valid project key.")
            return
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            click.echo(f"Error fetching epics: {e}")
            return

    except requests.exceptions.RequestException as e:
        click.echo(f"Error fetching epics: {e}")
        return

    issues = response.json().get("issues", [])
    if not issues:
        click.echo("No epics found matching the criteria.")
        return

    records = []
    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]
        pod_field = fields.get(POD_FIELD)
        team = pod_field["value"] if pod_field and isinstance(pod_field, dict) and "value" in pod_field else "N/A"

        if pod and team != pod:
            continue

        with spinner(f"Querying children of epic: {key}"):
            total_children, done_children = get_child_stats(key, auth, headers, month_range_jql)

        if done_children and isinstance(done_children, int) and done_children > 0:
            records.append({
                "Key": key,
                "Summary": fields.get("summary", "N/A"),
                "Status": fields.get("status", {}).get("name", "N/A"),
                "Start Date": fields.get(START_DATE_FIELD, "N/A"),
                "End Date": fields.get(END_DATE_FIELD, "N/A"),
                "Total Tickets": total_children,
                "Total Tickets Complete": done_children,
                "Team": team
            })

    df = pd.DataFrame(records)
    pd.set_option('display.max_rows', None)

    if not df.empty:
        df.sort_values(by=["Team", "Key"], inplace=True)
        df.rename(columns={col: f"[{col}]" for col in df.columns}, inplace=True)


        df_lines = df.to_string(index=False).splitlines()
        header = df_lines[0]
        rows = df_lines[1:]
        separator = "-" * len(header)

        click.echo(click.style(separator, fg="cyan", bold=True))
        click.echo(header)
        click.echo(click.style(separator, fg="cyan", bold=True))
        for line in rows:
            click.echo(line)
        click.echo(click.style(separator, fg="cyan", bold=True))




        # Print summary stats
        start_label = "startOfMonth()" if month.lower() == "this" else "startOfMonth(-1)"
        end_label = "" if month.lower() == "this" else "to startOfMonth()"
        click.echo(click.style("\n--- Summary ---", bold=True, fg="cyan"))
        click.echo(f"Timeframe: " + click.style(f"{start_label} {end_label}".strip(), fg="yellow"))
        click.echo(f"Total Epics: " + click.style(f"{len(df)}", bold=True, fg="green"))
        click.echo(f"Total Completed Child Tickets: " + click.style(f"{df['[Total Tickets Complete]'].sum()}", bold=True, fg="green"))
        elapsed_time = time.time() - start_time
        click.echo(f"Runtime: " + click.style(f"{elapsed_time:.2f} seconds", fg="magenta"))

    else:
        click.echo("No matching epics with completed children.")

def get_child_stats(epic_key, auth, headers, month_range_jql):
    base_url = f"{JIRA_BASE_URL}/rest/api/3/search"

    total_params = {
        "jql": f'"Epic Link" = "{epic_key}"',
        "maxResults": 1
    }

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
