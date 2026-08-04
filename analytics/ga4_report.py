import argparse
import json
from pathlib import Path

import google.auth
import google.auth.transport.requests
import requests

KEY_PATH = Path(__file__).parent.parent / ".secrets" / "ga4-reader-key.json"
PROPERTY_ID = "543844011"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

parser = argparse.ArgumentParser(description="SOJU GA4 페이지별 트래픽 리포트")
parser.add_argument("--start", default="7daysAgo")
parser.add_argument("--end", default="today")
parser.add_argument("--limit", type=int, default=20)
args = parser.parse_args()

creds, _ = google.auth.load_credentials_from_file(str(KEY_PATH), scopes=SCOPES)
creds.refresh(google.auth.transport.requests.Request())

body = {
    "dateRanges": [{"startDate": args.start, "endDate": args.end}],
    "dimensions": [{"name": "pagePath"}],
    "metrics": [
        {"name": "screenPageViews"},
        {"name": "activeUsers"},
        {"name": "sessions"},
    ],
    "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
    "limit": args.limit,
}

r = requests.post(
    f"https://analyticsdata.googleapis.com/v1beta/properties/{PROPERTY_ID}:runReport",
    headers={"Authorization": f"Bearer {creds.token}"},
    json=body,
)
r.raise_for_status()
data = r.json()

for row in data.get("rows", []):
    path = row["dimensionValues"][0]["value"]
    views, users, sessions = (m["value"] for m in row["metricValues"])
    print(f"{path}\tviews={views}\tusers={users}\tsessions={sessions}")

if not data.get("rows"):
    print(json.dumps(data, ensure_ascii=False, indent=2))
