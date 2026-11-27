"""index.html 지역별 브랜드 탭(.rgH-card)을 원본으로 브랜드별 정적 페이지(brand/<slug>.html)를 생성.

- 검색엔진이 "브랜드명 + 도수/제조사" 같은 구체 검색어를 개별 페이지로 받게 하려는 목적(SEO).
- index.html의 .rgH-name을 <a href="brand/<slug>">로 감싸 내부 링크도 같이 걸어줌(멱등).
- sitemap.xml에 브랜드 URL을 넣고, 내용이 바뀐 페이지만 lastmod를 오늘로 갱신.
- 원본에서 사라진 브랜드의 페이지는 삭제.

index.html 브랜드 데이터를 고친 뒤 실행: python .github/scripts/build_brand_pages.py
"""
import collections
import datetime
import html
import os
import re

INDEX_HTML = 'index.html'
SITEMAP_XML = 'sitemap.xml'
OUT_DIR = 'brand'
SITE = 'https://xn--9l4b29k.kro.kr'
KST = datetime.timezone(datetime.timedelta(hours=9))
CAT_LABEL = {'cat-diluted': '희석식', 'cat-flavor': '플레이버', 'cat-distilled': '증류식'}
# 브랜드 이름을 바꾸면 slug(주소)가 바뀜 → 옛 주소는 지우지 않고 새 주소로 넘기는 이동 파일로 남김(검색 순위 유지).
# 이름을 바꿀 때마다 '옛 slug': '새 slug'를 추가할 것. 여기 없는 옛 페이지는 삭제되고 404가 됨.
REDIRECTS = {
    '명인안동소주-45도': '명인안동소주-45도-박재서-명인',
    '명인안동소주-35-22-19도': '명인안동소주-35-22-19도-박재서-명인',
    '민속주-안동소주-25도': '민속주-안동소주-25도-조옥화-명인',
    '민속주-안동소주-35도': '민속주-안동소주-35도-조옥화-명인',
    '민속주-안동소주-45도': '민속주-안동소주-45도-조옥화-명인',
}


def slugify(name):
    return re.sub(r'[^\w]+', '-', name).strip('-')


