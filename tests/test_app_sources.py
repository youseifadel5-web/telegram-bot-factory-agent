"""اختبارات طبقة مصادر المحتوى (services/app_sources) — كلها بدون شبكة.

بتغطّي: خرائط حقول golive وأوضاعه وGUIDs، normalizeImage وخرائط fasel،
محلّلات الـ pair/master/BaseVed في resolver، vodGroup/inferPackage/خرائط
فايربيس، ومحلّل M3U وسلامة القنوات الافتراضية.
"""
from __future__ import annotations

import json

import pytest

from services.app_sources import channels, fasel, firebase_catalog, golive, resolver


# ============================================================
# golive — خرائط الحقول + الأوضاع + الـ GUIDs
# ============================================================
def test_golive_clean_text_treats_blank_words_as_empty():
    assert golive.clean_text(None) == ""
    assert golive.clean_text("  ") == ""
    assert golive.clean_text("none") == ""
    assert golive.clean_text("NULL") == ""
    assert golive.clean_text("undefined") == ""
    assert golive.clean_text(" قيمة ") == "قيمة"


def test_golive_category_guids_exact():
    assert golive.MOVIE_CATEGORIES["arabic"]["categoryId"] == "2185cd2d-f379-4584-8caa-5884bced7150"
    assert golive.MOVIE_CATEGORIES["foreign"]["categoryId"] == "9ec354e5-4707-4161-9dab-b51f899b29d8"
    assert golive.MOVIE_CATEGORIES["arabic_all"]["categoryId"] == "a41d4764-d74e-4df3-a5aa-51e1725fe42e"
    assert golive.MOVIE_CATEGORIES["foreign_general"]["categoryId"] == "7bd112fc-a3c2-49ab-a3d7-5287ffd1d045"
    assert golive.SERIES_CATEGORIES["arabic"]["categoryId"] == "dd185bc6-1dfd-45c2-9189-13c47f672e5a"


def test_golive_movie_genres_and_series_keywords_literals():
    assert golive.MOVIE_GENRES["action"] == "أكشن"
    assert golive.MOVIE_GENRES["sci_fi"] == "خيال علمي"
    assert len(golive.MOVIE_GENRES) == 12
    assert golive.SERIES_KEYWORDS["turkish"] == "تركي"
    assert golive.SERIES_KEYWORDS["anime"] == "انمي"
    assert golive.SERIES_KEYWORDS["ramadan"] == "رمضان"


def test_golive_map_media_hikaye_field_mapping():
    item = {
        "id": 42,
        "titleAr": "فيلم عربي",
        "titleEn": "Arabic Movie",
        "title": "should-not-win",
        "slug": "arabic-movie",
        "posterUrl": "https://cdn/p.jpg",
        "backdropUrl": "https://cdn/b.jpg",
        "year": 2021,
        "rating": 8.4,
        "genreAr": "أكشن",
        "descriptionAr": "القصة بالعربي",
        "description": "english story",
        "sources": [
            {"streamUrl": "https://s/1.m3u8", "label": "سيرفر 1", "quality": "1080", "format": "m3u8"},
            {"url": "https://s/2.mp4", "quality": "720"},
        ],
    }
    media = golive.map_media(item, "movie")
    assert media["id"] == 42
    assert media["kind"] == "movie"
    assert media["title"] == "فيلم عربي"          # titleAr يفوز
    assert media["poster"] == "https://cdn/p.jpg"
    assert media["year"] == 2021
    assert media["rating"] == 8.4
    assert media["genre"] == "أكشن"
    assert media["story"] == "القصة بالعربي"      # descriptionAr يفوز
    assert media["sources"][0] == {"url": "https://s/1.m3u8", "label": "سيرفر 1",
                                   "quality": "1080", "format": "m3u8"}
    # عنصر التاني مفيش فيه label → الافتراضي
    assert media["sources"][1]["label"] == "سيرفر مشاهدة"
    assert media["sources"][1]["url"] == "https://s/2.mp4"


def test_golive_title_fallback_chain():
    assert golive.map_media({"titleEn": "EN only"})["title"] == "EN only"
    assert golive.map_media({"title": "T"})["title"] == "T"
    assert golive.map_media({"slug": "my-movie-slug"})["title"] == "my movie slug"
    assert golive.map_media({"posterUrl": "https://cdn/the-movie.jpg"})["title"] == "the-movie"
    assert golive.map_media({})["title"] == "بدون عنوان"


