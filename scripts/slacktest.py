from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import os

# Load variables from .env file
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("BAGEL_CZAR")
CHANNEL = os.getenv("CHANNEL_ID")

client = WebClient(token=SLACK_BOT_TOKEN)

def post_message():
    try:
        response = client.chat_postMessage(
            channel=CHANNEL,
            text=":sparkles: This is a test message from your local script, happy birthday!! :birthday-cake:",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🎼 Hexodex sound check. Testing one two..."
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Sent via `slacktest.py`"
                        }
                    ]
                }
            ]
        )
        print("Message sent successfully:", response["ts"])
    except SlackApiError as e:
        print(f"Error posting to Slack: {e.response['error']}")

if __name__ == "__main__":
    post_message()

