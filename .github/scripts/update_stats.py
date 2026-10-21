"""GA4 방문자 수 → stats.json (index.html 방문 카운터가 읽음).

키: env GA4_SA_KEY(서비스계정 JSON 문자열, GitHub secret) 없으면 report/analytics/service-account.json.
GA4는 당일 집계가 늦으므로 '어제'와 '누적'(어제까지)만 기록.
"""
import datetime
import json
import os
import pathlib

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

ROOT = pathlib.Path(__file__).resolve().parents[2]
GA4_PROPERTY_ID = "543844011"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
KST = datetime.timezone(datetime.timedelta(hours=9))


def users(session, start):
    resp = session.post(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY_ID}:runReport",
        json={"dateRanges": [{"startDate": start, "endDate": "yesterday"}],
              "metrics": [{"name": "totalUsers"}],
              # 실제 도메인만 — 로컬 서버(localhost) 미리보기 제외
              "dimensionFilter": {"filter": {"fieldName": "hostName",
                                             "stringFilter": {"matchType": "ENDS_WITH", "value": "kro.kr"}}}},
    )
    resp.raise_for_status()
    rows = resp.json().get("rows", [])
    return int(rows[0]["metricValues"][0]["value"]) if rows else 0


def main():
    raw = os.environ.get("GA4_SA_KEY")
    info = json.loads(raw) if raw else json.loads((ROOT / "report/analytics/service-account.json").read_text(encoding="utf-8"))
    session = AuthorizedSession(service_account.Credentials.from_service_account_info(info, scopes=SCOPES))
    stats = {
        "date": (datetime.datetime.now(KST) - datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        "yesterday": users(session, "yesterday"),
        "total": users(session, "2020-01-01"),
    }
    (ROOT / "stats.json").write_text(json.dumps(stats) + "\n", encoding="utf-8")
    print(stats)


if __name__ == "__main__":
    main()