def test_golive_map_media_golive_variant():
    item = {"id": 1, "titleAr": "ع", "title": "en", "category": {"nameAr": "أفلام"},
            "posterUrl": "p", "descriptionAr": "د"}
    media = golive.map_media(item, "movie", variant="golive")
    assert media["title"] == "ع"
    assert media["genre"] == "أفلام"
    assert media["story"] == "د"


def test_golive_series_detail_groups_by_season():
    data = {
        "id": 5,
        "titleAr": "مسلسل",
        "episodes": [
            {"id": 11, "episodeNumber": 2, "seasonNumber": 1, "titleAr": "ح2",
             "sources": [{"streamUrl": "https://s/11"}]},
            {"id": 10, "episodeNumber": 1, "seasonNumber": 1, "title": "ح1"},
            {"id": 20, "episodeNumber": 1, "seasonNumber": 2, "titleAr": "م2ح1"},
        ],
    }
    detail = golive.map_series_detail(data, 5)
    assert detail["kind"] == "series"
    assert [s["season"] for s in detail["seasons"]] == [1, 2]
    season1 = detail["seasons"][0]
    assert [e["number"] for e in season1["episodes"]] == [1, 2]      # مرتّبة تصاعدياً
    assert season1["id"] == 1 and season1["episodes_count"] == 2
    assert season1["episodes"][1]["title"] == "ح2"
    assert season1["episodes"][1]["sources"][0]["url"] == "https://s/11"


def test_golive_mode_string_conventions():
    assert golive.build_movies_params("arabic")["categoryId"] == golive.MOVIE_CATEGORIES["arabic"]["categoryId"]
    assert golive.build_movies_params("foreign")["categoryId"] == golive.MOVIE_CATEGORIES["foreign"]["categoryId"]
    assert golive.build_movies_params("genre_action")["genre"] == "أكشن"
    assert golive.build_movies_params("year_2019")["year"] == "2019"
    top = golive.build_movies_params("top_rated")
    assert top["ratingMin"] == 7 and top["sortBy"] == "rating" and top["sortOrder"] == "desc"
    base = golive.build_movies_params(page=3)
    assert base["page"] == 3 and base["limit"] == 35
    assert golive.is_popular("popular") is True
    assert golive.is_popular("arabic") is False


def test_golive_series_mode_string_conventions():
    assert golive.build_series_params("turkish")["search"] == "تركي"
    assert golive.build_series_params("anime")["search"] == "انمي"
    assert golive.build_series_params("arabic")["categoryId"] == golive.SERIES_CATEGORIES["arabic"]["categoryId"]
    assert golive.build_series_params(page=2)["limit"] == 35


def test_golive_limit_is_35():
    assert golive.LIMIT == 35


# ============================================================
# fasel — normalizeImage + خرائط الحقول
# ============================================================
def test_fasel_normalize_image():
    assert fasel.normalize_image("http://x/y.jpg") == "https://x/y.jpg"
    assert fasel.normalize_image("https://x/y.jpg") == "https://x/y.jpg"
    assert fasel.normalize_image("/a.jpg") == "https://image.tmdb.org/t/p/w500/a.jpg"
    assert fasel.normalize_image("a.jpg") == "https://image.tmdb.org/t/p/w500/a.jpg"
    assert fasel.normalize_image("") == ""
    assert fasel.normalize_image(None) == ""


def test_fasel_map_media_item_fields():
    item = {
        "id": 9, "title": "فيلم", "type": "series", "poster_path": "/p.jpg",
        "backdrop_path": "/b.jpg", "subtitle": "1080p", "vote_average": 7.7,
        "release_date": "2020-01-01", "overview": "قصة",
        "genreslist": [{"name": "أكشن"}, "دراما"],
    }
    media = fasel.map_media_item(item)
    assert media["id"] == 9
    assert media["title"] == "فيلم"
    assert media["type"] == "serie"                      # series → serie
    assert media["poster"] == "https://image.tmdb.org/t/p/w500/p.jpg"
    assert media["backdrop"] == "/b.jpg"
    assert media["vote"] == 7.7
    assert media["release"] == "2020-01-01"
    assert media["genres"] == ["أكشن", "دراما"]


