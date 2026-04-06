A home for misfit scripts — and a coding companion who doesn't like the rain. 

## What's here

### Burnup Charts (`scripts/burnup_slack.py`)
Generates burnup charts for Jira Epics and posts them to Slack. Triggered via GitHub Actions workflow dispatch.

### Claude Buddy (`.claude/skills/buddy/`)
A coding companion that lives in your terminal. Packaged as a [Claude Code skill](https://github.com/anthropics/skills).

**Privacy note:** The optional weather feature (`/buddy weather on`) uses [ipinfo.io](https://ipinfo.io) for IP-based geolocation and [Open-Meteo](https://open-meteo.com) for weather data. No API keys are required; no data is stored remotely.

## License

This project is licensed under the MIT License. See LICENSE for more details.
