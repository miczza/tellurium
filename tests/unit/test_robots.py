"""robots.txt parsing and matching (RFC 9309), the cache, and the outcome of a fetch."""

from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace

import pytest

from tellurium.browser import robots
from tellurium.browser.robots import RobotsRules, parse

# RFC 9309 §5.1
SIMPLE = """\
User-Agent: *
Disallow: *.gif$
Disallow: /example/
Allow: /publications/

User-Agent: foobot
Disallow:/
Allow:/example/page.html
Allow:/example/allowed.gif

User-Agent: barbot
User-Agent: bazbot
Disallow: /example/page.html

User-Agent: quxbot

EOF
"""


@pytest.mark.parametrize(
    "agent, path, allowed",
    [
        ("foobot", "/example/page.html", True),
        ("foobot", "/example/allowed.gif", True),
        ("foobot", "/example/disallowed.gif", False),
        ("foobot", "/", False),
        ("FooBot", "/example/page.html", True),  # product tokens: case-insensitive
        ("barbot", "/example/page.html", False),
        ("bazbot", "/example/page.html", False),
        ("barbot", "/example/allowed.gif", True),  # its group has no gif rule
        ("quxbot", "/example/", True),  # an empty group allows everything
        ("quxbot", "/x.gif", True),
        ("*", "/example/", False),
        ("*", "/example/page.html", False),
        ("*", "/publications/", True),
        ("*", "/image.gif", False),
        ("*", "/image.gif?x=1", True),  # $ anchors the end of path and query
        ("otherbot", "/example/", False),  # no group of its own: the * one
        ("otherbot", "/elsewhere", True),
    ],
)
def test_rfc_9309_simple_example(agent, path, allowed):
    assert parse(SIMPLE, agent).allows(path) is allowed


def test_rfc_9309_longest_match():  # §5.2
    rules = parse(
        "User-Agent: foobot\nAllow: /example/page/\nDisallow: /example/page/disallowed.gif\n",
        "foobot",
    )
    assert rules.allows("/example/page/")
    assert rules.allows("/example/page/other")
    assert not rules.allows("/example/page/disallowed.gif")