def test_fasel_map_media_item_type_rules():
    assert fasel.map_media_item({"id": 1, "is_anime": 1, "type": "movie"})["type"] == "anime"
    assert fasel.map_media_item({"id": 1, "type": "tv"})["type"] == "serie"
    assert fasel.map_media_item({"id": 1})["type"] == "movie"
    assert fasel.map_media_item({"id": 0}) == {}          # id=0 → مرفوض
    assert fasel.map_media_item({"id": 1, "first_air_date": "2019-02-02"})["release"] == "2019-02-02"


def test_fasel_map_video_fields():
    video = fasel.map_video({
        "url": "https://s/1.m3u8", "server": "سيرفر أ", "useragent": "UA",
        "header": "https://ref/", "quality": "HD", "hls": 1,
    })
    assert video["link"] == "https://s/1.m3u8"
    assert video["server"] == "سيرفر أ"
    assert video["userAgent"] == "UA"
    assert video["referer"] == "https://ref/"
    assert video["hls"] is True
    assert video["hd"] is True                            # quality فيه "hd"
    # قاعدة المواصفة: label فيه 1080/720 كمان يعتبر HD
    assert fasel.map_video({"link": "https://s/2", "label": "1080p"})["hd"] is True
    assert fasel.map_video({"link": "https://s/3", "hd": 1})["hd"] is True


def test_fasel_map_video_drops_blank_and_status_zero():
    assert fasel.map_video({"link": "", "url": ""}) == {}
    assert fasel.map_video({"link": "https://s/1", "status": 0}) == {}
    assert fasel.map_video({"file": "https://s/2", "downloadonly": 1})["downloadOnly"] is True
    assert fasel.map_video({"link": "https://s/3"})["server"] == "سيرفر"


def test_fasel_map_series_detail_and_season():
    root = {
        "id": 3, "name": "مسلسل", "overview": "ق", "poster_path": "/p.jpg",
        "vote_average": 8, "genreslist": ["دراما"],
        "seasons": [{"id": 30, "name": "الموسم الأول"}, {"id": 31}],
    }
    detail = fasel.map_series_detail(root, 3)
    assert detail["title"] == "مسلسل"
    assert detail["genres"] == ["دراما"]
    assert [s["id"] for s in detail["seasons"]] == [30, 31]
    assert detail["seasons"][1]["name"] == "الموسم 2"

    season = fasel.map_season({"episodes": [
        {"id": 100, "episode_number": 1, "name": "ح1", "imdb_external_id": "tt1"},
        {"id": 101, "name": "ح2", "imdb_id": "tt2", "videos": [{"link": "https://s/2"}]},
    ]}, 30)
    assert season["episodes"][0]["imdb"] == "tt1"
    assert season["episodes"][1]["number"] == 2
    assert season["episodes"][1]["imdb"] == "tt2"
    assert season["episodes"][1]["videos"][0]["link"] == "https://s/2"


def test_fasel_home_sections_order():
    root = {"popular": [{"id": 1, "title": "A", "type": "movie"}],
            "anime": [{"id": 2, "title": "B", "type": "anime"}],
            "livetv": [{"id": 3, "name": "Live", "videos": [{"link": "http://l/1"}]}]}
    sections = fasel.map_home_sections(root)
    names = [s["name"] for s in sections]
    assert names == ["POPULAR", "ANIME", "LIVE TV"]     # بنفس ترتيب المواصفة
    assert sections[0]["items"][0]["group"] == "FASEL HD / FILMS / POPULAR"
    assert sections[1]["items"][0]["kind"] == "ANIME"
    assert sections[1]["items"][0]["url"] == "faselhd://anime/2"
    assert sections[2]["items"][0]["url"] == "http://l/1"


def test_fasel_host_config_sanitising():
    cfg = fasel.map_host_config({"host_id": "h", "domains": ["a.com"],
                                 "urlsite": "not-http", "enableded": "http://real.site/x|",
                                 "enabled": False}, 0)
    assert cfg["urlSite"] == "http://real.site/x"
    assert cfg["enabled"] is False
    long_site = "http://" + "a" * 400
    assert fasel.map_host_config({"urlsite": long_site})["urlSite"] == ""