def strip_tags(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def first(pat, s, default=''):
    m = re.search(pat, s, re.DOTALL)
    return m.group(1) if m else default


def blocks(cls, card):
    # .chg/.spec는 카드 안에 여러 개일 수 있음 — 전부 이어붙여 상세 페이지의 한 섹션으로
    return ''.join(re.findall(r'<div class="%s tl-events">\n(.*?)\n</div>' % cls, card, re.DOTALL))


def parse(text):
    idx = {}
    for m in re.finditer(r'<span class="idx-cat[^"]*">([^<]*)</span><span class="idx-brand-name">([^<]*)</span>.*?<div class="idx-brand-kw">([^<]*)</div>', text):
        idx[m.group(2).strip()] = (m.group(1).strip(), m.group(3).strip())

    brands = []
    regions = re.split(r'<div class="region-detail" id="region-', text)[1:]
    for reg in regions:
        region = first(r'<div class="region-label-title">([^<]*)</div>', reg).strip()
        for grp in re.split(r'<details class="rgH2-group">', reg)[1:]:
            company = strip_tags(first(r'<summary class="rgH2-head[^"]*">(.*?)<span', grp))
            grp = grp.split('</details>')[0]
            cards = re.split(r'<div class="rgH-card ', grp)[1:]
            for i, card in enumerate(cards):
                name = strip_tags(first(r'<div class="rgH-name">(.*?)</div>', card))
                if not name:
                    continue
                cat_cls = card.split('"')[0]
                cat, kw = idx.get(name, (CAT_LABEL.get(cat_cls, ''), ''))
                brands.append({
                    'name': name, 'slug': slugify(name), 'region': region, 'company': company,
                    'cat': cat, 'cat_cls': cat_cls, 'kw': kw,
                    'year': strip_tags(first(r'<div class="rgH-year">(.*?)</div>', card)),
                    'abv': strip_tags(first(r'<span class="abv-badge">(.*?)</span>', card)),
                    'photos': re.findall(r'<img class="rgH-photo" src="([^"]*)" alt="([^"]*)"', card),
                    'ety': first(r'<div class="ety">(.*?)</div>\n', card),
                    'det': first(r'<div class="det">(.*?)</div>\n', card),
                    'ing': first(r'<div class="ing">(.*?)</div>\n', card),
                    'chg': blocks('chg', card),
                    'spec': blocks('spec', card),
                    'disc': 'disc-badge' in card.split('<div class="rgH-right">')[0],
                    # 여는 <div class="rgH-card"는 split에 먹혀서 중간 카드 −1, 그룹 마지막 카드는 감싸는 div까지 −2가 정상
                    'nested': card.count('<div') - card.count('</div>') != (-2 if i == len(cards) - 1 else -1),
                })
    return brands


def link_names(text):
    # .rgH-name 안 텍스트를 브랜드 페이지 링크로 감쌈(이미 감싸져 있으면 href만 최신 slug로)
    def sub(m):
        name = strip_tags(m.group(1))
        return '<div class="rgH-name"><a href="brand/%s">%s</a></div>' % (slugify(name), html.escape(name, quote=False))
    return re.sub(r'<div class="rgH-name">(.*?)</div>', sub, text)


def section(title, body):
    return '<section><h2>%s</h2>%s</section>\n' % (title, body) if body else ''


def josa(word, with_final, without_final):
    # 마지막 한글/숫자의 받침 유무로 조사 선택(괄호 속 부연은 무시). 영문 등은 받침 없음으로 봄
    w = re.sub(r'\s*\([^()]*\)\s*$', '', word).strip() or word
    c = w[-1]
    final = (ord(c) - 0xAC00) % 28 != 0 if '가' <= c <= '힣' else c in '013678'
    return word + (with_final if final else without_final)


def lead(b):
    # 이미 있는 데이터(제조사·지역·분류·출시연도·도수·단종)로 만든 한 문장 요약 — 새 사실은 넣지 않음
    cat = b['cat'].replace('(단종)', '')
    kind = cat + ' 소주' if cat in ('희석식', '증류식', '플레이버', '담금용', '수출용') else cat or '소주'
    y = re.match(r'\d{4}', b['year'])
    when = ''
    if y:
        when = y.group() + ('년경에' if '추정' in b['year'] else '년 이전에' if '이전' in b['year'] else '년에')
    s = '%s %s %s %s 지역의 %s' % (josa(b['name'], '은', '는'), josa(b['company'], '이', '가'),
                                '%s 출시한' % when if when else '만드는', b['region'].replace(' · ', '·'), kind)
    abv = b['abv'].replace('(추정)', '').strip()
    s += '로, 도수는 %s임.' % abv if abv else '임.'
    if b['disc'] or '단종' in b['cat']:
        s += ' 지금은 단종된 제품임.'
    return s


def tiles(items, more_label='전체 %d종 보기'):
    def tile(s):
        ph = '<img src="../%s" alt="" loading="lazy">' % html.escape(s['photos'][0][0]) if s['photos'] else html.escape(s['name'][:1])
        sub = ' · '.join(x for x in (s['abv'], s['year']) if x)
        return '<a class="tile" href="%s"><span class="ph">%s</span><span class="nm">%s</span><span class="sub">%s</span></a>' % (s['slug'], ph, html.escape(s['name']), html.escape(sub))
    # 사진 있는 것부터(같은 조건이면 원래 순서)
    items = sorted(items, key=lambda s: not s['photos'])
    if not items:
        return ''
    out = '<div class="tiles">%s</div>' % ''.join(tile(s) for s in items[:12])
    if len(items) > 12:
        out += '<details class="all"><summary>%s</summary><div class="tiles">%s</div></details>' % (more_label % len(items), ''.join(tile(s) for s in items[12:]))
    return out


def redirect_page(new_slug):
    url = '%s/brand/%s' % (SITE, new_slug)
    return ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8"/>\n<title>소주도감</title>\n'
            '<!-- 이름이 바뀐 브랜드의 옛 주소 — build_brand_pages.py REDIRECTS가 생성 -->\n'
            '<link rel="canonical" href="%s">\n<meta http-equiv="refresh" content="0; url=%s">\n</head>\n'
            '<body>\n<a href="%s">%s 페이지로 이동</a>\n</body>\n</html>\n') % (url, new_slug, new_slug, html.escape(new_slug))


