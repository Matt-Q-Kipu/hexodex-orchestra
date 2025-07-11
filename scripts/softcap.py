import pandas as pd
import json

from datetime import datetime
import pytz
tz = pytz.timezone("America/New_York")

import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

import click
@click.command(help="Helper script for the Software Capitalization process.")
@click.option('--input','-f', default="kipusystem.xlsx", help="<input_filename>")
@click.option('--output','-o', default="output_data.json", help="<output_filename>")


def reticulate_splines(input,output):
    print('reticulating splines...')

    name_col = 'Name'
    label = 'Department'
    label_filters = ['DEVELOPMENT','DEV OPS','PRODUCT TEAM','QUALITY ASSURANCE','RCM PRODUCT']

    df = pd.read_excel(input)
    df[label] = df[label].str.strip().str.upper()
    filtered_df = df[df[label].isin(label_filters)].copy()
    filtered_df.loc[:, name_col] = filtered_df[name_col].apply(flip_name)

    now = datetime.now(tz)
    timestamp = now.strftime("%Y-%m-%d %I:%M %p ET")

    output_json = {
        "timestamp": timestamp,
        "jira_projects": ["PF", "EMR","CRM","ECAL","KCI","AO","INN","KPUI","KCOM","ANA"],
        "team": [
            {
	        "name": row[name_col],
                "department": row[label],
                "pod": ""
            }
            for _, row in filtered_df.iterrows()
        ]
    }

    with open(output, 'w') as f:
        json.dump(output_json, f, indent=2)

    print('done. (see: '+output+')')


def flip_name(name):
    parts = [part.strip() for part in name.split(',')]
    return f"{parts[1]} {parts[0]}" if len(parts) == 2 else name


if __name__ == '__main__':
    reticulate_splines()
