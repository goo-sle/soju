"""guide.html 지역별 브랜드 탭(.rgH-card)을 원본으로 브랜드별 정적 페이지(brand/<slug>.html)를 생성.

- 검색엔진이 "브랜드명 + 도수/제조사" 같은 구체 검색어를 개별 페이지로 받게 하려는 목적(SEO).
- guide.html의 .rgH-name을 <a href="brand/<slug>">로 감싸 내부 링크도 같이 걸어줌(멱등).
- sitemap.xml에 브랜드 URL을 넣고, 내용이 바뀐 페이지만 lastmod를 오늘로 갱신.
- 원본에서 사라진 브랜드의 페이지는 삭제.

guide.html 브랜드 데이터를 고친 뒤 실행: python .github/scripts/build_brand_pages.py
"""
import datetime
import html
import os
import re

GUIDE_HTML = 'guide.html'
SITEMAP_XML = 'sitemap.xml'
OUT_DIR = 'brand'
SITE = 'https://xn--9l4b29k.kro.kr'
KST = datetime.timezone(datetime.timedelta(hours=9))
CAT_LABEL = {'cat-diluted': '희석식', 'cat-flavor': '플레이버', 'cat-distilled': '증류식'}


def slugify(name):
    return re.sub(r'[^\w]+', '-', name).strip('-')