def render(b, siblings, edition, neighbors=()):
    e = html.escape
    abv = b['abv']
    title = '%s%s · %s | 소주도감' % (b['name'], ' 도수 ' + abv if abv else '', b['company'])
    summary = strip_tags(b['det']) or b['kw']
    desc = '%s(%s) — %s%s. %s' % (b['name'], b['company'], b['cat'], ', ' + abv if abv else '', summary)
    desc = desc[:155]
    url = '%s/brand/%s' % (SITE, b['slug'])

    tags = [e(abv) if abv else '',
            '<i class="dot"></i>%s' % e(b['cat']) if b['cat'] else '',
            e(b['region']), e(b['company']),
            '%s 출시' % e(b['year']) if b['year'] else '']
    facts_html = ''.join('<span class="tag">%s</span>' % t for t in tags if t)
    photo = more = og_image = ''
    if b['photos']:
        src, alt = b['photos'][0]
        photo = '<img class="photo" src="../%s" alt="%s">' % (e(src), e(alt or b['name']))
        og_image = '\n<meta property="og:image" content="%s/%s">' % (SITE, e(src))
    if len(b['photos']) > 1:
        # 시대별 사진(메인 팝업의 페이지 넘기기 대상)은 대표 사진 아래 썸네일 줄로 — 캡션은 alt 끝의 출처 괄호(형식 무관)를 뗌
        more = '<div class="more">%s</div>' % ''.join(
            '<figure><img src="../%s" alt="%s" loading="lazy"><figcaption>%s</figcaption></figure>'
            % (e(src), e(alt), e(re.sub(r'\s*\((?:[^()]|\([^()]*\))*\)\s*$', '', alt))) for src, alt in b['photos'][1:])
    sib = tiles(siblings)
    near = tiles(neighbors)
    breadcrumb = ('{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":['
                  '{"@type":"ListItem","position":1,"name":"소주도감","item":"%s/"},'
                  '{"@type":"ListItem","position":2,"name":"%s","item":"%s"}]}') % (SITE, b['name'].replace('"', ''), url)

    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<meta name="theme-color" content="#F4F6F8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@300;500;700&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="canonical" href="{url}">