def test_allow_wins_a_tie():
    rules = parse("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert rules.allows("/page")
    rules = parse("User-agent: *\nAllow: /page\nDisallow: /page\n")
    assert rules.allows("/page")


@pytest.mark.parametrize(
    "pattern, path, matches",
    [
        ("/fish", "/fish", True),
        ("/fish", "/fish.html", True),
        ("/fish", "/fish/salmon.html", True),
        ("/fish", "/Fish.asp", False),  # paths are case-sensitive
        ("/fish", "/catfish", False),
        ("/fish*", "/fishheads", True),
        ("/fish/", "/fish", False),
        ("/*.php", "/index.php", True),
        ("/*.php", "/filepath/index.php", True),
        ("/*.php", "/index.php?param", True),
        ("/*.php", "/", False),
        ("/*.php$", "/filepath/index.php", True),
        ("/*.php$", "/index.php?param", False),
        ("/*.php$", "/index.php5", False),
        ("/fish*.php", "/fishheads/catfish.php?parameters", True),
        ("/fish*.php", "/Fish.PHP", False),
        ("/a$b", "/a$b", True),  # $ only anchors at the end
        ("/this/*/exactly", "/this/path/exactly", True),
        ("/this/path/exactly$", "/this/path/exactly/", False),
    ],
)
def test_wildcards(pattern, path, matches):
    rules = parse(f"User-agent: *\nDisallow: {pattern}\n")
    assert rules.allows(path) is not matches


@pytest.mark.parametrize(
    "pattern, path",
    [
        ("/foo/bar?baz=https://foo.bar", "/foo/bar?baz=https://foo.bar"),
        ("/foo/bar/ツ", "/foo/bar/%E3%83%84"),  # §2.2.2: non-ASCII is percent-encoded
        ("/foo/bar/%E3%83%84", "/foo/bar/%E3%83%84"),
        ("/foo/bar/%e3%83%84", "/foo/bar/%E3%83%84"),  # hex case does not matter
        ("/foo/bar/%62%61%7A", "/foo/bar/baz"),  # unreserved octets are decoded
        ("/foo/bar/baz", "/foo/bar/%62%61%7A"),
    ],
)
def test_percent_encoding_is_normalised(pattern, path):
    assert not parse(f"User-agent: *\nDisallow: {pattern}\n").allows(path)


def test_an_encoded_reserved_character_stays_encoded():
    rules = parse("User-agent: *\nDisallow: /a%2Fb\n")
    assert not rules.allows("/a%2Fb")
    assert rules.allows("/a/b")


def test_robots_txt_itself_is_always_allowed():
    assert parse("User-agent: *\nDisallow: /\n").allows("/robots.txt")
    assert robots.DISALLOW_ALL.allows("/robots.txt")
    assert not robots.DISALLOW_ALL.allows("/")


def test_empty_disallow_allows_everything():
    assert parse("User-agent: *\nDisallow:\n").allows("/anything")


def test_groups_of_the_same_agent_are_merged():
    text = "User-agent: a\nDisallow: /x\n\nUser-agent: b\nDisallow: /y\n\nUser-agent: a\nDisallow: /z\n"
    rules = parse(text, "a")
    assert not rules.allows("/x") and not rules.allows("/z")
    assert rules.allows("/y")


def test_the_star_groups_are_merged_too():
    rules = parse("User-agent: *\nDisallow: /x\n\nUser-agent: *\nDisallow: /z\n")
    assert not rules.allows("/x") and not rules.allows("/z")


def test_no_group_for_the_agent_and_no_star_group_allows_everything():
    assert parse("User-agent: other\nDisallow: /\n", "mine").allows("/")


def test_rules_before_any_user_agent_are_ignored():
    assert parse("Disallow: /\nUser-agent: *\nDisallow: /x\n").allows("/")


def test_comments_blank_lines_case_and_line_endings():
    text = "﻿# comment\r\nUSER-AGENT : *  # trailing\r\n\r\nDISALLOW:/x # no\rallow: /x/y\n"
    rules = parse(text)
    assert not rules.allows("/x")
    assert rules.allows("/x/y")


def test_other_records_do_not_split_a_group():
    text = "User-agent: *\nSitemap: https://a.test/s.xml\nCrawl-delay: 10\nDisallow: /x\n"
    assert not parse(text).allows("/x")


def test_agent_value_is_matched_by_its_product_token():
    assert not parse("User-agent: mybot/1.2\nDisallow: /\n", "MyBot").allows("/")


def test_a_user_agent_after_rules_starts_a_new_group():
    text = "User-agent: a\nDisallow: /x\nUser-agent: b\nDisallow: /y\n"
    assert parse(text, "a").allows("/y")
    assert parse(text, "b").allows("/x")


def test_only_the_first_500_kib_are_parsed():
    filler = "# " + "x" * 1000 + "\n"
    text = "User-agent: *\n" + filler * 600 + "Disallow: /late\n"
    assert parse(text).allows("/late")
    assert not parse("User-agent: *\n" + filler * 10 + "Disallow: /late\n").allows("/late")


def test_a_pathological_pattern_is_matched_in_linear_time():
    rules = parse("User-agent: *\nDisallow: /" + "*a" * 200 + "b\n")
    assert rules.allows("/" + "a" * 5000)


def test_allow_all_and_disallow_all():
    assert RobotsRules(()).allows("/x")
    assert robots.ALLOW_ALL.allows("/x")


@pytest.mark.parametrize(
    "url, target",
    [
        ("http://Site.Test/a/b?c=d#frag", ("http://site.test", "/a/b?c=d")),
        ("https://site.test", ("https://site.test", "/")),
        ("https://site.test:443/x", ("https://site.test", "/x")),
        ("http://site.test:8080/x", ("http://site.test:8080", "/x")),
        ("http://[::1]:81/", ("http://[::1]:81", "/")),
        ("about:blank", None),
        ("data:text/html,x", None),
        ("file:///etc/hostname", None),
        ("chrome://version", None),
    ],
)
def test_split_url(url, target):
    assert robots.split_url(url) == target


@pytest.mark.parametrize(
    "status, allowed",
    [(200, False), (204, False), (404, True), (403, True), (429, True), (500, False), (503, False)],
)
def test_outcome_by_status(status, allowed):
    rules = robots.outcome(status, b"User-agent: *\nDisallow: /\n", "*")
    assert rules.allows("/page") is allowed


def test_outcome_of_an_empty_2xx_body_allows_everything():
    assert robots.outcome(200, b"", "*").allows("/page")


def test_outcome_of_a_body_that_is_not_utf8():
    body = b"User-agent: *\nDisallow: /\xff\xfe\nDisallow: /y\n"
    assert not robots.outcome(200, body, "*").allows("/y")


def test_agent_must_be_a_product_token():
    for bad in ("", "my bot", "bot/1.0", "bot2", None):
        with pytest.raises(ValueError, match="robots_agent"):
            robots.Robots(respect=True, agent=bad)
    robots.Robots(respect=True, agent="my-bot_x")


def test_robots_disallowed_error_is_a_navigation_error():
    from tellurium import NavigationError, RobotsDisallowedError

    exc = RobotsDisallowedError("http://site.test/private?q", "http://site.test", "/private?q")
    assert isinstance(exc, NavigationError)
    assert str(exc) == "robots.txt of http://site.test disallows /private?q"
    assert exc.url == "http://site.test/private?q"
    assert (exc.origin, exc.path) == ("http://site.test", "/private?q")


_IDS = itertools.count()


def _browser():
    return SimpleNamespace(_contexts={})


def _tab(browser=None, context: str | None = None):
    """A stand-in tab: what Robots reads of it is its browser and context."""
    browser = browser or _browser()
    tab = SimpleNamespace(_browser=browser, _target_id=next(_IDS))  # distinct: compared by ==
    if context is not None:
        browser._contexts.setdefault(context, SimpleNamespace(_tabs=[]))._tabs.append(tab)
    return tab


@pytest.fixture
def frames(monkeypatch):
    """robots.open_frame replaced: each call adds a frame named after its context."""
    made: list = []

    async def open_frame(browser, context_id):
        made.append(robots.Frame(session=None, target_id=f"{context_id}#{len(made)}"))
        return made[-1]

    monkeypatch.setattr(robots, "open_frame", open_frame)
    return made


def frames_of(made):
    return [tuple(f.target_id.split("#")) for f in made]


class _Fetcher:
    """A stand-in for the Chrome download: counts calls, answers when told."""

    def __init__(self, rules: RobotsRules = robots.ALLOW_ALL):
        self.calls: list[str] = []
        self.rules = rules
        self.release = asyncio.Event()

    async def __call__(self, frame, origin: str, agent: str) -> tuple[RobotsRules, float]:
        self.calls.append(origin)
        await self.release.wait()
        return self.rules, robots.CACHE_TTL


async def test_one_download_per_origin_for_concurrent_callers(frames, monkeypatch):
    fetcher = _Fetcher()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    waits = [asyncio.ensure_future(r.rules(_tab(), "http://a.test")) for _ in range(100)]
    await asyncio.sleep(0)
    fetcher.release.set()
    assert all(x is robots.ALLOW_ALL for x in await asyncio.gather(*waits))
    assert fetcher.calls == ["http://a.test"]
    await r.rules(_tab(), "http://a.test")  # cached
    assert fetcher.calls == ["http://a.test"]


async def test_the_starter_being_cancelled_does_not_cancel_the_others(frames, monkeypatch):
    fetcher = _Fetcher()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    first = asyncio.ensure_future(r.rules(_tab(), "http://a.test"))
    await asyncio.sleep(0)
    second = asyncio.ensure_future(r.rules(_tab(), "http://a.test"))
    await asyncio.sleep(0)
    first.cancel()
    await asyncio.sleep(0)
    fetcher.release.set()
    assert await second is robots.ALLOW_ALL
    assert first.cancelled()
    assert fetcher.calls == ["http://a.test"]


async def test_a_cancelled_lone_caller_still_fills_the_cache(frames, monkeypatch):
    fetcher = _Fetcher()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    first = asyncio.ensure_future(r.rules(_tab(), "http://a.test"))
    await asyncio.sleep(0)
    first.cancel()
    fetcher.release.set()
    await asyncio.sleep(0.01)
    await r.rules(_tab(), "http://a.test")
    assert fetcher.calls == ["http://a.test"]


async def test_a_hidden_target_that_went_is_opened_again(frames, monkeypatch):
    seen: list = []

    async def download(frame, origin, agent):
        seen.append(frame)
        if len(seen) == 1:
            raise ConnectionError("the hidden target closed")
        return robots.DISALLOW_ALL, robots.CACHE_TTL

    monkeypatch.setattr(robots, "download", download)
    r = robots.Robots()
    assert await r.rules(_tab(), "http://a.test") is robots.DISALLOW_ALL
    assert len(frames) == 2 and seen == frames


async def test_one_hidden_target_per_context(frames, monkeypatch):
    fetcher = _Fetcher()
    fetcher.release.set()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    browser = _browser()
    plain, other = _tab(browser), _tab(browser, context="C1")
    await asyncio.gather(r.rules(plain, "http://a.test"), r.rules(plain, "http://b.test"))
    await r.rules(other, "http://a.test")  # another context: its own entry
    assert sorted(fetcher.calls) == ["http://a.test", "http://a.test", "http://b.test"]
    assert [ctx for ctx, _ in frames_of(frames)] == ["", "C1"]
    r.forget_context("C1")
    await r.rules(other, "http://c.test")
    assert [ctx for ctx, _ in frames_of(frames)] == ["", "C1", "C1"]


async def test_entries_expire(frames, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(robots, "_now", lambda: clock[0])
    fetcher = _Fetcher()
    fetcher.release.set()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    await r.rules(_tab(), "http://a.test")
    clock[0] += robots.CACHE_TTL - 1
    await r.rules(_tab(), "http://a.test")
    assert len(fetcher.calls) == 1
    clock[0] += 2
    await r.rules(_tab(), "http://a.test")
    assert len(fetcher.calls) == 2


async def test_the_cache_keeps_the_most_recent_origins(frames, monkeypatch):
    fetcher = _Fetcher()
    fetcher.release.set()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    for i in range(robots.CACHE_SIZE):
        await r.rules(_tab(), f"http://{i}.test")
    await r.rules(_tab(), "http://0.test")  # used again: now the newest
    await r.rules(_tab(), "http://new.test")  # pushes out the oldest, 1.test
    count = len(fetcher.calls)
    await r.rules(_tab(), "http://0.test")
    assert len(fetcher.calls) == count
    await r.rules(_tab(), "http://1.test")
    assert len(fetcher.calls) == count + 1


async def test_close_cancels_the_downloads_in_flight(frames, monkeypatch):
    fetcher = _Fetcher()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots()
    waiter = asyncio.ensure_future(r.rules(_tab(), "http://a.test"))
    await asyncio.sleep(0)
    r.close()
    with pytest.raises(ConnectionError):
        await waiter


async def test_check_without_the_flag_downloads_nothing(monkeypatch):
    fetcher = _Fetcher()
    monkeypatch.setattr(robots, "download", fetcher)
    await robots.Robots(respect=False).check(_tab(), "http://a.test/private")
    assert fetcher.calls == []


async def test_check_raises_for_a_disallowed_path(frames, monkeypatch):
    fetcher = _Fetcher(parse("User-agent: *\nDisallow: /private\n"))
    fetcher.release.set()
    monkeypatch.setattr(robots, "download", fetcher)
    r = robots.Robots(respect=True)
    await r.check(_tab(), "http://a.test/public")
    with pytest.raises(robots.RobotsDisallowedError, match="robots.txt of http://a.test"):
        await r.check(_tab(), "http://a.test/private/x")
    await r.check(_tab(), "about:blank")
    assert fetcher.calls == ["http://a.test"]
