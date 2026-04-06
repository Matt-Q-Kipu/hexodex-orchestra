import os
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from requests.auth import HTTPBasicAuth
import helpers.common as c

load_dotenv()
SLACK_TOKEN = os.getenv("BAGEL_CZAR")
DEFAULT_CHANNEL = os.getenv("RD_TEST")

def post_burnup_to_slack(image_path: str, epic_key: str, channel: str = None):
    target_channel = channel if channel else DEFAULT_CHANNEL
    try:
        response = c.slack_upload_file(
            SLACK_TOKEN,
            target_channel,
            image_path,
            title=f"📈 Burnup Chart for {epic_key}",
            initial_comment=" ",
        )
        print("Image posted successfully.")
    except c.SlackApiError as e:
        print(f"Error uploading image to {target_channel}: {e.error}")

        if e.error == "channel_not_found" and target_channel != DEFAULT_CHANNEL:
            print(f"Retrying with default channel: {DEFAULT_CHANNEL}")
            try:
                response = c.slack_upload_file(
                    SLACK_TOKEN,
                    DEFAULT_CHANNEL,
                    image_path,
                    title=f"📈 Burnup Chart for {epic_key}",
                    initial_comment=" ",
                )
                print("Image posted successfully (fallback):", response["file"]["id"])
            except c.SlackApiError as e2:
                print(f"Fallback upload failed: {e2.error}")


def parse_burnup_data(issues, show_progress=False, monthly=False):
    scope_by = defaultdict(int)
    done_by = defaultdict(int)
    progress_by = defaultdict(int) if show_progress else None
    all_dates = set()

    # Statuses that indicate work hasn't started yet
    NOT_STARTED_STATUSES = {"open", "backlog", "to do", "gathering requirements"}

    for issue in issues:
        created_str = issue["fields"]["created"]
        created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        key = created.strftime("%Y-%m") if monthly else created.strftime("%Y-%m-%d")
        scope_by[key] += 1
        all_dates.add(created.date())

        closed_date = None
        progress_date = None
        fallback_progress_date = None
        histories = issue.get("changelog", {}).get("histories", [])
        for hist in histories:
            for item in hist.get("items", []):
                if item.get("field") != "status":
                    continue
                to_status = item.get("toString", "").strip().lower()
                from_status = item.get("fromString", "").strip().lower()
                changed_str = hist.get("created")
                changed = datetime.fromisoformat(changed_str.replace("Z", "+00:00"))
                if to_status in c.CLOSED_STATUSES and not closed_date:
                    closed_date = changed
                if show_progress:
                    # Priority 1: Explicit "In Progress" transition
                    if to_status == "in progress" and not progress_date:
                        progress_date = changed
                    # Priority 2: Fallback - first time leaving not-started status
                    if not fallback_progress_date:
                        if from_status in NOT_STARTED_STATUSES and to_status not in NOT_STARTED_STATUSES:
                            fallback_progress_date = changed

        # Use explicit progress date if found, otherwise use fallback
        if show_progress and not progress_date and fallback_progress_date:
            progress_date = fallback_progress_date

        if closed_date:
            key = closed_date.strftime("%Y-%m") if monthly else closed_date.strftime("%Y-%m-%d")
            done_by[key] += 1
            all_dates.add(closed_date.date())
        if show_progress and progress_date:
            key = progress_date.strftime("%Y-%m") if monthly else progress_date.strftime("%Y-%m-%d")
            progress_by[key] += 1
            all_dates.add(progress_date.date())

    if not all_dates:
        return {"dates": [], "scope": [], "done": [], "progress": [] if show_progress else None}

    start = min(all_dates)
    end = max(all_dates)
    keys = []
    current = start
    while current <= end:
        key = current.strftime("%Y-%m") if monthly else current.strftime("%Y-%m-%d")
        if not keys or keys[-1] != key:
            keys.append(key)
        if monthly:
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)
        else:
            current += timedelta(days=1)

    def cumulative_count(raw_map):
        total = 0
        out = []
        for k in keys:
            total += raw_map.get(k, 0)
            out.append(total)
        return out

    return {
        "dates": keys,
        "scope": cumulative_count(scope_by),
        "done": cumulative_count(done_by),
        "progress": cumulative_count(progress_by) if show_progress else None
    }

