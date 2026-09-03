#!/usr/bin/env python3
"""
Google News RSS("소주" 검색)에서 최근 뉴스를 가져와 guide.html 둘러보기 탭의
뉴스 게시판(.bv-news-board)을 자동 갱신한다.

GitHub Actions에서 매일 실행(.github/workflows/update-news.yml).
수동 실행: python .github/scripts/update_news_clippings.py

실패해도(네트워크 오류, RSS 0건 등) guide.html은 건드리지 않고 조용히 종료 —
정적 사이트라 이 스크립트가 죽어도 사이트 자체는 항상 마지막 정상 상태를 유지.
"""
import datetime
import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

KST = datetime.timezone(datetime.timedelta(hours=9))  # 크론이 21:00 UTC(=06:00 KST 다음날)에 도는데
# datetime.date.today()는 러너의 UTC 시각을 쓰므로 라벨이 매번 KST 기준 하루 전으로 찍히는 버그가 있었음(26.08.18)

GUIDE_HTML = 'guide.html'
QUERY_TERM = '소주'
DAYS_BACK = 30
TARGET_COUNT = 10
SIM_THRESHOLD = 0.12  # 이 이상이면 같은 사건으로 보고 제외(제목 문자 바이그램 자카드 유사도) — 실측상 같은 사건 재보도는 0.14~0.6대, 서로 다른 사건은 0~0.03대로 갈림(26.08.13 실데이터로 보정)

# Google News RSS의 <source> 태그가 매체명 대신 그냥 도메인을 줄 때가 있어서
# (kmib.co.kr, hani.co.kr 등 — 같은 도메인이어도 요청마다 매체명/도메인이 오락가락함,
# 26.08.13 실제로 확인) 알려진 도메인은 여기서 한글 매체명으로 보정한다.
DOMAIN_NAME_FALLBACK = {
    'kmib.co.kr': '국민일보', 'hani.co.kr': '한겨레', 'daum.net': '다음뉴스',
    'v.daum.net': '다음뉴스', 'news.naver.com': '네이버뉴스', 'n.news.naver.com': '네이버뉴스',
    'chosun.com': '조선일보', 'joongang.co.kr': '중앙일보', 'joins.com': '중앙일보',
    'donga.com': '동아일보', 'hankookilbo.com': '한국일보', 'hankyung.com': '한국경제',
    'mk.co.kr': '매일경제', 'seoul.co.kr': '서울신문', 'heraldcorp.com': '헤럴드경제',
    'edaily.co.kr': '이데일리', 'asiae.co.kr': '아시아경제', 'newsis.com': '뉴시스',
    'yna.co.kr': '연합뉴스', 'imbc.com': 'MBC', 'kbs.co.kr': 'KBS', 'sbs.co.kr': 'SBS',
    'ytn.co.kr': 'YTN', 'nocutnews.co.kr': '노컷뉴스', 'ohmynews.com': '오마이뉴스',
    'pressian.com': '프레시안', 'khan.co.kr': '경향신문', 'mt.co.kr': '머니투데이',
    'fnnews.com': '파이낸셜뉴스', 'newspim.com': '뉴스핌', 'news1.kr': '뉴스1',
    'kormedi.com': '코메디닷컴', 'insight.co.kr': '인사이트', 'senews.kr': '사회적경제뉴스',
    'm-i.kr': '매일일보', 'sisajournal-e.com': '시사저널e', 'foodtoday.or.kr': '푸드투데이',
    'newsis.co.kr': '뉴시스', 'sports.khan.co.kr': '스포츠경향', 'sportskhan.co.kr': '스포츠경향',
    'jtbc.co.kr': 'JTBC', 'mbn.co.kr': 'MBN', 'chosunbiz.com': '조선비즈', 'dailian.co.kr': '데일리안',
    'newdaily.co.kr': '뉴데일리', 'segye.com': '세계일보', 'munhwa.com': '문화일보',
    'kukinews.com': '쿠키뉴스', 'ajunews.com': '아주경제', 'etnews.com': '전자신문',
    'zdnet.co.kr': 'ZDNet Korea', 'g-enews.com': '글로벌이코노믹', 'starnewskorea.com': '스타뉴스',
    'osen.co.kr': 'OSEN', 'sportsseoul.com': '스포츠서울', 'xportsnews.com': '엑스포츠뉴스',
    'wikitree.co.kr': '위키트리', 'polinews.co.kr': '폴리뉴스',
    'bizwatch.co.kr': '비즈워치', 'nate.com': '네이트뉴스', 'foodnews.news': '푸드뉴스',
    'bntnews.co.kr': 'BNT뉴스', 'economist.co.kr': '이코노미스트',
    'cctoday.co.kr': '충청투데이', 'animalplanet.co.kr': '애니멀플래닛',
    'investing.com': 'Investing.com', 'voi.id': 'VOI',
    'newsiesports.com': '뉴스아이이에스', 'haveagood-holiday.com': 'Holiday Travel',
    'sisaon.co.kr': '시사오늘',
}