def strip_tags(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def first(pat, s, default=''):
    m = re.search(pat, s, re.DOTALL)
    return m.group(1) if m else default


def blocks(cls, card):
    # .chg/.spec는 카드 안에 여러 개일 수 있음 — 팝업(buildIndex)과 같이 이어붙임
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
            for card in re.split(r'<div class="rgH-card ', grp)[1:]:
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
                    'chg': blocks('chg', card),
                    'spec': blocks('spec', card),
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


def render(b, siblings):
    e = html.escape
    abv = b['abv']
    title = '%s%s · %s | 대한민국 소주 가이드' % (b['name'], ' 도수 ' + abv if abv else '', b['company'])
    summary = strip_tags(b['det']) or b['kw']
    desc = '%s(%s) — %s%s. %s' % (b['name'], b['company'], b['cat'], ', ' + abv if abv else '', summary)
    desc = desc[:155]
    url = '%s/brand/%s' % (SITE, b['slug'])

    facts = [('분류', b['cat']), ('도수', abv), ('출시', b['year']), ('제조사', b['company']), ('지역', b['region'])]
    facts_html = ''.join('<div><dt>%s</dt><dd>%s</dd></div>' % (k, e(v)) for k, v in facts if v)
    photo = ''
    if b['photos']:
        src, alt = b['photos'][0]
        photo = '<img class="photo" src="../%s" alt="%s">' % (e(src), e(alt or b['name']))
    sib = ''.join('<li><a href="%s">%s</a></li>' % (s['slug'], e(s['name'])) for s in siblings)
    breadcrumb = ('{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":['
                  '{"@type":"ListItem","position":1,"name":"대한민국 소주 가이드","item":"%s/guide"},'
                  '{"@type":"ListItem","position":2,"name":"%s","item":"%s"}]}') % (SITE, b['name'].replace('"', ''), url)

    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<link rel="canonical" href="{url}">
<meta name="description" content="{desc}">
<meta property="og:site_name" content="대한민국 소주 가이드">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="ko_KR">
<script type="application/ld+json">{breadcrumb}</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-01Z00FVDNW"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-01Z00FVDNW');</script>
<style>
:root{{--ink:#17170F;--muted:#6E6858;--line:#DCD6C6;--bg:#F5F3EE;--brand:#003D2E;--brand-2:#0B8457;--cat-diluted:#4f8fd1;--cat-flavor:#e28a4d;--cat-distilled:#9c7a5c}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Pretendard Variable",'Noto Sans KR',sans-serif;line-height:1.7}}
main{{max-width:760px;margin:0 auto;padding:8px 16px 64px}}
/* guide.html .gnav와 같은 상단 메뉴 — 검색으로 바로 들어온 방문자도 같은 사이트로 인식하게 */
.gnav{{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 20px;padding:16px 20px;margin-bottom:20px;border-bottom:1px solid var(--line)}}
.gnav-brand{{font-weight:900;font-size:18px;color:var(--ink);text-decoration:none;white-space:nowrap}} .gnav-brand span{{color:var(--brand-2)}}
.gnav-links{{display:flex;flex-wrap:wrap;gap:6px 22px}} .gnav-links a{{font-size:14px;font-weight:600;color:var(--muted);text-decoration:none;padding:4px 2px}} .gnav-links a:hover{{color:var(--brand)}}
@media (max-width:640px){{.gnav{{padding:14px 16px}} .gnav-links{{gap:4px 16px}} .gnav-links a{{font-size:13px}}}}
.back{{font-size:14px;margin:0 0 16px}} .back a{{color:var(--brand-2);text-decoration:none}}
h1{{font-size:clamp(26px,5vw,36px);font-weight:900;margin:0 0 4px;letter-spacing:-.02em}}
.kw{{color:var(--muted);margin:0 0 20px}}
.top{{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-bottom:24px}}
.photo{{width:180px;aspect-ratio:3/4;object-fit:cover;border-radius:8px;background:#fff}}
dl{{flex:1;min-width:220px;margin:0;display:grid;gap:6px;border-left:4px solid var(--{cat_cls},var(--line));padding-left:14px}}
dl div{{display:flex;gap:12px}} dt{{width:52px;color:var(--muted);font-weight:700}} dd{{margin:0;font-weight:700}}
section{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:14px}}
h2{{font-size:17px;font-weight:900;margin:0 0 8px}}
.tl-event{{display:flex;gap:12px;padding:2px 0}} .tl-event-when{{flex:none;width:72px;font-weight:700;color:var(--muted)}}
ul{{margin:0;padding-left:18px}} a{{color:var(--brand-2)}}
</style>
</head>
<body>
<header class="gnav">
<a class="gnav-brand" href="../guide#quickindex">대한민국 <span>소주</span> 가이드</a>
<nav class="gnav-links"><a href="../guide#browse">둘러보기</a><a href="../guide#quickindex">빠른 찾기</a><a href="../guide#timeline">타임라인</a><a href="../guide#region">지역별 브랜드</a><a href="../guide#companies">제조사 현황</a><a href="../guide#method">제조 방법</a></nav>
</header>
<main>
<h1>{name}</h1>
<p class="kw">{kw}</p>
<div class="top">{photo}<dl>{facts}</dl></div>
{sections}
<p class="back"><a href="../guide#region">지역별 소주 브랜드 전체 보기 →</a></p>
</main>
</body>
</html>
'''.format(title=e(title), url=url, desc=e(desc), breadcrumb=breadcrumb, cat_cls=b['cat_cls'],
           name=e(b['name']), kw=e(b['kw']), photo=photo, facts=facts_html,
           sections=section('이름 유래', b['ety']) + section('상세 연혁', b['det']) +
           section('변경 이력', b['chg']) + section('스페셜 에디션', b['spec']) +
           section('%s의 다른 소주' % e(b['company']), sib and '<ul>%s</ul>' % sib))


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


def main():
    with open(GUIDE_HTML, encoding='utf-8') as f:
        text = f.read()
    brands = parse(text)
    slugs = [b['slug'] for b in brands]
    dup = {s for s in slugs if slugs.count(s) > 1}
    if dup:
        raise SystemExit('브랜드 slug 중복: %s — 브랜드명을 구분되게 고칠 것' % ', '.join(sorted(dup)))

    linked = link_names(text)
    if linked != text:
        with open(GUIDE_HTML, 'w', encoding='utf-8', newline='\n') as f:
            f.write(linked)

    os.makedirs(OUT_DIR, exist_ok=True)
    changed = set()
    for b in brands:
        siblings = [s for s in brands if s['company'] == b['company'] and s is not b]
        page = render(b, siblings)
        path = os.path.join(OUT_DIR, b['slug'] + '.html')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                if f.read() == page:
                    continue
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(page)
        changed.add(b['slug'])
    for fn in os.listdir(OUT_DIR):
        if fn.endswith('.html') and fn[:-5] not in slugs:
            os.remove(os.path.join(OUT_DIR, fn))

    update_sitemap(changed, slugs, datetime.datetime.now(KST).strftime('%Y-%m-%d'))
    print('브랜드 %d종 · 변경 %d개 페이지' % (len(brands), len(changed)))


if __name__ == '__main__':
    main()