def test_fasel_host_bases_order():
    assert fasel.HOST_BASES[0] == "https://fashd.com/faselhd15/public/api/"
    assert fasel.HOST_BASES[1] == "https://kahitdgku.com/faselhd15/public/api/"
    assert fasel.HOST_BASES[2] == "https://hrrejhp.com/egybestanto/public/api/"


# ============================================================
# resolver — محلّلات pair / master / BaseVed
# ============================================================
def test_resolver_parse_pairs_braced():
    body = '{"file":"https://cdn/a.m3u8","label":"1080p"},{"file":"https://cdn/b.mp4","label":"720p"}'
    pairs = resolver.parse_pairs(body)
    assert pairs == [{"label": "1080p", "url": "https://cdn/a.m3u8"},
                     {"label": "720p", "url": "https://cdn/b.mp4"}]


def test_resolver_parse_pairs_newline_form():
    body = 'file:"https://cdn/a.m3u8", label:"auto"'
    pairs = resolver.parse_pairs(body)
    assert pairs and pairs[0]["url"] == "https://cdn/a.m3u8"
    assert pairs[0]["label"] == "auto"


def test_resolver_parse_pairs_json_form():
    body = json.dumps({"qualities": [{"quality": "1080p", "url": "https://cdn/x.m3u8"},
                                     {"label": "480p", "file": "https://cdn/y.mp4"}]})
    pairs = resolver.parse_pairs(body)
    assert {"label": "1080p", "url": "https://cdn/x.m3u8"} in pairs
    assert {"label": "480p", "url": "https://cdn/y.mp4"} in pairs


def test_resolver_parse_pairs_rejects_non_http_and_long_urls():
    body = '{"file":"ftp://bad/1","label":"x"},{"file":"https://ok/1","label":"y"}'
    pairs = resolver.parse_pairs(body)
    assert pairs == [{"label": "y", "url": "https://ok/1"}]
    long_url = "https://x/" + "a" * 2500
    assert resolver.parse_pairs('{"file":"%s","label":"z"}' % long_url) == []


def test_resolver_add_pair_label_normalisation():
    qualities: list = []
    resolver.add_pair(qualities, set(), "https://ok/1", '"أ،ب"')
    assert qualities[0]["label"] == "أ/ب"


def test_resolver_parse_master_literal():
    body = "\n".join([
        "#EXTM3U",
        "#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080",
        "1080/index.m3u8",
        "#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=640x360",
        "360/index.m3u8",
        "#EXT-X-STREAM-INF:BANDWIDTH=800000",
        "low/index.m3u8",
    ])
    variants = resolver.parse_master(body, base="https://cdn/master.m3u8")
    assert variants[0] == {"label": "1920x1080", "url": "https://cdn/1080/index.m3u8"}
    assert variants[1]["label"] == "640x360"
    assert variants[2]["label"] == "800k"                 # مفيش resolution → bandwidth/1000
    assert variants[2]["url"] == "https://cdn/low/index.m3u8"


def test_resolver_parse_base_ved_response_literal():
    body = json.dumps({"status": "success",
                       "Quality": ["1080p", "720p"],
                       "filtered_content": ["https://a/1.mp4", "https://a/2.mp4"]})
    result = resolver.parse_base_ved_response(body)
    assert result == [{"label": "1080p", "url": "https://a/1.mp4"},
                      {"label": "720p", "url": "https://a/2.mp4"}]


def test_resolver_parse_base_ved_response_status_and_label_fallback():
    bad = json.dumps({"status": "error", "Quality": ["x"], "urls": ["https://a/1.mp4"]})
    assert resolver.parse_base_ved_response(bad) == []
    fallback = json.dumps({"status": "", "qualities": ["", ""],
                           "urls": ["https://a/v_1080.mp4", "https://a/v_360.mp4"]})
    result = resolver.parse_base_ved_response(fallback)
    assert [q["label"] for q in result] == ["1080p", "360p"]


def test_resolver_constants_present():
    assert "multiquality.host" in resolver.SOURCE_HOSTS
    assert "kawaiifansub.com" in resolver.SOURCE_HOSTS
    assert "streamwish" in resolver.EMBED_HOST_HINTS
    assert "youtube.com/embed" in resolver.EMBED_HOST_HINTS
    assert resolver.BASEVED_ENDPOINTS["updown"][0] == "https://mawdhou3.com/scrapefinal/updown.php"
    assert resolver.BASEVED_ENDPOINTS["egy"][0] == "https://mawdhou3.com/scrapeamine/scriptEgybest.php"


