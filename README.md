# Tellurium

Browser automation for scraping protected sites. Zero dependencies. Stealth by default.

Tellurium controls Chrome via CDP pipe transport (no detectable WebSocket port), injects stealth patches through a real Chrome extension (no detectable script injection), and simulates human input with biomechanically correct mouse and keyboard dynamics.

```python
import asyncio
from tellurium import Browser

async def main():
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        tab = await browser.new_tab("https://example.com")
        el = await tab.select("h1")
        print(await el.text())

asyncio.run(main())
```

## Installation

```bash
pip install tellurium
```

Optional MCP server for LLM agents (`tellurium mcp`, see [MCP server](#mcp-server-tellurium-mcp)):

```bash
pip install tellurium[mcp]
```

Optional GeoIP support (auto-detect timezone/locale from proxy exit IP):

```bash
pip install tellurium[geoip]
```

Then fetch a country database once (offline lookups):

```bash
tellurium download-geoip                                 # DB-IP Country Lite, no account
tellurium download-geoip --maxmind-license-key KEY       # MaxMind GeoLite2-Country
```

The database lives in `~/.tellurium/geolite2/` (override with `TELLURIUM_GEOIP_DB`). Without a database tellurium falls back to a one-shot online IP-to-country lookup and logs a warning.

## Quick Start

### Navigate and extract content

```python
browser = await Browser.launch(headless=True)
async with browser:
    tab = await browser.new_tab("https://news.ycombinator.com")
    
    # Select elements
    titles = await tab.select_all(".titleline > a")
    for title in titles[:5]:
        print(await title.text(), "-", await title.attr("href"))
```

### Fill a form

```python
browser = await Browser.launch(headless=True, stealth=True)
async with browser:
    tab = await browser.new_tab("https://example.com/login")
    
    email = await tab.select("input[name=email]")
    await email.type("user@example.com", human=True)
    
    password = await tab.select("input[name=password]")
    await password.type("secret123", human=True)
    
    await (await tab.find("Sign In")).click(human=True)
    await tab.wait_for_navigation()
```

### Capture API responses

```python
browser = await Browser.launch(headless=True)
async with browser:
    tab = await browser.new_tab("https://example.com")
    await tab.capture(log=True, log_filter="json")
    
    await (await tab.find("Load More")).click()
    req = await tab.wait_for_request("*/api/feed*")
    data = await req.json()
    print(data)
```

## Using tellurium from an LLM agent

An agent does not read HTML: it reads a compact accessibility snapshot, picks a
ref, and acts on it. `tab.snapshot()` gives one line per node, with a ref on
every node you can act on:

```text
- link "Report" [ref=e1]
- link "Big file" [ref=e2]
- iframe [ref=e3]:
  - link "Inner" [ref=e4]
```

`tab.select("@e1")` (or `tab.ref("e1")`) turns a ref back into a normal
`Element`, so `click()`, `type()` and `human=True` work as usual. A complete
run, from snapshot to downloaded file:

```python
import asyncio
import re

from tellurium import Browser


async def main(url: str) -> None:
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.get(url)
        page = await tab.snapshot(interactive=True)  # what the LLM reads
        print(page)
        ref = re.search(r'- link "Report" \[ref=(e\d+)\]', page).group(1)  # what it picks
        async with tab.expect_download() as info:
            await (await tab.select(f"@{ref}")).click(human=True)
        download = await info.value
        print(download.suggested_filename, await download.path())


asyncio.run(main("http://127.0.0.1:8000/download.html"))
```

- **Snapshot options**: `interactive=True` keeps only what can be used,
  `selector="form"` snapshots one subtree, `depth=` limits nesting,
  `max_chars=` cuts the text with an explicit `[truncated: …]` line.
  `snapshot_nodes()` returns the same tree as `SnapshotNode(ref, role, name,
  value, states, children)`. Pages over `max_nodes=` (default 50000) raise
  `SnapshotTooLargeError`: snapshot a part with `selector=`.
- **Ref lifetime**: a node keeps its ref across snapshots of the same document.
  After a navigation, or once the node left the page (an SPA re-render), its
  ref raises `StaleElementError`, never acts on another element; a ref no
  snapshot gave out raises `LookupError`. Take a new snapshot and retry.
- **Frames**: same-process iframes are part of the snapshot and their refs
  work like any other; a cross-site iframe shows as `- iframe "<url>" [oopif]`.
- **Downloads**: `tab.expect_download(timeout=30)` takes the next download of
  the tab (its iframes included). `download.url`, `suggested_filename`,
  `await download.path()`, `await download.save_as(path)`, `await
  download.cancel()`; failures raise `DownloadError`. Files go to a folder the
  browser owns and removes on `close()`, unless `Browser.launch(downloads_dir=…)`
  or `browser.new_context(downloads_dir=…)` names one to keep. `tab.get()` on
  a download URL raises `NavigationError`: use `expect_download()` instead.

## MCP server (`tellurium mcp`)

The same loop, for agents that speak the Model Context Protocol (Claude Code,
Codex, …). Install the extra and register the server; it talks over stdio, so
no port is opened:

```bash
pip install 'tellurium[mcp]'
claude mcp add tellurium -- tellurium mcp            # add --headed to watch the browser
```

A typical run: `session-open {"name": "github"}` returns a `sessionId` and the
`targetId` of its first tab; `navigate`, `snapshot`, then `fill` / `click` by
ref; `download` returns the saved file's path; `session-close` saves. Next
time `session-open {"name": "github"}` brings back the same identity (cookies,
storage, fingerprint seed). Without a name the session is throwaway.

| Tools | |
|---|---|
| `session-open`, `session-list`, `session-close` | browsers; a named session lives in `~/.tellurium/sessions/<name>` |
| `tab-open`, `tab-list`, `tab-close` | tabs; popups appear in `tab-list` with their own `targetId` |
| `navigate` | `url`, or `history`: `back` / `forward` / `reload` |
| `snapshot` | the accessibility snapshot (`interactive`, `selector`, `depth`, `maxChars`) |
| `click`, `fill`, `press`, `select-option`, `check`, `hover`, `scroll` | act on a ref; human-like input unless `human: false` |
| `download` | click a ref, wait, save to `~/.tellurium/downloads/` and return the path |
| `wait-for`, `get-text`, `screenshot`, `eval` | wait for text / ref / URL; read text; PNG image; JavaScript |

- Every page tool takes the required `targetId`; arguments are checked against
  the tool's schema, so an unknown argument is an error, not ignored.
- Actions return `{ok, url, title, navigated}`, not a new snapshot: the agent
  asks for one when the page changed.
- Errors come back as tool errors that say what to do: a stale ref asks for a
  new snapshot, a covered element names what is on top, a page too large to
  snapshot suggests `selector=` or `interactive=true`.
- When the client disconnects (or only stops reading replies), or on
  SIGTERM/SIGINT, every browser is closed
  and every named session saved.
- `navigate` and `tab-open` open only `http`, `https`, `about:blank` and `data:`
  URLs. `file:` (local files), `chrome:`, `chrome-extension:`, `devtools:`,
  `view-source:` and `javascript:` are refused, so a page that talks the agent
  into it cannot read your files; `tellurium mcp --allow-local-urls` lifts
  this. Chrome itself refuses a web page's redirect to `file:`.
- `TELLURIUM_HOME` moves `~/.tellurium` (sessions and downloads) elsewhere.

---

## API Reference

### Browser

The main entry point. Launches and controls a Chrome instance.

#### `Browser.launch(**kwargs) -> Browser`

Launches Chrome and returns a ready `Browser`. Must be awaited.

```python
browser = await Browser.launch(
    headless=False,         # Run with visible window (default: False)
    stealth=True,           # Enable anti-detection (default: False)
    seed=42069,             # Deterministic fingerprint (default: random)
    proxy="socks5://u:p@host:1080",  # Proxy with optional auth
    browser="stock",        # "stock" (default) or "patched"
    executable="/path/to/chrome",    # Explicit binary path
    user_data_dir="/path/to/profile", # Persistent profile
    args=["--disable-gpu"],          # Extra Chrome flags
    timezone="Europe/Rome",          # Manual timezone override
    languages=["it-IT", "it", "en"], # Manual navigator.languages override
    viewport=(1280, 720),            # Window size
    mouse_profile="careful",         # Wind Mouse personality
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `headless` | `bool` | `False` | Run without visible window |
| `stealth` | `bool` | `False` | Enable anti-detection |
| `seed` | `int \| None` | `None` | Fingerprint seed (random if None) |
| `proxy` | `str \| None` | `None` | Proxy URL (http, https, socks5) |
| `browser` | `str` | `"stock"` | `"stock"` or `"patched"` |
| `executable` | `str \| None` | `None` | Explicit Chrome binary path |
| `user_data_dir` | `str \| None` | `None` | Profile directory (temp if None) |
| `args` | `list[str] \| None` | `None` | Extra Chrome CLI flags |
| `timezone` | `str \| None` | `None` | IANA timezone override (wins over GeoIP) |
| `languages` | `list[str] \| None` | `None` | `navigator.languages` override (wins over GeoIP) |
| `viewport` | `tuple[int, int] \| None` | `None` | Window size as `(width, height)` |
| `mouse_profile` | `str` | `"normal"` | `"careful"`, `"normal"` or `"hasty"` |

#### Manual overrides

`timezone` and `languages` always take precedence over the GeoIP result and
over the seeded stealth profile, and they work with `stealth=False` too:

```python
browser = await Browser.launch(
    proxy="socks5://de-exit:1080",
    stealth=True,
    timezone="Europe/Rome",           # instead of the proxy's Berlin timezone
    languages=["it-IT", "it", "en"],  # -> Accept-Language: it-IT,it;q=0.9,en;q=0.8
)
```

Languages are passed to Chrome as `--accept-lang`, so the browser derives both
`navigator.languages` and the `Accept-Language` header natively — no CDP
override, no fingerprint mismatch.

`viewport` is applied as `--window-size` at launch (plus `Browser.setWindowBounds`
for a headed window). `Emulation.setDeviceMetricsOverride` is deliberately not
used: it desynchronises `window.outerWidth` / `screen` from the emulated
viewport, which is itself a detection signal.

`mouse_profile` selects the Wind Mouse personality used by every `human=True`
mouse movement: `"careful"` (slow, precise), `"normal"` (default), `"hasty"`
(fast, overshooting).

#### Context manager

```python
browser = await Browser.launch(headless=True)
async with browser:
    # browser is automatically closed on exit
    tab = await browser.new_tab("https://example.com")
```

#### `browser.new_tab(url="about:blank") -> Tab`

Opens a new tab and navigates to the URL.

```python
tab = await browser.new_tab("https://example.com")
```

#### `browser.get(url, **kwargs) -> Tab`

Navigate the main tab to URL. Shortcut for `browser.main_tab` + `tab.get(url)`.

```python
tab = await browser.get("https://example.com")
```

#### `browser.tabs -> list[Tab]`

All open tabs, popups included. Every new page — `new_tab()`, context tabs,
`target=_blank` links and `window.open` popups — is held frozen until its
stealth patches and overrides are in place, so none of its scripts runs
unpatched. Tabs closed by the page drop out of the list.

#### `browser.wait_for_tab(url, timeout=30) -> Tab`

Return the first open tab whose URL matches (glob with `*`/`?`, substring
otherwise), waiting for it to appear. Use it to pick up popups:

```python
await (await tab.select("a[target=_blank]")).click(human=True)
popup = await browser.wait_for_tab("*/checkout*")
```

#### `browser.main_tab -> Tab`

The first (primary) tab.

#### `browser.new_context(proxy=None) -> BrowserContext`

Create an isolated browser context (like incognito). Separate cookies and storage.

```python
ctx = await browser.new_context()
tab = await ctx.new_tab("https://example.com")
# This tab has its own cookie jar
```

#### Cookie management

```python
# Get all cookies
cookies = await browser.get_cookies()
cookies = await browser.get_cookies(domain=".example.com")

# Set cookies
from tellurium import Cookie
await browser.set_cookies([
    Cookie(name="session", value="abc123", domain=".example.com", secure=True)
])

# Save and load
await browser.save_cookies("cookies.json")
await browser.save_cookies("cookies.txt", format="netscape")
await browser.load_cookies("cookies.json")

# Clear
await browser.clear_cookies()
await browser.clear_cookies(domain=".example.com")
```

#### `browser.close()`

Close the browser, all tabs, and the Chrome process.

---

### Tab

Controls a single browser tab.

#### Navigation

```python
# Navigate to URL (waits for page load)
await tab.get("https://example.com")
# wait_until: "commit" | "domcontentloaded" | "load" (default) | "networkidle"
await tab.get("https://example.com", wait_until="domcontentloaded")
await tab.get("https://example.com", wait_until="networkidle")  # 500 ms without requests

# History
await tab.back()
await tab.forward()
await tab.reload()

# Current state
print(tab.url)    # final URL (after redirects), kept up to date
print(tab.title)  # document.title as of the last tab.get()

# Close
await tab.close()

# Wait for navigation
await tab.wait_for_navigation()
await tab.wait_for_navigation(url="*/dashboard*")
await tab.wait_for_url("*/success*", timeout=10)
```

#### Selecting elements

```python
# CSS selector (waits up to 10s for element to appear)
el = await tab.select("#login-button")
el = await tab.select("div.card:first-child", timeout=5)

# All matching elements (returns immediately, may be empty)
items = await tab.select_all("ul.results > li")
items = await tab.select_all("ul.results > li", timeout=10)  # wait for >= 1 match

# Find by visible text
el = await tab.find("Sign In")
el = await tab.find("Sign In", exact=True)  # Exact match
all_links = await tab.find_all("Read more")
all_links = await tab.find_all("Read more", timeout=10)  # wait for >= 1 match

# XPath
el = await tab.xpath("//div[@class='price']")
prices = await tab.xpath_all("//div[@class='price']")
prices = await tab.xpath_all("//div[@class='price']", timeout=10)

# Wait for element state: "visible" (default), "hidden", "attached", "detached"
el = await tab.wait_for("#dynamic-content", timeout=30)
el = await tab.wait_for("#modal", state="attached")
await tab.wait_for("#spinner", state="hidden", timeout=15)   # returns None
await tab.wait_for("#toast", state="detached")               # returns None
```

`select_all`, `find_all` and `xpath_all` default to `timeout=0` (no waiting) and
return an empty list instead of raising; `select`, `find` and `wait_for` raise
`TimeoutError`.

#### JavaScript

```python
# Evaluate expression, get result
title = await tab.eval("document.title")
count = await tab.eval("document.querySelectorAll('li').length")
data = await tab.eval("JSON.parse(document.body.dataset.config)")

# Evaluate on a specific element
text = await tab.eval_on("h1", "el => el.textContent")

# Inject script (runs on every page load)
await tab.add_script("window.__injected = true;")
```

#### Input

```python
# Mouse
await tab.mouse_move(100, 200)
await tab.mouse_move(100, 200, human=True)  # Wind Mouse trajectory
await tab.mouse_click(100, 200)
await tab.mouse_click(100, 200, human=True) # Human trajectory + click

# Keyboard
await tab.keyboard_press("Enter")
await tab.keyboard_press("Tab")
await tab.keyboard_type("Hello world")
await tab.keyboard_type("Hello world", human=True)  # Realistic timing
await tab.keyboard_type("Hello world", human=True, typos=True)  # + typo/backspace

# Scroll
await tab.scroll(delta_y=500)                  # Instant scroll
await tab.scroll(delta_y=500, human=True)      # Natural scroll with inertia
```

The Wind Mouse personality used by `human=True` comes from
`Browser.launch(mouse_profile=...)`.

#### Screenshots and PDF

```python
# Get PNG bytes
data = await tab.screenshot()

# Save to file
await tab.screenshot(path="page.png")
await tab.screenshot(path="full.png", full_page=True)

# Lossy formats accept a quality (ignored for PNG)
await tab.screenshot(path="page.jpg", format="jpeg", quality=70)

# PDF (headless only — Page.printToPDF is not implemented in headed Chrome)
pdf_bytes = await tab.pdf()
await tab.pdf("page.pdf", landscape=True, paperWidth=8.5, printBackground=False)

# Get full HTML
html = await tab.content()
```

Extra keyword arguments to `tab.pdf()` are forwarded verbatim as
[`Page.printToPDF`](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-printToPDF)
parameters; `printBackground=True` is the default.

#### Window

```python
await tab.set_viewport(1280, 720)   # Browser.setWindowBounds — no CDP emulation
await tab.maximize()
await tab.minimize()
await tab.bring_to_front()          # Page.bringToFront
```

`set_viewport` resizes the real window, so `innerWidth`, `outerWidth` and
`screenX` stay consistent. If `Browser.setWindowBounds` is unavailable it falls
back to `Emulation.setDeviceMetricsOverride` and logs a warning — that command
is a detectable signal, so prefer `Browser.launch(viewport=(w, h))`.

#### Network capture

```python
# Start capturing
await tab.capture()
await tab.capture(log=True)                    # Print requests to stderr
await tab.capture(log=True, log_filter="json") # Only JSON responses

# Search captured requests
reqs = await tab.requests(url="*/api/*")
reqs = await tab.requests(method="POST", content_type="json")
reqs = await tab.requests(status=range(400, 500))
reqs = await tab.requests(header="Authorization")
reqs = await tab.requests(body_contains="token")

# Wait for a specific request
req = await tab.wait_for_request("*/api/data*", timeout=10)
body = await req.body()
data = await req.json()

# Recording mode (export to file)
recorder = await tab.record(url_pattern="*/api/*")
# ... interact with the page ...
session = recorder.export()
session.save("api_session.json")
await recorder.stop()

# Stop capturing
await tab.capture_stop()
```

#### Waiting

```python
await tab.wait(2)            # Pause 2 seconds
await tab.wait_for_url("*/success*", timeout=10)   # glob pattern
await tab.wait_for_url("/success")                 # substring (no * or ?)
await tab.wait_for_navigation(url="*/dashboard*")
```

`wait_for_url` and `wait_for_navigation` treat a pattern containing `*` or `?`
as a glob (`fnmatch`, matched against the whole URL) and anything else as a
substring.

#### Raw CDP

```python
# Send any CDP command directly
result = await tab.send_cdp("Page.getNavigationHistory", {})
```

---

### Element

Represents a DOM element. Obtained from `tab.select()`, `tab.find()`, etc.

#### Properties

```python
text = await el.text()             # Own text: direct child text nodes, trimmed
text = await el.own_text()         # Alias of text()
text = await el.text_all()         # Full textContent of the subtree
tag = await el.tag()               # Tag name (lowercase): "div", "a", "input"
html = await el.html()             # Outer HTML
href = await el.attr("href")       # Single attribute
attrs = await el.attributes()      # All attributes as dict
box = await el.bounding_box()      # {x, y, width, height}

visible = await el.is_visible()
enabled = await el.is_enabled()
checked = await el.is_checked()
```

`text()` returns only the element's *own* text, `text_all()` the whole subtree.
For `<p>Price <b>9.99</b></p>` that is `"Price"` vs `"Price 9.99"`; for a leaf
element such as `<h1>Hello</h1>` both return `"Hello"`.

#### Tree navigation

```python
kids = await el.children()         # Direct element children
parent = await el.parent()         # Parent element, or None for the root
```

#### Interaction

```python
# Click
await el.click()                   # JS click (fast, reliable)
await el.click(human=True)         # Wind Mouse trajectory + CDP click

# Type
await el.type("hello@test.com")
await el.type("hello@test.com", human=True)   # Realistic keystroke timing
await el.type("new text", clear=True)          # Clear field first
await el.type("hello world", human=True, wpm=70, typos=True)  # Opt-in typos

# Other interactions
await el.hover()
await el.focus()
await el.scroll_into_view()
await el.scroll_into_view(human=True)          # Natural scroll
await el.upload("/path/to/file.pdf")
await el.select_option("admin")               # For <select> elements
await el.drag_to(target_element, steps=10)
```

#### Relative selection

```python
# Find elements relative to this one
child = await el.select(".child-class")
items = await el.select_all("li")

# By visible text, scoped to this element's descendants
link = await el.find("Buy now")                # raises LookupError if missing
links = await el.find_all("Buy now", exact=True)

# XPath with this element as the context node
price = await el.xpath(".//span[@class='price']")   # None if no match
prices = await el.xpath_all(".//span[@class='price']")
```

#### Custom JS

```python
# Run arbitrary JS with element as argument
color = await el.apply("el => getComputedStyle(el).color")
```

#### Screenshot

```python
await el.screenshot(path="element.png")
```

---

### Cookie

Dataclass for browser cookies with JSON and Netscape format support.

```python
from tellurium import Cookie

# Create
cookie = Cookie(
    name="session",
    value="abc123",
    domain=".example.com",
    path="/",
    expires=1742860800,      # Unix timestamp, -1 for session cookie
    http_only=True,
    secure=True,
    same_site="Lax",         # "Strict", "Lax", or "None"
)

# Serialize
data = cookie.to_json()            # dict
line = cookie.to_netscape()        # tab-separated string

# Deserialize
cookie = Cookie.from_json(data)
cookie = Cookie.from_netscape(line)

# Batch save/load
Cookie.save_list(cookies, "cookies.json")
Cookie.save_list(cookies, "cookies.txt", format="netscape")
loaded = Cookie.load_list("cookies.json")              # auto-detect format
loaded = Cookie.load_list("cookies.txt", format="netscape")
```

---

## Usage Scenarios

### Scenario 1: Scraping a protected site with login

```python
import asyncio
from tellurium import Browser

async def scrape_dashboard():
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        tab = await browser.new_tab("https://app.example.com/login")

        # Login with human-like interaction
        email = await tab.select("input[name=email]")
        await email.type("user@example.com", human=True)

        password = await tab.select("input[name=password]")
        await password.type("mypassword", human=True)

        await (await tab.find("Log In")).click(human=True)
        await tab.wait_for_url("*/dashboard*", timeout=15)

        # Save session for reuse
        await browser.save_cookies("session.json")

        # Scrape data
        cards = await tab.select_all(".data-card")
        for card in cards:
            title = await (await card.select("h3")).text()
            value = await (await card.select(".value")).text()
            print(f"{title}: {value}")

asyncio.run(scrape_dashboard())
```

### Scenario 2: Resuming a session with saved cookies

```python
async def resume_session():
    browser = await Browser.launch(headless=True, stealth=True, seed=42069)
    async with browser:
        # Restore previous session
        await browser.load_cookies("session.json")

        tab = await browser.new_tab("https://app.example.com/dashboard")
        # Already logged in via cookies
        data = await tab.eval("document.querySelector('.user-name').textContent")
        print(f"Logged in as: {data}")

asyncio.run(resume_session())
```

### Scenario 3: Intercepting API responses

```python
async def capture_api():
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        tab = await browser.new_tab("https://social.example.com")
        await tab.capture(log=True, log_filter="json")

        # Scroll to trigger infinite loading
        for i in range(5):
            await tab.scroll(delta_y=800, human=True)
            await tab.wait(2)

        # Extract all API responses
        feed_requests = await tab.requests(url="*/api/feed*", content_type="json")
        all_posts = []
        for req in feed_requests:
            data = await req.json()
            all_posts.extend(data.get("posts", []))

        print(f"Captured {len(all_posts)} posts from {len(feed_requests)} API calls")

asyncio.run(capture_api())
```

### Scenario 4: Scraping with proxy rotation

```python
async def scrape_with_proxies():
    proxies = [
        "socks5://user:pass@de-proxy.example.com:1080",
        "socks5://user:pass@fr-proxy.example.com:1080",
        "socks5://user:pass@us-proxy.example.com:1080",
    ]

    for i, proxy in enumerate(proxies):
        browser = await Browser.launch(
            headless=True,
            stealth=True,
            seed=10000 + i,    # Different fingerprint per proxy
            proxy=proxy,       # GeoIP auto-detects timezone/locale
        )
        async with browser:
            tab = await browser.new_tab("https://target.example.com")
            data = await tab.eval("document.body.innerText")
            print(f"Proxy {i}: {len(data)} chars")

asyncio.run(scrape_with_proxies())
```

### Scenario 5: Solving Cloudflare with human simulation

```python
async def bypass_cloudflare():
    browser = await Browser.launch(
        headless=False,    # Headed mode for Turnstile
        stealth=True,
        seed=42069,
    )
    async with browser:
        tab = await browser.new_tab("https://protected.example.com")

        # Wait for Cloudflare challenge
        await tab.wait(3)

        # If Turnstile checkbox appears, click it with human simulation
        try:
            iframe = await tab.select("iframe[src*='challenges.cloudflare']", timeout=5)
            box = await iframe.bounding_box()
            # Click inside the iframe (Turnstile checkbox is near top-left)
            await tab.mouse_click(
                box["x"] + 30,
                box["y"] + 25,
                human=True,
            )
            await tab.wait(5)
        except TimeoutError:
            pass  # No challenge appeared

        # Now on the real page
        content = await tab.eval("document.title")
        print(f"Page title: {content}")

asyncio.run(bypass_cloudflare())
```

### Scenario 6: Recording a session for replay

```python
async def record_session():
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        tab = await browser.new_tab("https://api.example.com")
        recorder = await tab.record(url_pattern="*/api/*")

        # Interact with the site
        await (await tab.find("Load Data")).click()
        await tab.wait(2)
        await tab.scroll(delta_y=500)
        await tab.wait(2)

        # Export the recorded session
        session = await recorder.export()
        session.save("api_recording.json")
        print(f"Recorded {len(session.requests)} API calls")
        await recorder.stop()

asyncio.run(record_session())
```

### Scenario 7: Multi-account with isolated contexts

```python
async def multi_account():
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        # Account 1 in default context
        tab1 = await browser.new_tab("https://app.example.com/login")
        await (await tab1.select("#email")).type("user1@test.com")
        await (await tab1.select("#password")).type("pass1")
        await (await tab1.find("Login")).click()

        # Account 2 in isolated context (separate cookies)
        ctx = await browser.new_context()
        tab2 = await ctx.new_tab("https://app.example.com/login")
        await (await tab2.select("#email")).type("user2@test.com")
        await (await tab2.select("#password")).type("pass2")
        await (await tab2.find("Login")).click()

        # Both are logged in as different users simultaneously
        name1 = await tab1.eval("document.querySelector('.username').textContent")
        name2 = await tab2.eval("document.querySelector('.username').textContent")
        print(f"Tab 1: {name1}, Tab 2: {name2}")

asyncio.run(multi_account())
```

### Scenario 8: Taking screenshots of search results

```python
async def screenshot_results():
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab("https://search.example.com")

        search = await tab.select("input[type=search]")
        await search.type("tellurium python", human=True)
        await tab.keyboard_press("Enter")
        await tab.wait_for("#results", timeout=10)

        # Screenshot individual results
        results = await tab.select_all(".result-card")
        for i, result in enumerate(results[:3]):
            await result.scroll_into_view()
            await result.screenshot(path=f"result_{i}.png")

        # Full page screenshot
        await tab.screenshot(path="full_results.png", full_page=True)

asyncio.run(screenshot_results())
```

### Scenario 9: Waiting for dynamic content with XPath

```python
async def dynamic_spa():
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        tab = await browser.new_tab("https://spa.example.com")

        # Wait for React/Vue to render
        await tab.wait_for("[data-loaded=true]", timeout=15)

        # XPath for complex selections
        price = await tab.xpath("//span[contains(@class,'price')]/text()")
        if price:
            print(f"Price: {await price.text()}")

        # Wait for specific content to appear
        el = await tab.wait_for(".notification-badge", timeout=30)
        count = await el.text()
        print(f"Notifications: {count}")

asyncio.run(dynamic_spa())
```

### Scenario 10: Raw CDP for advanced use cases

```python
async def advanced_cdp():
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab("https://example.com")

        # Enable performance metrics
        await tab.send_cdp("Performance.enable", {})
        metrics = await tab.send_cdp("Performance.getMetrics", {})
        for m in metrics["metrics"]:
            if m["name"] in ("JSHeapUsedSize", "Documents", "Nodes"):
                print(f"{m['name']}: {m['value']}")

        # Emulate mobile device
        await tab.send_cdp("Emulation.setDeviceMetricsOverride", {
            "width": 375, "height": 812,
            "deviceScaleFactor": 3, "mobile": True,
        })
        await tab.get("https://example.com")
        await tab.screenshot(path="mobile.png")

asyncio.run(advanced_cdp())
```

---

## Proxy and GeoIP

Tellurium supports HTTP, HTTPS, and SOCKS5 proxies with optional authentication.

```python
# HTTP proxy
browser = await Browser.launch(proxy="http://proxy.example.com:8080")

# SOCKS5 with auth
browser = await Browser.launch(proxy="socks5://user:pass@proxy.example.com:1080")

# Proxy + stealth (automatic GeoIP)
browser = await Browser.launch(
    stealth=True,
    proxy="socks5://user:pass@de-proxy.example.com:1080",
)
```

### Authenticated proxies

Chrome does not natively support proxies with credentials. When you provide a proxy URL with `user:pass@`, Tellurium automatically starts a local **ProxyForwarder** on `localhost` that handles authentication transparently:

```
Chrome -> localhost:<random_port> (ProxyForwarder) -> user:pass@upstream_proxy
```

This avoids using `Fetch.enable` via CDP (which would add a detectable surface).

### GeoIP exit IP resolution

When `stealth=True` and a proxy is configured, Tellurium determines the correct timezone, locale, and language by:

1. **Making an HTTP request through the proxy** to an IP-echo service (`api.ipify.org`, `checkip.amazonaws.com`, etc.) to discover the **real exit IP** — not the proxy hostname
2. **Resolving the exit IP** via a local country database (`GeoLite2-Country` or DB-IP Country Lite, searched in `$TELLURIUM_GEOIP_DB` then `~/.tellurium/geolite2/`) to get the country code
3. **Mapping the country** to timezone and languages (42 countries covered)
4. **Applying the result** to the stealth profile: `Emulation.setTimezoneOverride`, `Emulation.setLocaleOverride`, `--accept-lang` (which drives both the `Accept-Language` header and `navigator.languages`), keyboard layout

This ensures that a German proxy produces German timezone/locale regardless of where the proxy server's hostname resolves to.

```
Browser.launch(stealth=True, proxy="socks5://user:pass@de:1080")
    |
    |-- ProxyForwarder starts on localhost:random_port
    |-- HTTP request through proxy -> api.ipify.org -> "203.0.113.42"
    |-- GeoLite2 lookup: 203.0.113.42 -> country="DE"
    |-- timezone="Europe/Berlin", locale="de-DE", languages=["de-DE", "en"]
    |-- CDP: Emulation.setTimezoneOverride("Europe/Berlin")
    |-- CDP: Emulation.setLocaleOverride("de-DE")
    |-- Chrome flag: --accept-lang=de-DE,en
    |-- Stealth script: keyboard_layout.js with LOCALE="de-DE"
```

**Fallback behavior:**
- If `tellurium[geoip]` is not installed: logs a warning, uses OS timezone/locale
- If the IP-echo services are unreachable: falls back to DNS resolution of the proxy hostname
- If no local database is installed: one online IP-to-country lookup (warning logged); run `tellurium download-geoip` for offline resolution
- Manual overrides win over auto-detection: `Browser.launch(timezone="Europe/Berlin", languages=["de-DE", "en"])` replaces the GeoIP/OS values (timezone via CDP, languages via `--accept-lang`). Point `TELLURIUM_GEOIP_DB` at a specific database to control which one is consulted

**SOCKS5 without auth (no forwarder):** `urllib` does not support SOCKS natively, so the exit IP cannot be determined via HTTP. Falls back to DNS resolution of the proxy hostname. For best results, use proxies with auth or HTTP proxies.

### Supported proxy formats

| Format | Example |
|--------|---------|
| HTTP | `http://proxy:8080` |
| HTTP with auth | `http://user:pass@proxy:8080` |
| HTTPS | `https://proxy:8080` |
| SOCKS5 | `socks5://proxy:1080` |
| SOCKS5 with auth | `socks5://user:pass@proxy:1080` |

---

## Stealth Mode

When `stealth=True`, Tellurium automatically:

- Communicates via pipe transport (`--remote-debugging-pipe`, no observable
  WebSocket port)
- Never calls `Runtime.enable` (prevents console-based detection)
- Delivers its stealth patches as a real MV3 Chrome extension when the binary
  accepts `--load-extension` (Chrome for Testing, plain Chromium) and via
  `Page.addScriptToEvaluateOnNewDocument` otherwise — Chrome branded >= 137
  silently ignores `--load-extension`, so CDP delivery is the path on a stock
  Google Chrome install
- Removes `navigator.webdriver` (`--remote-debugging-pipe` sets it to `true`
  natively, unlike `--remote-debugging-port`)
- Restores `window.chrome` (`runtime`, `loadTimes`, `csi`)
- Fakes `navigator.plugins` (5 PDF viewers, real `PluginArray` shape)
- Spoofs the keyboard layout to match the locale
- Prevents WebRTC IP leaks (only when a proxy is configured or `webrtc_ip=` is set)
- Fixes headless-mode signals when `headless=True` (outer dimensions,
  notification permission, connection, voices, media devices)
- Sets User-Agent, platform and Client Hints consistently through
  `Emulation.setUserAgentOverride`, `hardwareConcurrency` through
  `Emulation.setHardwareConcurrencyOverride`, and timezone/locale through
  `Emulation.setTimezoneOverride` / `Emulation.setLocaleOverride`
- Sets the `Accept-Language` header **and** `navigator.languages` natively via
  `--accept-lang`. Overriding `acceptLanguage` through CDP leaks the raw
  q-value string into `navigator.languages` and emits a malformed header, so
  Tellurium passes an empty `acceptLanguage` and lets Chrome derive both
- Freezes every cross-origin iframe and worker at creation
  (`Target.setAutoAttach` with `waitForDebuggerOnStart`), patches it, and only
  then resumes it — an anti-bot running inside an OOPIF never observes an
  unpatched value
- Keeps `screenX`/`screenY` plausible: Chrome already derives them from the
  window origin, so Tellurium only repairs the degenerate placement where the
  window sits at `(0, 0)` with no frame and `screenX === clientX`

Core scripts on the stock backend: `webdriver.js`, `chrome_runtime.js`,
`plugins.js`, `keyboard_layout.js`; plus `webrtc.js` (with a proxy),
`headless_*.js` (headless only) and `worker_navigator.js` (worker targets).
On the patched backend all of these are skipped — the binary does it in C++.

### What is deliberately *not* spoofed on stock Chrome

WebGL vendor/renderer (`webgl.js`), `Function.prototype.toString` masking
(`tostring_mask.js`) and the `Navigator.prototype` overrides
(`navigator_proto.js`) were **removed** in T7.5. Each one is a CreepJS
`stealth` signal *regardless of the value it returns*: a spoofed NVIDIA
renderer on an Intel machine is a cross-check failure, and a `toString` Proxy
is a classifier flag on its own. `deviceMemory` is passthrough for the same
reason. Real GPU and canvas entropy are only rotated by the patched binary.

`navigator.webdriver` is likewise **not** defined inside workers:
`WorkerNavigator` has no such property in real Chrome, so adding one would be a
new fingerprint rather than a fix. Only `hardwareConcurrency` is aligned with
the main world.

### Human behaviour

With `human=True` on individual actions:

- Mouse uses the Wind Mouse algorithm with a Sigma-Lognormal velocity profile
- Typing uses realistic keystroke dynamics (digraph effects, micro-pauses,
  dwell time, key rollover)
- Scrolling uses CDP wheel events with natural inertia
- An `ActionTimer` inserts an inter-action pause before every human click,
  type and scroll, drawn from a table of measured transition delays with a
  log-normal fallback for the pairs the table does not cover

`Browser.launch(stealth_idle=True)` additionally makes `Tab.wait()` emit
occasional low-amplitude mouse micro-movements instead of leaving the cursor
perfectly still for the whole wait.

### Measured detection scores

Stock Chrome, headed, `stealth=True`
(`examples/fingerprint_tests/comparative_results.json`):

| Check | Result |
|---|---|
| CreepJS `lies` | 0 |
| CreepJS `headless` | 0% |
| CreepJS `stealth` | 0% |
| CreepJS `like_headless` | 38% — environmental, see Known limitations |
| bot.sannysoft.com | 31 passed, **0 failed**, 0 warnings |
| browserscan.net | no bot detected |
| `navigator.webdriver` | `false` |
| Comparative suite | **8/8** — parity with the nodriver baseline |

Reproduce with `make parity` (needs network and a display); the same gate runs
weekly in `.github/workflows/nightly-creepjs.yml`.

### Deterministic fingerprints

The `seed` parameter generates a deterministic, coherent fingerprint:

```python
# Same seed = same fingerprint every time
b1 = await Browser.launch(stealth=True, seed=42069)
b2 = await Browser.launch(stealth=True, seed=42069)
# Both have identical: UA, screen size, WebGL renderer, hardware specs
```

Use `user_data_dir` with a fixed `seed` for persistent identity across sessions.

---

## CLI

```bash
tellurium info                                              # installation info
tellurium update-cdp [--chrome-version VERSION]             # regenerate CDP bindings
tellurium download-browser [--browser {stock,patched}] [--version VERSION]
tellurium download-geoip [--maxmind-license-key KEY]
tellurium stealth-test [--browser {stock,patched}] [--full] [--headed]
tellurium list-browsers
tellurium update-browser [--check] [--security-only]
tellurium prune-browsers [--keep N]
tellurium verify-browser [--reinstall]
tellurium mcp [--headed] [--allow-local-urls]              # MCP server on stdio (tellurium[mcp])
```

| Command | What it does |
|---|---|
| `update-cdp` | Regenerate the CDP bindings in `tellurium/cdp/domains/` from the upstream protocol. `--chrome-version` targets a specific Chrome release. |
| `download-browser` | `--browser stock` (default) fetches Chrome for Testing; `--browser patched` installs a `chromium-telluride` release. `--version` pins a Chromium version, otherwise the latest release is used. |
| `download-geoip` | Install a country MMDB into `~/.tellurium/geolite2/`. Without a key it fetches DB-IP Country Lite (CC BY 4.0, no account needed); `--maxmind-license-key` uses MaxMind GeoLite2-Country instead. |
| `stealth-test` | Offline stealth assertions (webdriver, `window.chrome`, plugins, `toString` shape). `--full` also visits sannysoft/browserscan (needs network), `--headed` runs with a visible window. |
| `info` | Tellurium version, Python version, detected Chrome, cache directory, installed patched versions, GeoIP database in use. |
| `list-browsers` | Installed patched Chromium versions in the cache, marking the one `current` points at. |
| `update-browser` | Check the `chromium-telluride` releases and install a newer one. `--check` only reports, `--security-only` installs security releases only. |
| `prune-browsers` | Delete old cached versions, keeping the `--keep N` most recent. The version behind `current` is never pruned. |
| `verify-browser` | Re-hash the installed binary and compare with `binary_sha256` in `MANIFEST.json`. `--reinstall` re-downloads when the check fails. |
| `mcp` | Serve tellurium's browser tools over MCP on stdio for an LLM agent. `--headed` shows the windows, `--allow-local-urls` lets the agent open `file:` and browser pages. Needs `pip install tellurium[mcp]`. |

---

## Development

```bash
make test        # unit + integration + stealth (integration/stealth use xvfb-run when no DISPLAY)
make test-unit   # fast, offline, no browser
make lint        # ruff check + ruff format --check (same gate as CI)
make fmt         # ruff check --fix + ruff format
make build       # uv build + twine check --strict into dist/
make parity      # CreepJS stock-runtime parity gate (NEEDS NETWORK, not part of CI)
make clean
```

Test layout:

| Path | Needs |
|---|---|
| `tests/unit/` | nothing — offline, no browser |
| `tests/integration/` | headless Chrome + local HTTP servers (~47 s) |
| `tests/stealth/` | a `DISPLAY` (offline otherwise, ~15 s) |
| `examples/fingerprint_tests/test_stock_runtime_parity.py` | network + display; the `make parity` gate, deliberately outside CI |

`tests/integration/test_patched_e2e.py` is skipped unless a `chromium-telluride`
binary is installed (in the cache or via `TELLURIUM_PATCHED_EXECUTABLE`).

CI lives in `.github/workflows/` (`ci.yml`, `release.yml`,
`nightly-creepjs.yml`); see `.github/workflows/README.md` for what each job
does. The publishing procedure for both tellurium and `chromium-telluride` is
in [`docs/RELEASE.md`](docs/RELEASE.md).

---

## Requirements

- Python 3.10+
- Chrome, Chromium, or Chrome for Testing (auto-downloaded if not found)
- Zero Python dependencies (stdlib only)

## License

MIT

## Session — Persistent login state

`Session` saves browser state (cookies, localStorage, fingerprint seed) and
application metadata (credentials, tokens) across runs. You wrap the login flow
in code; if the saved session is still valid, the login is skipped.

### Quick start

```python
from tellurium import Session

session = Session("mario")        # stored under ./sessions/mario/
session.add("username", "mario")  # no-op if already saved
session.add("password", "secret") # no-op if already saved

@session.validate
async def signed_in(tab):
    await tab.get("https://example.com/dashboard")
    return (await tab.select(".welcome", timeout=3)) is not None

@session.login
async def do_login(tab, metadata):
    await tab.get("https://example.com/login")
    await (await tab.select("#user")).type(metadata["username"])
    await (await tab.select("#pass")).type(metadata["password"])
    await (await tab.select("#submit")).click()

async with session.start(stealth=True, headless=False) as browser:
    tab = browser.main_tab
    await tab.get("https://example.com/dashboard")
    # ... scraping ...
    session.save()
```

### On-disk layout

```
sessions/mario/
├── session.json        # metadata, seed, timestamps
└── chrome/             # user_data_dir — cookies, storage, cache
```

**Add `sessions/` to `.gitignore`** — the file contains credentials in plaintext.
Tellurium sets `0600` permissions on POSIX; it does not encrypt the file.

### API reference

| Construct | Meaning |
|---|---|
| `Session(name, path=None, seed=None, validate_mode="all")` | Create/load a session. When the file exists, its values win; the constructor `seed` is ignored. |
| `session.add(key, value)` | Add to metadata only if the key is absent (idempotent across runs). |
| `session.set(key, value)` | Unconditional set/overwrite. |
| `session.get(key, default=None)` | Read. |
| `@session.validate` | Register an async `(tab) -> bool` validator. Multiple allowed. |
| `@session.login` | Register the async `(tab, metadata)` login callback. Only one. |
| `session.start(**kwargs)` | Async context manager. Launches the browser, runs validators, calls login on failure. Kwargs are forwarded to `Browser.launch()` (except `user_data_dir` and `seed`). |
| `session.save(full=False)` | Persist state. `full=True` also saves launch params used. |

### Validation modes

- `validate_mode="all"` (default): all validators must return truthy. Short-circuits on first falsy / raising validator.
- `validate_mode="any"`: at least one validator must return truthy. Raising validators are skipped.

### Errors

- `SessionInvalidError` — validation failed and no `@login` is registered.
- `SessionLoginFailedError` — login callback raised (original exception preserved as `__cause__`).
- `SessionCorruptError` — `session.json` is unparseable.

## Patched binary (chromium-telluride)

Tellurium can drive a hardened Chromium build from the separate
[`chromium-telluride`](https://github.com/miczza/chromium-telluride)
repository. The patched binary implements fingerprint spoofing natively
(canvas, audio, WebGL, client hints, navigator, timing) so tellurium skips
its JS-level stealth scripts and only passes `--fingerprint=<seed>` flags.

### Install

```bash
tellurium download-browser --browser patched            # latest release
tellurium download-browser --browser patched --version 146.0.7680.188
tellurium list-browsers                                  # what is installed
tellurium verify-browser [--reinstall]                   # SHA256 against MANIFEST.json
tellurium update-browser [--check] [--security-only]     # upgrade to the latest release
tellurium prune-browsers --keep 2                        # drop old versions (never `current`)
```

Releases are downloaded from GitHub Releases of `chromium-telluride`, checked
against `SHA256SUMS`, extracted to `~/.tellurium/chromium/<chromium-version>/`
and the `chrome` binary is verified against `MANIFEST.json` (`binary_sha256`).
The `current` symlink points at the default version. Override the cache
location with `TELLURIUM_CACHE_DIR`.

Manual install works too: extract the release tarball and move its
`chromium-telluride/` directory to `~/.tellurium/chromium/<version>/`
(the directory must contain `chrome`, `MANIFEST.json` and the runtime
resources shipped in the tarball).

### Launch

```python
import asyncio
from tellurium import Browser

async def main():
    # default version (`current`, with a silent daily update check)
    browser = await Browser.launch(browser="patched", seed=42069)
    # or pin a version (no update check) and optionally its binary hash
    browser = await Browser.launch(
        browser="patched",
        chromium_version="146.0.7680.188",
        chromium_sha256="08ddbd55...",   # optional
    )
    # or point at any build on disk (skips cache + integrity verification)
    browser = await Browser.launch(browser="patched", executable="/path/to/chrome")
    async with browser:
        tab = await browser.new_tab("https://example.com")

asyncio.run(main())
```

Notes:

- `--fingerprint=<seed>` is required by the fork, so tellurium always passes
  one: `seed=` (or the stealth profile seed) when given, otherwise a random
  seed per launch, readable from the engine after launch.
- `stealth=True` additionally builds a `StealthProfile` and passes
  `--fingerprint-platform=<os>`; `webrtc_ip=` maps to
  `--fingerprint-webrtc-ip=<ip>` with the resolved address (`"auto"` → the
  proxy's IP); `"disable"` passes no flag, leaving the fork's default (drop
  srflx/relay candidates, seeded mDNS hostnames).
- `auto_security_update=True` installs a security release automatically when
  the daily check finds one (ignored when `chromium_version` is pinned).
- If the release tarball ships without `chrome_sandbox`, launch with
  `args=["--no-sandbox"]` or enable unprivileged user namespaces.

## Known limitations

### `like_headless ~38%` on CreepJS

CreepJS reports `like_headless ~= 38%` even when the runtime posture is clean
(`headless = 0%`, `stealth = 0%`, `lies = 0`). This is an **environmental**
signal — display server, GPU profile, audio device presence, font set — not a
behavioural lie, and it is the only residual CreepJS bucket that is non-zero.
Real headed sessions (e.g. `DISPLAY=:0` with Xorg + a real GPU) score lower;
containers and virtual displays score higher. Documented as accepted state:
tellurium still matches the nodriver baseline 8/8 on the comparative suite.

### Patched binary (`chromium-telluride`)

- CreepJS reports `lies = 0` (`window.Fingerprint.lies.totalLies`; triage in
  `chromium-telluride/docs/superpowers/notes/2026-04-26-lie3-triage.md`).
  Residual non-lie signals (`like_headless`, canvas entropy cluster) are
  tracked in `chromium-telluride/docs/known-issues.md`.
- The v0.1 release tarball does **not** ship `chrome_sandbox` (the GN target is
  not in the build graph for the current `BUILD_ARGS.gn`; the manifest records
  this as `sandbox.chrome_sandbox_bundled = false` /
  `missing_optional_files: ["chrome_sandbox"]`). Launch with
  `args=["--no-sandbox"]`, or run on a kernel with unprivileged user
  namespaces enabled (`user.max_user_namespaces > 0`).
- Only `linux-x64` is built. `--fingerprint-timezone` and
  `--fingerprint-locale` are **not** implemented by any patch and are not
  passed; `supported_flags` in `MANIFEST.json` lists only `--fingerprint`,
  `--fingerprint-platform` and `--fingerprint-webrtc-ip`.

### Platform support

Linux x64 is the only tested platform. A Windows CDP pipe transport exists
(`tellurium/cdp/transport/_pipe_win.py`) but is **untested**, and there is no
Windows or macOS job in CI — a multi-OS matrix is planned, not shipped. The
patched binary is Linux-only.

### WebGPU

WebGPU exposes adapter and limit information that cannot be masked from
JavaScript without producing a detectable override, so on stock Chrome it is
left untouched and reports the real GPU. Only a patched binary can rotate it
coherently; that work is not in v0.1 of `chromium-telluride` either. Disable
WebGPU at launch (`args=["--disable-features=WebGPU"]`) if the exposure
matters more than the anomaly of a browser without it.

### Network-layer fingerprints (JA3/JA4/JA4T)

Tellurium operates above the TLS and TCP stacks. The ClientHello and the TCP
options Chrome emits are the host's and Chrome's own, which is the right
answer as long as the spoofed OS matches the real one. Forcing a different
`target_os` in the stealth profile creates a mismatch that JA4T / TCP
fingerprinting can see (a "Windows" UA arriving with Linux TCP window scaling
and options ordering). The proxy forwarder does not rewrite TLS.