def plot_and_post_burnup(epic_key, issues, show_progress=False, monthly=False, channel=None):
    data = parse_burnup_data(issues, show_progress=show_progress, monthly=monthly)

    if not data["dates"]:
        print("No timeline data found.")
        return

    if monthly:
        x_dates = [datetime.strptime(d, "%Y-%m").date() for d in data["dates"]]
    else:
        x_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in data["dates"]]

    scope = data["scope"]
    done = data["done"]
    progress = data.get("progress")

    plt.figure(figsize=(10, 6))
    plt.plot(x_dates, scope, label="Total Scope", linewidth=2)
    plt.plot(x_dates, done, label="Completed", linewidth=2)
    if progress is not None:
        plt.plot(x_dates, progress, label="In Progress", linestyle="--", linewidth=2)

    plt.title(f"Burnup Chart: {epic_key}")
    plt.xlabel("Date")
    plt.ylabel("Tickets")

    max_y = max(scope) if scope is not None else 0
    plt.ylim(bottom=0, top=max_y + 1)
    plt.yticks(range(0, int(max_y) + 2))

    ax = plt.gca()
    # Set sensible x-axis limits based on actual data
    if len(x_dates) > 0:
        min_date = min(x_dates)
        max_date = max(x_dates)

        # Add padding: 7 days before and after for single/short date ranges
        if len(x_dates) <= 7:
            padding = timedelta(days=7)
        else:
            # For longer ranges, add 5% padding on each side
            date_range = (max_date - min_date).days
            padding = timedelta(days=max(7, int(date_range * 0.05)))

        plt.xlim(min_date - padding, max_date + padding)

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.xticks(rotation=45)

    plt.grid(True, linestyle=":")
    plt.legend()
    plt.tight_layout()

    outpath = "img/burnup.png"
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    plt.savefig(outpath)
    plt.close()

    post_burnup_to_slack(outpath, epic_key, channel)

@c.click.command()
@c.click.argument("epic_key")
@c.click.option("-p", "--progress", is_flag=True, help="Include a line for when tickets first moved to 'In Progress'.")
@c.click.option("-c", "--channel", default=None, help="Slack channel ID to post the chart into.")
def main(epic_key, progress, channel):
    auth = HTTPBasicAuth(c.JIRA_EMAIL, c.JIRA_TOKEN)
    base_url = c.JIRA_BASE_URL
    target_channel = channel or DEFAULT_CHANNEL

    issue_url = f"{base_url}/rest/api/3/issue/{epic_key}"
    headers = {"Accept": "application/json"}

    resp = c.requests.get(issue_url, headers=headers, auth=auth)
    if resp.status_code != 200:
        c.slack_post_message(SLACK_TOKEN, target_channel, f"⚠️ Jira issue `{epic_key}` not found.")
        return
    issue = resp.json()
    issue_type = issue.get("fields", {}).get("issuetype", {}).get("name", "").strip()
    if issue_type.lower() != "epic":
        c.slack_post_message(SLACK_TOKEN, target_channel, f"⚠️ `{epic_key}` is a {issue_type}. Burnup chart can only run for Epics.")
        return

    jql = f'"Epic Link" = "{c.escape_jql_value(epic_key)}" ORDER BY created ASC'
    issues = c.jira_search(
        jql,
        fields=["summary", "status", "created", "resolutiondate"],
        expand=["changelog"],
        auth=auth,
        base_url=base_url
    )

    if not issues:
        c.slack_post_message(SLACK_TOKEN, target_channel, f"⚠️ No child issues found for epic `{epic_key}`.")
        return

    plot_and_post_burnup(epic_key, issues, show_progress=progress, channel=channel)

if __name__ == "__main__":
    main()