def test_resolver_scraper_selection_and_referer():
    assert resolver.scrapers_for("", "https://x/?p=12") == resolver.SCRAPER_VIP
    assert resolver.scrapers_for("shahed", "https://x/1") == resolver.SCRAPER_SHAHED
    assert resolver.scrapers_for("updown", "https://x/1") == resolver.SCRAPER_UPDOWN
    assert resolver.scrapers_for("", "https://x/1") == resolver.SCRAPER_GENERIC
    assert resolver.fasel_referer("https://www.fasel-hd.com/?p=1") == "https://www.fasel-hd.com/"
    assert resolver.fasel_referer("https://other.site/x") is None
    assert resolver.host_referer("https://cdn.site/a/b") == "https://cdn.site/"


def test_resolver_build_api_url_no_duplicate_marker():
    assert resolver._build_api_url("https://s/api=", "http://v/1") == "https://s/api=http%3A%2F%2Fv%2F1"
    assert resolver._build_api_url("https://s/x", "http://v/1") == "https://s/x?api=http%3A%2F%2Fv%2F1"
    assert resolver._build_api_url("https://w.workers.dev?url=", "http://v/1") == "https://w.workers.dev?url=http%3A%2F%2Fv%2F1"


def test_resolver_resolve_blank_returns_none_source():
    import asyncio
    result = asyncio.run(resolver.resolve({"link": "   "}, []))
    assert result == {"qualities": [], "direct": None, "source": "none"}


# ============================================================
# firebase — vodGroup + inferPackage + خرائط العناصر
# ============================================================
def test_firebase_vod_group():
    assert firebase_catalog.vod_group("أفلام", "MOVIES") == "FILMS:أفلام"
    assert firebase_catalog.vod_group("مسلسلات", "SERIES") == "SERIES:مسلسلات"
    assert firebase_catalog.vod_group("My Series", "VOD") == "SERIES:My Series"
    assert firebase_catalog.vod_group("أنمي", "CARTOONS") == "CARTOONS:أنمي"
    assert firebase_catalog.vod_group("Cartoon Time", "LIVE") == "Cartoon Time"
    assert firebase_catalog.is_vod_scope("movies") is True
    assert firebase_catalog.is_vod_scope("LIVE") is False


def test_firebase_infer_package():
    assert firebase_catalog.infer_package("beIN Sports 1") == "BEIN SPORT"
    assert firebase_catalog.infer_package("TOD TV") == "TOD Sports"
    assert firebase_catalog.infer_package("SHAHID Sports") == "SHAHID SPORT"
    assert firebase_catalog.infer_package("MBC 2") == "MBC GROUP"
    assert firebase_catalog.infer_package("Rotana Cinema") == "Rotana"
    assert firebase_catalog.infer_package("قناة الكأس") == "ALKASS"
    assert firebase_catalog.infer_package("Abu Dhabi Sports") == "Abu Dhabi Sports"
    assert firebase_catalog.infer_package("Sky News") == "NEWS"
    assert firebase_catalog.infer_package("Random") == "OTHER"


def test_firebase_url_normalisation():
    assert firebase_catalog.normalize_scraping_url("https://old.xyz/watch/x") == "https://k.alooytv10.com/watch/x"
    assert firebase_catalog.normalize_scraping_url("https://plain.com/x") == "https://plain.com/x"
    assert firebase_catalog.normalize_image_url("//cdn/x.jpg") == "https://cdn/x.jpg"
    assert firebase_catalog.normalize_image_url("https://cdn/x.jpg") == "https://cdn/x.jpg"
    assert firebase_catalog.normalize_image_url("img/x.jpg") == "https://k.alooytv10.com/img/x.jpg"


def test_firebase_map_category_and_channel_items():
    category = firebase_catalog.map_category({"id": "c1", "title": "أفلام", "scope": "movies",
                                              "order": 2, "targetUrl": "https://old.xyz/m",
                                              "imageUrl": "//img/x.jpg"})
    assert category["scope"] == "MOVIES"
    assert category["targetUrl"] == "https://k.alooytv10.com/m"
    assert category["image"] == "https://img/x.jpg"

    items = firebase_catalog.map_channel_items(
        {"title": "قناة", "servers": [{"url": "http://a/1", "name": "s1", "userAgent": "UA1"},
                                      {"url": "http://a/2"}]},
        "key1", 1, {"id": "c1", "title": "LIVE", "scope": "LIVE", "order": 0, "image": ""})
    assert items[0]["id"] == "firebase_key1"
    assert items[0]["name"] == "قناة"
    assert items[0]["httpUserAgent"] == "UA1"
    assert items[1]["id"] == "firebase_key1_s1"
    assert items[1]["name"].startswith("قناة · ")