<meta name="description" content="{desc}">
<meta property="og:site_name" content="소주도감">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="ko_KR">{og_image}
<script type="application/ld+json">{breadcrumb}</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-01Z00FVDNW"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-01Z00FVDNW');</script>
<style>
:root{{--ink:#252A33;--muted:#5F6672;--line:#DDE3EC;--bg:#F4F6F8;--brand:#22408C;--brand-2:#2F57B0;--cat-diluted:#4f8fd1;--cat-flavor:#e28a4d;--cat-distilled:#9c7a5c}}
::selection{{background:color-mix(in srgb,var(--brand) 18%,transparent)}}
*{{box-sizing:border-box}}
:focus-visible{{outline:2px solid var(--brand-2);outline-offset:2px}}
body{{margin:0;word-break:keep-all;overflow-wrap:anywhere;background:var(--bg);color:var(--ink);font-family:"Pretendard Variable",'Noto Sans KR',sans-serif;line-height:1.7}}
main{{max-width:760px;margin:0 auto;padding:8px 16px 64px}}
/* index.html .gnav와 같은 상단 메뉴 — 검색으로 바로 들어온 방문자도 같은 사이트로 인식하게 */
.gnav{{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 20px;padding:16px 20px;margin-bottom:20px;border-bottom:1px solid var(--line)}}
.gnav-brand{{font-family:"Hahmlet","Pretendard Variable",serif;font-weight:700;font-size:24px;letter-spacing:-.01em;color:var(--brand);text-decoration:none;white-space:nowrap}} @media (max-width:640px){{.gnav-brand{{font-size:21px}}}}
.gnav-links{{display:flex;flex-wrap:wrap;gap:6px 22px}} .gnav-links a{{font-size:14px;font-weight:600;color:var(--muted);text-decoration:none;padding:4px 2px}} @media (hover:hover){{.gnav-links a:hover{{color:var(--brand)}}}}
@media (max-width:640px){{.gnav{{padding:14px 16px}} .gnav-links{{width:100%;justify-content:space-between;gap:4px 8px}} .gnav-links a{{font-size:13px}}}}
h1,h2{{font-family:"Hahmlet","Pretendard Variable",serif}}
h1{{text-wrap:balance;font-size:clamp(26px,5vw,36px);font-weight:300;color:var(--brand);margin:0 0 4px;letter-spacing:-.02em}}
.kw{{color:var(--muted);margin:0 0 20px}}
.lead{{margin:0 0 20px;font-size:16px}}
.top{{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-bottom:24px}}
.photo{{width:200px;aspect-ratio:3/4;object-fit:cover;border-radius:14px;background:#fff;border:1px solid var(--line)}}
.more{{display:flex;flex-wrap:wrap;gap:12px;margin:-8px 0 24px}} .more figure{{margin:0;width:110px}}
/* .det 안 라인업·한정판 사진 — 가로든 세로든 높이 280px 안에서 원래 비율 그대로, 가운데 정렬 */
.det-img{{display:block;width:auto;height:auto;max-width:100%;max-height:280px;margin:14px auto 0;border-radius:8px;background:#fff}}
.more img{{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:8px;background:#fff}} .more figcaption{{font-size:12px;line-height:1.4;word-break:keep-all;color:var(--muted);margin-top:4px}}
.tags{{flex:1;min-width:220px;display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}}
.tag{{display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border:1px solid var(--line);border-radius:999px;background:#fff;font-size:13px;font-weight:600}}
.tag .dot{{width:8px;height:8px;border-radius:50%;background:var(--{cat_cls},var(--muted))}}
section{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin-bottom:14px}}
h2{{font-size:17px;font-weight:500;margin:0 0 8px}}
.tl-event{{display:flex;gap:12px;padding:2px 0}} .tl-event-when{{flex:none;width:72px;font-weight:700;color:var(--muted)}}
ul{{margin:0;padding-left:18px}} a{{color:var(--brand-2)}}
/* index.html과 같은 소주병 커서(기본·링크) */
html{{cursor:url("data:image/png;base64,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") 5 3, auto}} a{{cursor:url("data:image/png;base64,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") 2 1,pointer}}
/* 같은 회사 다른 소주: 메인 빠른 찾기와 같은 사진 타일 */
.tiles{{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:10px}}
.tile{{display:block;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;color:var(--ink);text-decoration:none;transition:transform .15s,box-shadow .15s}}
@media (hover:hover){{.tile:hover{{transform:translateY(-3px);box-shadow:0 8px 18px color-mix(in srgb,var(--ink) 12%,transparent)}}}}
.tile .ph{{display:grid;place-items:center;aspect-ratio:3/4;background:#EEF2F7;color:var(--muted);font-family:"Hahmlet",serif;font-size:26px}}
.tile .ph img{{width:100%;height:100%;object-fit:cover;display:block}}
.tile .nm{{display:block;padding:7px 9px 0;font-weight:700;font-size:13px;line-height:1.35}} .tile .sub{{display:block;padding:2px 9px 9px;font-size:12px;color:var(--muted)}}
.all{{margin-top:12px}} .all summary{{cursor:pointer;font-weight:700;color:var(--brand-2);font-size:14px;margin-bottom:10px}}
@media (max-width:640px){{.tiles{{grid-template-columns:repeat(3,1fr);gap:8px}} .photo{{width:100%;max-width:240px}}}}
/* 메인과 같은 푸터 */
.footer{{max-width:760px;margin:0 auto;padding:12px 16px 40px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;display:flex;flex-direction:column;align-items:center;gap:2px;text-align:center}}
.footer i{{display:inline-block;width:1px;height:10px;background:var(--line);margin:0 8px;vertical-align:middle}}
</style>
</head>
<body>
<header class="gnav">
<a class="gnav-brand" href="../">소주도감</a>
<nav class="gnav-links"><a href="../#browse">둘러보기</a><a href="../#region">소주 찾기</a><a href="../#timeline">소주 백과</a><a href="../#news">소주 라운지</a></nav>
</header>
<main>
<h1>{name}</h1>
<p class="kw">{kw}</p>
<div class="top">{photo}<div class="tags">{facts}</div></div>{more}
<p class="lead">{lead}</p>
{sections}
</main>
<footer class="footer"><span>소주도감<i></i>{edition} Edition</span><span><b>출처</b><i></i>나무위키·위키백과·한국경제매거진·브랜딩리드·각사 보도자료 종합</span><span>© GooSle 2026 소주도감</span></footer>
</body>
</html>
'''.format(title=e(title), url=url, desc=e(desc), breadcrumb=breadcrumb, cat_cls=b['cat_cls'],
           name=e(b['name']), kw=e(b['kw']), photo=photo, more=more, og_image=og_image, facts=facts_html,
           lead=e(lead(b)),
           sections=section('🔤 이름 유래', b['ety']) + section('📜 상세 연혁', b['det']) + section('🌾 원재료', b['ing']) +
           section('🔄 변경 이력', b['chg']) + section('✨ 스페셜 에디션', b['spec']) +
           section('🏭 %s의 다른 소주' % e(b['company']), sib) +
           section('📍 %s 지역의 다른 소주' % e(b['region'].replace(' · ', '·')), near), edition=edition)


def update_sitemap(changed, all_slugs, today):
    with open(SITEMAP_XML, encoding='utf-8') as f:
        xml = f.read()
    old = dict(re.findall(r'<loc>%s/brand/([^<]+)</loc>\s*<lastmod>([^<]*)' % re.escape(SITE), xml))
    xml = re.sub(r'\s*<url>\s*<loc>%s/brand/.*?</url>' % re.escape(SITE), '', xml, flags=re.DOTALL)
    entries = ''.join(
        '\n  <url>\n    <loc>%s/brand/%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n  </url>'
        % (SITE, s, today if s in changed or s not in old else old[s]) for s in all_slugs)
    xml = xml.replace('\n</urlset>', entries + '\n</urlset>')
    with open(SITEMAP_XML, 'w', encoding='utf-8', newline='\n') as f:
        f.write(xml)


def check_sync(text, brands):
    # 지역 카드(.rgH-card)와 빠른 찾기(.idx-brand)는 손으로 맞추는 두 원본 → 어긋난 곳을 경고만(생성은 계속)
    warns = []
    idx = {}
    for m in re.finditer(r'<div class="idx-brand">(.*?)<div class="idx-brand-kw">', text):
        row = m.group(1)
        name = html.unescape(first(r'<span class="idx-brand-name">([^<]*)</span>', row).strip())
        idx[name] = (first(r'<span class="idx-abv">([^<]*)</span>', row).strip(),
                     first(r'<span class="idx-year">([^<]*)</span>', row).strip(),
                     '단종' in first(r'<span class="idx-cat[^"]*">([^<]*)</span>', row))
    reg = {b['name']: b for b in brands}
    for n in sorted(set(reg) - set(idx)):
        warns.append('빠른 찾기에 없음: ' + n)
    for n in sorted(set(idx) - set(reg)):
        warns.append('지역 카드에 없음: ' + n)
    for n in sorted(set(reg) & set(idx)):
        b, (abv, year, disc) = reg[n], idx[n]
        if b['abv'] != abv and (re.search(r'\d', b['abv']) or re.search(r'\d', abv)):
            warns.append('도수 불일치: %s (지역 %s / 빠른 찾기 %s)' % (n, b['abv'] or '없음', abv or '없음'))
        if b['year'][:4] != year[:4]:
            warns.append('출시연도 불일치: %s (지역 %s / 빠른 찾기 %s)' % (n, b['year'], year))
        if b['disc'] != disc:
            warns.append('단종 표시 불일치: %s (지역 %s / 빠른 찾기 %s)' % (n, b['disc'], disc))
        if b['nested']:
            warns.append('카드 <div>/</div> 개수 어긋남(닫는 태그 누락으로 다음 카드가 안에 들어갔을 수 있음): ' + n)
    for w in warns:
        print('경고: ' + w)


def write_if_changed(slug, page):
    path = os.path.join(OUT_DIR, slug + '.html')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            if f.read() == page:
                return False
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(page)
    return True


def main():
    with open(INDEX_HTML, encoding='utf-8') as f:
        text = f.read()
    brands = parse(text)
    edition = first(r'(\d\d\.\d\d) Edition', text, '')  # 브랜드 페이지 푸터도 메인과 같은 에디션
    slugs = [b['slug'] for b in brands]
    dup = {s for s in slugs if slugs.count(s) > 1}
    if dup:
        raise SystemExit('브랜드 slug 중복: %s — 브랜드명을 구분되게 고칠 것' % ', '.join(sorted(dup)))

    linked = link_names(text)
    if linked != text:
        with open(INDEX_HTML, 'w', encoding='utf-8', newline='\n') as f:
            f.write(linked)

    os.makedirs(OUT_DIR, exist_ok=True)
    changed = set()
    by_co, by_region = collections.defaultdict(list), collections.defaultdict(list)
    for b in brands:
        by_co[b['company']].append(b)
        by_region[b['region']].append(b)
    for b in brands:
        siblings = [s for s in by_co[b['company']] if s is not b]
        neighbors = [s for s in by_region[b['region']] if s['company'] != b['company']]
        if write_if_changed(b['slug'], render(b, siblings, edition, neighbors)):
            changed.add(b['slug'])
    for old, new in REDIRECTS.items():
        if old in slugs:
            raise SystemExit('REDIRECTS의 옛 slug가 다시 브랜드로 쓰임: %s — REDIRECTS에서 뺄 것' % old)
        if new not in slugs:
            print('경고: REDIRECTS 대상 브랜드 없음: %s → %s' % (old, new))
        write_if_changed(old, redirect_page(new))
    for fn in os.listdir(OUT_DIR):
        if fn.endswith('.html') and fn[:-5] not in slugs and fn[:-5] not in REDIRECTS:
            os.remove(os.path.join(OUT_DIR, fn))
            print('경고: 브랜드 페이지 삭제됨(404): %s — 이름만 바꾼 거면 REDIRECTS에 추가' % fn[:-5])

    update_sitemap(changed, slugs, datetime.datetime.now(KST).strftime('%Y-%m-%d'))
    print('브랜드 %d종 · 변경 %d개 페이지' % (len(brands), len(changed)))
    check_sync(text, brands)  # 출력 인코딩 오류가 나도 페이지·sitemap은 이미 써진 뒤


if __name__ == '__main__':
    main()
