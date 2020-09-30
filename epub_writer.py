import re
from os import remove, makedirs, path

import requests_async as requests
from bs4 import BeautifulSoup
from ebooklib import epub


def and_then(opt, mapper):
    if opt is None:
        return opt
    else:
        return mapper(opt)


async def download_chapter(fid, chapter):
    url = "https://www.fanfiction.net/s/%s/%s" % (fid, chapter)
    resp = await requests.get(url)
    if resp.status_code != 200:
        raise FileNotFoundError(f"Нельзя скачать с адреса {url}")

    return BeautifulSoup(resp.text, "lxml")


def extract_summary(fic_body):
    heading_tag = fic_body.find('div', id='profile_top')
    if heading_tag is None:
        raise RuntimeError('Failed to find a <div id="profile_top">')

    fic_info = {'title': and_then(heading_tag.find('b', class_='xcontrast_txt'), lambda x: x.text),
                'author': and_then(heading_tag.find('a', class_='xcontrast_txt'), lambda x: x.text),
                'summary': and_then(heading_tag.find('div', class_='xcontrast_txt'), lambda x: x.text)}
    infoline = heading_tag.find('span', class_='xgray xcontrast_txt')
    if infoline is not None:
        key_whitelist = ('Words', 'Chapters', 'Status', 'Rated')
        for entry in infoline.text.split('-'):
            key, *val = map(lambda s: s.strip(), entry.split(':'))
            if key in key_whitelist:
                fic_info[key] = val[0]

    chapter_titles = {}
    if 'Chapters' in fic_info:
        chapter_titles_select = fic_body.find('select', id='chap_select')
        if chapter_titles_select is None:
            raise RuntimeError("Failed to find <select id=chap_select>")

        all_titles = chapter_titles_select.find_all('option')
        for item in all_titles:
            *_, name = item.text.split('.', 1)
            chapter_titles[int(item['value'])] = name
    else:
        fic_info['Chapters'] = '1'
        chapter_titles[1] = fic_info['title']

    fic_info['chapter_titles'] = chapter_titles
    return fic_info


def extract_chapter(fic_body, chapter_title):
    chapter_text = fic_body.find('div', id='storytext')
    if chapter_text is None:
        raise RuntimeError("В главе нет содержимого!")

    chapter_title_tag = fic_body.new_tag('h1')
    chapter_title_tag.string = chapter_title
    chapter_text.insert(0, chapter_title_tag)

    chapter_html = BeautifulSoup("""
    <html>
    <head>
        <title>...</title>
        <link rel="stylesheet" type="text/css" href="style/main.css" />
    </head>
    <body></body>
    </html>""", 'lxml')
    chapter_html.head.title.string = chapter_title
    chapter_html.body.append(chapter_text)

    return str(chapter_html)


def write_chapter(chapter_body, fid, cid):
    fic_name = path.join(fid, "%s.html" % cid)
    try:
        makedirs(path.dirname(fic_name))
    except FileExistsError:
        pass

    with open(fic_name, 'w+') as f:
        f.write(chapter_body)


async def package_fanfic(fanfic_link):
    match = re.match(r"^https?://(m.)?fanfiction.net/s/(?P<id>\w+)/(?P<chapter>\w+)/(?P<slug>.+)$", fanfic_link)
    if match is None:
        raise FileNotFoundError(f"Невозможно скачать с адреса: {fanfic_link}.\nИсправьте адрес.")

    fic_id, fic_slug = match.group('id', 'slug')

    try:
        chapter_data = await download_chapter(fic_id, 1)
        heading = extract_summary(chapter_data)
        chapter_count = int(heading['Chapters'])

        ebook = epub.EpubBook()
        ebook.set_identifier("fanfition-%s" % fic_id)
        ebook.set_title(heading['title'])
        ebook.add_author(heading['author'])

        intro_ch = epub.EpubHtml(title="Introduction", file_name='intro.xhtml')
        intro_ch.content = """
            <html>
            <head>
                <title>Introduction</title>
                <link rel="stylesheet" href="style/main.css" type="text/css" />
            </head>
            <body>
                <h1>%s</h1>
                <p><b>By: %s</b></p>
                <p>%s</p>
            </body>
            </html>
            """ % (heading['title'], heading['author'], heading['summary'])
        ebook.add_item(intro_ch)

        chapters = []

        head_ch = epub.EpubHtml(title=heading['chapter_titles'][1], file_name='chapter_1.xhtml')
        head_ch.content = extract_chapter(chapter_data, head_ch.title)
        ebook.add_item(head_ch)
        chapters.append(head_ch)

        for chapter_id in range(2, chapter_count + 1):
            chapter_title = heading['chapter_titles'][chapter_id]
            chapter_data = await download_chapter(fic_id, chapter_id)
            chapter_data = extract_chapter(chapter_data, chapter_title)

            chapter = epub.EpubHtml(title=chapter_title, file_name='chapter_%s.xhtml' % chapter_id)
            chapter.content = chapter_data
            ebook.add_item(chapter)
            chapters.append(chapter)

        # Set the TOC
        ebook.toc = (
            epub.Link('intro.xhtml', 'Introduction', 'intro'),
            (epub.Section('Chapters'), chapters)
        )

        # add navigation files
        ebook.add_item(epub.EpubNcx())
        ebook.add_item(epub.EpubNav())

        # Create spine
        nav_page = epub.EpubNav(uid='book_toc', file_name='toc.xhtml')
        ebook.add_item(nav_page)
        ebook.spine = [intro_ch, nav_page] + chapters

        filename = '%s-%s.epub' % (fic_slug, fic_id)
        if path.exists(filename):
            remove(filename)
        epub.write_epub(filename, ebook, {})
        return filename

    except Exception:
        raise Exception()