def test_firebase_build_channels_object_and_sorting():
    categories = [firebase_catalog.map_category({"id": "c2", "title": "B", "scope": "LIVE", "order": 2}),
                  firebase_catalog.map_category({"id": "c1", "title": "A", "scope": "LIVE", "order": 1})]
    channels_raw = {"k1": {"categoryId": "c2", "title": "ch2", "url": "http://a/2"},
                    "k2": {"categoryId": "c1", "title": "ch1", "url": "http://a/1"}}
    items = firebase_catalog.build_channels(categories, channels_raw)
    assert [i["name"] for i in items] == ["ch1", "ch2"]     # حسب order الفئة


def test_firebase_parse_movie_html():
    html = (
        '<div class="post movie-img"><h3><a href="/watch/the-movie.html">فيلم رائع</a></h3>'
        '<img data-src="https://cdn/img1.jpg"></div>'
        '<div class="post movie-img"><h3><a href="/watch/my-series.html">مسلسل عربي</a></h3>'
        '<img src="https://cdn/img2.jpg"></div>'
        '<div class="post movie-img"><h3><a href="/watch/skip.html">x</a></h3>'
        '<img data-src="https://cdn/blank_thumbnail.png"></div>'
    )
    items = firebase_catalog.parse_movie_html(html, "أفلام")
    assert items[0]["id"] == "vod_films_the-movie"
    assert items[0]["group"] == "FILMS:أفلام"
    assert items[0]["logoUrl"] == "https://cdn/img1.jpg"
    assert items[1]["id"] == "vod_series_my-series"
    assert items[1]["type"] == "SERIES"


def test_firebase_split_catalog():
    items = [
        {"isLive": True, "group": "LIVE:X"},
        {"isLive": False, "group": "FILMS:X"},
        {"isLive": False, "group": "SERIES:X"},
        {"isLive": False, "group": "CARTOONS:X"},
    ]
    split = firebase_catalog.split_catalog(items)
    assert len(split["channels"]) == 1
    assert len(split["films"]) == 1
    assert len(split["series"]) == 1
    assert len(split["cartoons"]) == 1


# ============================================================
# channels — محلّل M3U + سلامة القنوات الافتراضية
# ============================================================
def test_channels_parse_m3u_literal():
    playlist = (
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="id1" tvg-name="Name1" tvg-logo="http://l/1.png" '
        'group-title="news" tvg-language="AR" http-user-agent="UA1" referrer="http://ref/",قناة الأولى\n'
        'http://stream/1.m3u8\n'
        '#EXTINF:-1,قناة بدون وصف\n'
        'http://stream/2.m3u8\n'
    )
    parsed = channels.parse_m3u(playlist)
    assert len(parsed) == 2
    first = parsed[0]
    assert first["name"] == "قناة الأولى"
    assert first["group"] == "NEWS"                     # كابيتال
    assert first["tvg_id"] == "id1"
    assert first["tvg_name"] == "Name1"
    assert first["language"] == "AR"
    assert first["httpUserAgent"] == "UA1"
    assert first["httpReferrer"] == "http://ref/"
    assert parsed[1]["group"] == "IPTV"                 # الافتراضي
    assert parsed[1]["language"] == "EN"                # الافتراضي


def test_channels_parse_m3u_empty_and_non_url():
    assert channels.parse_m3u("") == []
    assert channels.parse_m3u("#EXTM3U\n#EXTINF:-1,x\nnot-a-url\n") == []


def test_channels_default_channels_integrity():
    assert len(channels.DEFAULT_CHANNELS) == 10
    assert len(channels.DEFAULT_FILMS) == 3
    assert len(channels.DEFAULT_CARTOONS) == 2
    assert len(channels.default_channels()) == 15
    ids = [c["id"] for c in channels.default_channels()]
    assert len(ids) == len(set(ids))                     # كل الـ id فريدة


