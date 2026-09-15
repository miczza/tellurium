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

Optional GeoIP support (auto-detect timezone/locale from proxy exit IP):

```bash
pip install tellurium[geoip]
```

The GeoIP module requires a MaxMind GeoLite2-Country database file at `~/.tellurium/geolite2/GeoLite2-Country.mmdb`. Download it from [MaxMind](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) (free account required).

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

All open tabs.

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
await tab.get("https://example.com", wait_until="domcontentloaded")

# History
await tab.back()
await tab.forward()
await tab.reload()

# Current state
print(tab.url)
print(tab.title)

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

# All matching elements
items = await tab.select_all("ul.results > li")

# Find by visible text
el = await tab.find("Sign In")
el = await tab.find("Sign In", exact=True)  # Exact match
all_links = await tab.find_all("Read more")

# XPath
el = await tab.xpath("//div[@class='price']")

# Wait for element
el = await tab.wait_for("#dynamic-content", timeout=30)
```

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

# Scroll
await tab.scroll(delta_y=500)                  # Instant scroll
await tab.scroll(delta_y=500, human=True)      # Natural scroll with inertia
```

#### Screenshots

```python
# Get PNG bytes
data = await tab.screenshot()

# Save to file
await tab.screenshot(path="page.png")
await tab.screenshot(path="full.png", full_page=True)

# Get full HTML
html = await tab.content()
```

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
await tab.wait_for_url("*/success*", timeout=10)
```

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
text = await el.text()             # Visible text content
tag = await el.tag()               # Tag name (lowercase): "div", "a", "input"
html = await el.html()             # Outer HTML
href = await el.attr("href")       # Single attribute
attrs = await el.attributes()      # All attributes as dict
box = await el.bounding_box()      # {x, y, width, height}

visible = await el.is_visible()
enabled = await el.is_enabled()
checked = await el.is_checked()
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
children = await el.select_all("li")
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
        session = recorder.export()
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
2. **Resolving the exit IP** via the GeoLite2-Country database to get the country code
3. **Mapping the country** to timezone and languages (42 countries covered)
4. **Applying the result** to the stealth profile: `Emulation.setTimezoneOverride`, `Emulation.setLocaleOverride`, `Accept-Language` header, keyboard layout

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
    |-- Extension: keyboard_layout.js with LOCALE="de-DE"
```

**Fallback behavior:**
- If `tellurium[geoip]` is not installed: logs a warning, uses OS timezone/locale
- If the IP-echo services are unreachable: falls back to DNS resolution of the proxy hostname
- If the GeoLite2 database is missing: raises `FileNotFoundError` with instructions
- Manual override always takes precedence: `Browser.launch(timezone="Europe/Berlin", languages=["de-DE"])`

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

- Communicates via pipe transport (no detectable WebSocket port)
- Never calls `Runtime.enable` (prevents console-based detection)
- Injects stealth patches via a real Chrome extension (no detectable `Page.addScriptToEvaluateOnNewDocument`)
- Removes `navigator.webdriver`
- Fakes `navigator.plugins` (5 PDF viewers)
- Spoofs WebGL vendor/renderer from a real GPU database
- Overrides `hardwareConcurrency` and `deviceMemory` on the navigator prototype (propagates to Workers)
- Masks overridden functions to appear native (`Function.prototype.toString`)
- Spoofs keyboard layout to match locale
- Prevents WebRTC IP leaks (when using a proxy)
- Fixes headless-mode signals (outer dimensions, notifications, connection, voices, media devices)
- Sets User-Agent and Client Hints consistently (Sec-CH-UA, platform, architecture)

With `human=True` on individual actions:

- Mouse uses Wind Mouse algorithm with Sigma-Lognormal velocity profile
- Typing uses realistic keystroke dynamics (digraph effects, micro-pauses, dwell time)
- Scrolling uses CDP wheel events with natural inertia

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
tellurium info                          # Show installation info
tellurium download-browser              # Download Chrome for Testing
tellurium download-browser --browser patched  # Download patched Chromium
tellurium update-cdp                    # Regenerate CDP bindings
tellurium stealth-test                  # Quick stealth verification
tellurium stealth-test --full           # Full stealth test suite
```

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
  `--fingerprint-webrtc-ip=<mode>`.
- `auto_security_update=True` installs a security release automatically when
  the daily check finds one (ignored when `chromium_version` is pinned).
- If the release tarball ships without `chrome_sandbox`, launch with
  `args=["--no-sandbox"]` or enable unprivileged user namespaces.

## Known limitations

### `like_headless ~38%` on CreepJS

CreepJS reports `like_headless ≈ 38%` when tellurium runs against a
headless container. This is an **environmental** signal — display server,
GPU profile, audio device presence — not a behavioral lie. Real headed
sessions (e.g. `DISPLAY=:0` with Xorg + GPU) typically score lower.

In v0.1 this is documented as accepted state. The runtime stealth posture
itself reports `headless=0%, lies=0` and matches nodriver 8/8 on CreepJS.

### Patched binary: CreepJS status

The patched binary reports `lies = 0` on CreepJS (`window.Fingerprint.lies.totalLies`,
triage in `chromium-telluride/docs/superpowers/notes/2026-04-26-lie3-triage.md`).
Residual non-lie signals (`like_headless`, canvas entropy cluster) are tracked in
`chromium-telluride/docs/known-issues.md`.