def resolve_source_name(source, source_url):
    domain = ''
    if source_url:
        domain = re.sub(r'^https?://(www\.|m\.|v\.)?', '', source_url).split('/')[0].lower()
    looks_like_domain = bool(re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', source, re.I))
    if not looks_like_domain:
        return source
    for known_domain, name in DOMAIN_NAME_FALLBACK.items():
        if domain == known_domain or domain.endswith('.' + known_domain):
            return name
    return source


def fetch_rss(days_back):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)).strftime('%Y-%m-%d')
    q = urllib.parse.quote(f'{QUERY_TERM} after:{since}')
    url = f'https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_items(xml_bytes, cutoff):
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.findall('.//item'):
        title = (it.findtext('title') or '').strip()
        link = (it.findtext('link') or '').strip()
        pub = (it.findtext('pubDate') or '').strip()
        src_el = it.find('source')
        source = (src_el.text or '').strip() if src_el is not None else ''
        source_url = src_el.get('url') if src_el is not None else ''
        if not (title and link and pub and source):
            continue
        suffix = f' - {source}'
        if title.endswith(suffix):
            title = title[: -len(suffix)]
        source = resolve_source_name(source, source_url)
        if QUERY_TERM not in title:
            continue  # 본문에만 매칭되고 제목엔 '소주'가 없는 관련 낮은 결과 제외
        try:
            dt = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            continue
        if dt < cutoff:
            continue
        items.append({'title': title, 'link': link, 'source': source, 'date': dt})
    return items


def norm_bigrams(s):
    s = re.sub(r'[^\w가-힣]', '', s)
    return set(s[i:i + 2] for i in range(len(s) - 1))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe(items, target_count, threshold):
    items = sorted(items, key=lambda x: x['date'], reverse=True)
    kept, kept_grams = [], []
    for it in items:
        grams = norm_bigrams(it['title'])
        if any(jaccard(grams, g) >= threshold for g in kept_grams):
            continue
        kept.append(it)
        kept_grams.append(grams)
        if len(kept) >= target_count:
            break
    return kept


def render_li(it):
    title = html.escape(it['title'])
    source = html.escape(it['source'])
    date = it['date'].astimezone(datetime.timezone.utc).strftime('%Y.%m.%d')
    link = html.escape(it['link'], quote=True)
    return (
        f'<li class="bv-news-item"><a href="{link}" target="_blank" rel="noopener">'
        f'<span class="bv-news-title">{title}</span>'
        f'<span class="bv-news-meta"><span class="bv-news-source">{source}</span>'
        f'<span class="bv-news-date">{date}</span></span></a></li>'
    )


def patch_guide_html(items):
    with open(GUIDE_HTML, encoding='utf-8') as f:
        text = f.read()

    board_pat = re.compile(r'(<ul class="bv-news-board">\n).*?(\n</ul>)', re.DOTALL)
    if not board_pat.search(text):
        raise SystemExit('bv-news-board 블록을 못 찾음 — guide.html 구조가 바뀌었는지 확인할 것')
    new_body = '\n'.join(render_li(it) for it in items)
    text = board_pat.sub(lambda m: m.group(1) + new_body + m.group(2), text, count=1)

    today = datetime.datetime.now(KST).strftime('%Y.%m.%d')
    label_pat = re.compile(r'(<h2>소주 뉴스 클리핑</h2>\n<span>)[^<]*(</span>)')
    if not label_pat.search(text):
        raise SystemExit('뉴스 게시판 라벨(<span>)을 못 찾음 — guide.html 구조가 바뀌었는지 확인할 것')
    text = label_pat.sub(rf'\g<1>Google News 자동 수집 · {today} 갱신\g<2>', text, count=1)

    with open(GUIDE_HTML, encoding='utf-8') as f:
        original = f.read()
    if text == original:
        print('변경 없음 — 파일 갱신 스킵')
        return False
    with open(GUIDE_HTML, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return True


def main():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DAYS_BACK)
    try:
        xml_bytes = fetch_rss(DAYS_BACK)
        items = parse_items(xml_bytes, cutoff)
    except (urllib.error.URLError, ET.ParseError, TimeoutError) as e:
        print(f'RSS 수집 실패, guide.html 안 건드리고 종료: {e}')
        return

    if not items:
        print('파싱된 뉴스 0건 — guide.html 안 건드리고 종료')
        return

    selected = dedupe(items, TARGET_COUNT, SIM_THRESHOLD)
    print(f'수집 {len(items)}건 -> 중복제거 후 {len(selected)}건 선정')
    for it in selected:
        print(f"  {it['date'].strftime('%Y.%m.%d')}  {it['source']}  {it['title']}")

    patch_guide_html(selected)


if __name__ == '__main__':
    main()