def test_channels_default_channels_exact_urls():
    by_id = {c["id"]: c for c in channels.DEFAULT_CHANNELS}
    assert by_id["ch_01"]["url"] == "https://live-hls-web-aja.getaj.net/AJA/01.m3u8"
    assert by_id["ch_02"]["url"] == "https://tv-trtarabi.medya.trt.com.tr/master.m3u8"
    assert by_id["ch_03"]["url"] == "https://live-hls-web-ajm.getaj.net/AJM/01.m3u8"
    assert by_id["ch_04"]["url"] == "https://ntv1.akamaized.net/hls/live/2014075/NASA-NTV1-HLS/master.m3u8"
    assert by_id["ch_05"]["url"] == "https://rbmn-live.akamaized.net/hls/live/590964/BoRB-AT/master.m3u8"
    assert by_id["ch_06"]["url"] == "https://tv-trtworld.medya.trt.com.tr/master.m3u8"
    assert by_id["ch_07"]["url"] == "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/index.m3u8"
    assert by_id["ch_08"]["url"].endswith("tears-of-steel.ism/.m3u8")
    assert by_id["ch_09"]["url"] == "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
    assert by_id["ch_10"]["url"].endswith("bipbop_16x9_variant.m3u8")
    # المجموعات والـ isLive
    assert by_id["ch_01"]["group"] == "ARABIC"
    assert by_id["ch_04"]["group"] == "TECH"
    assert by_id["ch_05"]["group"] == "SPORTS"
    assert by_id["ch_08"]["isLive"] is False
    assert by_id["ch_09"]["isLive"] is False
    assert by_id["ch_01"]["isLive"] is True
    assert all(c.get("logoUrl") for c in channels.default_channels())
    assert all(c.get("language") in ("AR", "EN") for c in channels.default_channels())


def test_channels_radio_catalog_structure():
    catalog = channels.load_radio_catalog()
    types = [c["type"] for c in catalog]
    assert types == ["modern", "classic", "radio_quran", "islamic", "music_artists", "music_radios"]
    assert len(catalog) == 6
    assert channels.RADIO_TYPE_ICON["radio_quran"] == "MenuBook"
    assert channels.RADIO_TYPE_ICON["music_artists"] == "Mic"


def test_channels_radio_stations_custom():
    stations = channels.radio_stations(["محطتي|||http://radio/1"])
    assert any(s["group"] == "RADIO/CUSTOM" and s["url"] == "http://radio/1" for s in stations)


def test_channels_parse_genre_html():
    html = (
        '<div class="movie-img"><h3><a href="/watch/x.html">اسم العمل</a></h3>'
        '<img data-src="https://cdn/x.jpg"> 5 عدد الحلقات</div>'
    )
    cards = channels.parse_genre_html(html, "https://k.alooytv10.com")
    assert cards[0]["url"] == "https://k.alooytv10.com/watch/x.html"
    assert cards[0]["logoUrl"] == "https://cdn/x.jpg"
    assert cards[0]["episodes"] == 5


def test_channels_parse_watch_html():
    html = ('<title>عمل ما</title><img src="https://cdn/p.jpg">'
            '<div class="btn-ep"><source src="https://cdn/ep1.m3u8"></div>'
            '<div class="btn-ep"><source src="https://cdn/ep2.m3u8"></div>')
    data = channels.parse_watch_html(html, "https://k.alooytv10.com")
    assert data["name"] == "عمل ما"
    assert data["poster"] == "https://cdn/p.jpg"
    assert [e["url"] for e in data["episodes"]] == ["https://cdn/ep1.m3u8", "https://cdn/ep2.m3u8"]


# ============================================================
# السجل (registry)
# ============================================================
def test_registry_sources_and_gateways():
    from services.app_sources import SOURCES, GATEWAYS, enabled, set_enabled
    assert set(SOURCES) == {"golive", "fasel", "firebase", "channels"}
    assert GATEWAYS == {"googlefire": True, "faselhd": True, "hikaye": True, "custom": True}
    assert enabled("golive") and enabled("fasel") and enabled("firebase") and enabled("channels")
    set_enabled("faselhd", False)
    try:
        assert enabled("fasel") is False
    finally:
        set_enabled("faselhd", True)
    assert enabled("fasel") is True
