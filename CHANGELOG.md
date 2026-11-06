# Changelog

All notable changes to tellurium are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `Tab.keyboard_press("Shift+<digit or symbol>")` types the US layout's shifted character
  (`Shift+1` -> `!`, `Shift+/` -> `?`), with `key`, `code` (`Digit1`) and
  `windowsVirtualKeyCode` (49) as a real Shift press gives them. Every key event now
  carries the DOM `code` of its physical key. Other layouts are not modelled.
- `tellurium.Multiplexer(size, *, proxies=(), warm=0, acquire_timeout=30, **launch)`: one
  CDP endpoint in front of a pool of Chromes, one Chrome per WebSocket connection
  (`async with`, `await mux.serve(host, port)` until cancelled, `mux.url`, `mux.token`,
  `mux.status()`, `mux.restart(slot_id)`). Each client gets a Chrome of its own, launched
  with a fresh seed and the next proxy and closed with its profile when it leaves; up to
  `size` clients at once, the others wait in a first come, first served queue up to
  `acquire_timeout` seconds, then HTTP 503. `warm` Chromes are kept ready. Client ids are
  remapped (repeated or scattered ids are fine), events and `sessionId` pass untouched, a
  message that is not a JSON object with an integer id closes with 1007. A health probe
  (`Browser.getVersion` on the same pipe every 10 s, also for warm Chromes) kills a Chrome
  that misses two in a row; a crash or a hang closes its client with 1011 and the reason,
  and the place gets a new Chrome. Failed launches are retried with backoff and reported
  in `status()`. `GET /json/version` (also `/json/version/`) answers like Chrome's; the
  WebSocket path is `/devtools/browser/<anything>`. Every request, upgrade included,
  needs `Authorization: Bearer <token>` (token in `~/.tellurium/multiplex-token`, 0600),
  a `Host` naming the bind address and no `Origin`; a token in the URL, path included,
  is refused. Cancelling `serve()` closes the clients (1001), the Chromes, forwarders and
  profiles. `proxy`, `seed`, `user_data_dir` and `stealth` raise `TypeError`.
  A client that hangs up while it waits leaves the queue at once (no Chrome launched for
  it); past 64 waiting clients a new one gets 503 at once. A connection must send its
  request within 10 s, and at most 64 connections may be waiting to do so (the oldest is
  dropped): silent sockets cannot use up the descriptors. Both directions of the relay
  are bounded in bytes by back-pressure: past 16 MiB waiting for a slow client the pipe
  is no longer read (Chrome keeps the rest) and health probes are not counted as missed
  meanwhile (a probe is missed only if nothing at all came from the pipe while it
  waited: a Chrome that keeps talking is alive); past 64 MiB of commands Chrome has not answered the client is no longer
  read. Only a client that takes nothing for 60 s is closed (1008). Every close toward a
  client (restart, lost Chrome, stall, shutdown with 1001) takes at most 5 s, then its
  socket is cut: a client that reads nothing cannot keep a place or the shutdown waiting.
- Extra `tellurium[multiplex]` (`websockets>=17`); without it `Multiplexer()` raises
  `ImportError` with the install line.
- Multiplexer administration, behind the same checks as CDP (Bearer, `Host`, no
  `Origin`, no token in the URL): `GET /admin/status` answers `status()` as JSON (proxies
  without credentials, never the token); `POST /admin/slots/<id>/restart` replaces that
  place's Chrome (its client gets 1012) and answers 202, 409 when the place has no Chrome
  (idle, launching or closing), 404 for no such place. Another
  method on these routes is 405 with `Allow`, as is any method but `GET` elsewhere;
  requests carry no body.
- `tellurium multiplex --pool N [--proxies FILE] [--warm K] [--listen HOST:PORT]
  [--acquire-timeout S] [--browser stock|patched] [--headed]`: serves a `Multiplexer`
  (default `127.0.0.1:9339`, `--browser patched`). It prints the URL and the token file,
  never the token nor a proxy's credentials. The proxies file holds one URL per line
  (blank lines and `#` comments skipped); a bad line (spaces or control characters, NUL
  included, count as bad) is named by its number, never shown. A token file that cannot
  be used and an address that cannot be taken get messages of their own; on a
  non-loopback `--listen` it warns that token and CDP travel in plain text, and on a
  wildcard address that the `Host` check is off.
  Without the patched Chrome it points to `tellurium download-browser --browser patched`
  or `--browser stock`; without the extra, to `pip install 'tellurium[multiplex]'`.
  SIGINT, SIGTERM and SIGHUP (the terminal or ssh going away) close every client (1001),
  Chrome, forwarder and profile, then it exits with 0; more signals while it closes do
  not cut the closing short nor change the exit status. Only the signals the platform has
  are used, and without `loop.add_signal_handler` (Windows) Ctrl-C closes the same way:
  importing the CLI no longer needs SIGHUP.
- Playwright (the Python package only, no browsers) in the `dev` extra: a test drives the
  multiplexer with `connect_over_cdp`, two clients at once getting two Chromes.

- `tellurium.browser.raw_chrome.RawChrome`: Chrome on its CDP pipe without `Browser`
  (`await RawChrome.launch(...)` or `async with`), for code that speaks CDP itself.
  `transport` (`send(bytes)` / `recv() -> dict`), `pid`, `seed`, `proxy`, `alive`,
  idempotent and time-bounded `close()`. The command line comes from the same plan as
  `Browser.launch` (engine arguments with the seed, `--accept-lang`, `--window-size`,
  credential forwarder, WebRTC UDP only through the proxy, time zone and languages of the
  proxy's exit IP with `geoip=True`), with no stealth engine, extension or User-Agent
  rewrite, and always a temporary profile. The time zone (`timezone=` or the exit IP's)
  reaches Chrome as `TZ` in its environment, so stock Chrome gets it too. `seed` is `None`
  with stock Chrome, which takes none; a Chrome silent on the pipe for `READY_TIMEOUT`
  (30 s) raises `asyncio.TimeoutError`. Launch waits for `Browser.getVersion` on the
  pipe; a failure or cancellation at any step releases Chrome, forwarder and profile.
- `Slots.slot(timeout=None)` (the browser slots of `SessionPool`): *timeout* limits only the
  wait for a slot; past it `TimeoutError`, with no slot taken and no place left in the queue.
  The block itself is not limited (an `asyncio.timeout` around `slot()` would cut it too).
- `tellurium.access`: who may talk to a local tellurium server, without a web framework —
  the token file (`load_or_create_token(path)`, `TokenFileError`; the file name is the
  caller's), the bind address (`parse_bind`, `is_loopback`, `allowed_hosts`) and the checks
  on lowercased headers (`host_ok`, `token_in_url`, `bearer_ok` in constant time,
  `repeated_header`). `tellurium.mcp.auth` uses it and still exports the same names.

- Patched engine: `--fingerprint-timezone=<IANA>` with the timezone of the stealth profile
  (GeoIP and the manual `timezone=` of `launch` included) or, with stealth off, the manual
  `timezone=`. IANA ids and ICU custom ids (`GMT+05:30`, `GMT-3`) pass, as with
  `Emulation.setTimezoneOverride`; anything else (empty, spaces, `=`, `GMT+24:00`) is not
  passed, with a warning that contexts outside the CDP override stay on the host timezone.
  Capability `native_timezone` only when the binary's MANIFEST lists
  `--fingerprint-timezone` in `supported_flags`; the flag is passed regardless. Stock Chrome
  gets no flag; the CDP override stays, for binaries that do not read the flag.
- `Browser.headless` (read-only): whether Chrome was launched headless, from the flags it
  got (`headless=True` or `--headless` in `args`), on every platform. `wait_for_human`
  uses it instead of reading the process's command line, which the Windows launcher does
  not keep (it fell back to the user agent, which `--user-agent` rewrites).
- `await Session.save_now(full=False)`: `save()` from async code; during a start the cookie
  jar written is the one Chrome has now (read within 5 s), with the cookies a failed restore
  left pending.
- `Session.start(..., manual_timeout=600.0)`: the seconds a person gets to sign in with
  `on_login_failure="manual"` (was the fixed `MANUAL_TIMEOUT`, still the default).
- `SessionPool.open(name, create=True)`: with `create=False` a missing identity raises
  `FileNotFoundError` before any wait, and nothing is created or saved.
- `tellurium mcp --respect-robots`: `navigate` and `tab-open` to a URL the site's
  robots.txt disallows fail with "Navigation failed: robots.txt of <origin> disallows
  <path>" instead of opening it (stdio and HTTP; the sessions launch with
  `respect_robots=True`).
- `Browser.launch(respect_robots=True, robots_agent="*")`: `Tab.get`, `Browser.get`,
  `Browser.new_tab(url)` and `BrowserContext.new_tab(url)` raise `RobotsDisallowedError` (a
  `NavigationError`, exported from `tellurium`; message `robots.txt of <origin> disallows
  <path>`) for a URL the site's robots.txt disallows, before any request; the blank tab
  `new_tab` made for it is closed. `await tab.is_allowed(url, timeout=30.0)` answers with or
  without the flag (`NavigationTimeoutError`, phase `"robots.txt"`, past *timeout*). robots.txt is parsed per RFC 9309 (groups by product token, longest match wins,
  `allow` wins a tie, `*` and `$`, percent-encoding normalised, first 500 KiB; parsed off
  the event loop and matched off it too, each rule run by run between its `*`, so even
  `Disallow: /` and 499 000 `*` answers in well under a millisecond) and loaded by
  Chrome with `Network.loadNetworkResource` from a hidden `about:blank` target of the tab's
  browser context (same proxy, IP and TLS as the navigation; no cookies), once per origin
  and context for 24 h (LRU of 256), one download at a time even for a hundred concurrent
  calls. 2xx: its rules; 4xx: everything allowed; 5xx, network error or no answer within
  10 s: everything disallowed, asked again after 60 s. Clicks, redirects and navigations
  started by the page are not checked; `Crawl-delay` is ignored. The URL is checked as
  Chrome reads it (`new URL(url).href` in the hidden target: `http:site/p`,
  `http://site\@other/p`, dot segments, tabs; `view-source:` as the page it shows), and
  one Chrome cannot parse is refused
  ("not a URL Chrome can parse"); a hidden target that cannot be opened fails with
  "robots.txt for <url> could not be checked". Without the flag no
  navigation requests robots.txt.
- `Element.is_trap_link()` and `tellurium.stealth.trap_link.reasons(element)`: whether a
  person could not see or click a link right now, or it wears a honeypot marker, and which
  signals fired (`not-rendered`, `visibility-hidden`, `transparent`, `zero-size`,
  `off-page`, `clipped`, `covered`, `empty`, `same-color`, `aria-hidden`, `inert`,
  `no-pointer`, `honeypot-marker`, `nofollow` next to another one); `transparent` is
  under 5% shown through `opacity` and `filter: opacity()` multiplied up the ancestors,
  or a fully transparent `mask-image`; `covered` hit-tests the link where it shows in the
  viewport (a box on top, `z-index: -1` under a block); `clipped` reads `overflow`,
  `contain: paint`, `clip`
  and basic-shape `clip-path`s (`inset()`, `circle(0)`, `ellipse()`, a `polygon()` of no
  area); `same-color` only where the background is known (not over a hero image, a
  gradient or an overlay); `off-page` follows every box that scrolls the link, so a link
  below the fold of an app scrolling in its own box, or a further slide of a carousel, is
  reachable. Below the fold, image links with `alt`, icons with `aria-label`, open menus
  and skip links brought back by their focus rules are not traps; a link of a closed menu
  is. The `:focus`, `:focus-visible` and `:focus-within` rules are read from the readable
  sheets (`@import`, `@media`, `@supports`, `@layer`, nesting), never applied (nothing
  fetched, no transition, no focus moved): their declared `left`/`top`, `clip`,
  `clip-path`, size, `font-size` or `opacity` must undo what hides the link, so
  `a:focus { transform: ... }` reveals nothing; a cross-origin sheet, an inline style that
  wins or `tabindex="-1"` leave it a trap. One `Runtime.callFunctionOn` in the
  isolated world of the link's frame (OOPIFs included), and one more for each `<iframe>` up
  to the tab, checked like the link (a 0x0, off-page or transparent frame makes its links
  traps): no main-world call, global, node
  or attribute; `trap_link.NoIsolatedWorldError` when the frame has no isolated world. The
  check is `tellurium/stealth/scripts/trap_link.js`, loaded like the other stealth scripts.
- `Session.start(..., on_login_failure="raise"|"manual")`. `"raise"` (default) keeps the
  errors as they were; `"manual"` hands the browser to a person when validation fails with
  no `@session.login`, or the login callback raises: a headless Chrome is closed (its cookie
  jar kept) and reopened with a window on the same profile, a `wait_for_human` banner asks
  to sign in, and on "Done" the validators run again (the banner comes back while they
  fail). The start then yields the headed browser; `SessionLoginFailedError` if nobody
  signs in within 600 s. All of it inside the same `start()` and its lock.
- `tellurium login NAME [URL] [--dir D]`: opens Chrome with a window on the named session
  (`~/.tellurium/sessions/NAME` by default, the folder `tellurium mcp` uses, launched with
  stealth as MCP does), on *URL* if given, with a `wait_for_human` banner. Once the person
  has signed in, clicking "Done", pressing Enter in the terminal or closing the window saves
  the session: `session.json` and the cookie jar in `cookies.json`, which MCP and scripts
  then find signed in. Chrome is kept running past its last window (`--keep-alive-for-test`)
  so the jar can still be read, and since Chrome drops the cookies with no expiry with its
  last window, the jar is read while a window is open and those are put back before the save
  (a cookie set in the last 0.3 s before the window closed can be missed). A session open
  elsewhere: an error naming the PID, exit code 1.
- `Tab.wait_for_human(reason, *, until=None, timeout=600)` hands the tab to a person (a
  captcha, a 2FA prompt). In headed Chrome a banner at the top of the page shows *reason*
  and a "Done" button; the wait ends when the person clicks it or *until* holds: a URL
  pattern (glob with `*`/`?`, substring otherwise) matched against the main frame's URL
  without query and fragment (a sign-in page's `?next=/dashboard` or `#/dashboard` does not
  match `**/dashboard*`), or an async `(tab) -> bool`. The banner is built from an isolated world
  in a closed shadow root, so the page cannot read it, styled through the CSSOM (a
  `style-src` CSP does not strip it), and put back after every navigation; every 0.3 s it is
  repaired if the page removed it or overrode its inline style (`display: none
  !important`), kept in the top layer, and raised again or moved into the page's modal
  `<dialog>` when its button is not what a click there would hit. "Done" arrives through a
  CDP binding that exists only in that isolated world and fires only for a person's input
  (a trusted click, or a submission of the banner's form during a transient user
  activation), so neither the page nor a synthetic `click()` can end the wait; the
  submission never leaves the shadow root, so capture listeners that stop every click do
  not block it, and on documents loaded during the wait the banner's own capture listener
  runs first. A page that cancels the clicks on the banner in the document already open,
  or hides it again faster than a round, can still block "Done"; one that makes it
  invisible and lays it over a button of its own gets the person's real click onto it, so
  "Done" says that a person clicked, not that the task is done (see the README, which also
  advises a validator after `tellurium login`). In
  headless Chrome (told apart if any witness says so: the `--headless` Chrome was started
  with, which a wrapper script adding the flag hides, or `HeadlessChrome` in its user agent,
  which `--user-agent` rewrites) there is no banner and *until* is required (`ValueError` otherwise). `TimeoutError` after *timeout* seconds (`None`: no
  limit); the banner is removed on every way out, cancellation included. A page too busy
  to answer within 5 s delays the next check (and the banner) instead of failing the wait,
  from its very first call on: the script that brings the banner to new documents is
  registered in the background, and its reply awaited until the wait ends.
  The banner's isolated world and its binding are kept only when both were set up in the
  document still showing, so a navigation to another renderer as the wait starts (Chrome's
  first page to the site) cannot leave a "Done" that reaches nobody.
- `SessionPool(directory, max_browsers=4, **launch)` (`~` in `directory` is expanded): named
  identities side by side, each a `Session` in its own folder with its own Chrome, profile,
  cookie jar and fingerprint seed. `async with pool.open(name) as browser` starts one (a
  missing name is created, its `session.json` written so the seed lasts); at most
  `max_browsers` are open at once: a slot is taken before Chrome starts and given back only
  after it is closed, on a failed launch, an error in the body and a cancellation too, and
  an open waiting for a slot can be cancelled. The same name opened twice in the pool, or a
  session another process holds, fails at once with `SessionBusyError` without waiting for
  a slot. `await pool.list()`, `create(name, seed=None)`, `get(name)` and `delete(name)`
  manage the identities; `delete` of a session open in the pool or in another process
  raises `SessionBusyError` and leaves the folder alone. Names are 1-64 letters, digits,
  `.`, `_`, `-` (starting with a letter or digit), so none leaves the pool directory.
- `SessionBusyError` (from `tellurium` and `tellurium.session`): `Session.start()` locks the
  session folder (`session.lock`, `fcntl.flock` on POSIX, `msvcrt.locking` on Windows,
  mode 0600, with the holder's PID inside) from before Chrome starts until after it is
  closed, error and cancellation included. A second process, or a second `Session` on the
  same folder, gets `SessionBusyError` with `.pid` and `.path` instead of a Chrome launch
  error; the OS drops the lock when its holder dies, so a `kill -9` leaves nothing to clean.
  Checking who holds a session (the MCP server does it before a launch) takes the lock only
  for an instant and shared, and a start that meets such a check retries for up to 0.5 s, so
  neither reports a session busy that is free.
  Before launching, `start()` also waits (up to 10 s) for the Chrome of a holder that died
  to let go of the profile (its `SingletonLock`), and names that Chrome's PID in a
  `SessionBusyError` if it stays. A Chrome counts as holding the profile only if its
  `--user-data-dir` is that very folder, symlinks resolved (`/x/chrome2` is not `/x/chrome`).
- `Session` carries its cookie jar across restarts: Chrome drops the cookies with no expiry
  (`expires == -1`: SSO, banks) when it restarts, and can lose one written an instant before
  it closes. Before Chrome closes (on error too, each call bounded by 5 s) the jar is read
  and its cookies not yet expired are written to `cookies.json` in the session folder
  (atomic, mode 0600); the next `start()` puts back, before the validators run, those Chrome
  does not have (same name, domain and path), leaving the ones it kept untouched; until
  Chrome has taken them (the restore timed out, the start was cancelled) the close keeps
  them in `cookies.json` next to Chrome's jar, so a failed restore never loses them. A file
  written as Chrome closed is newer than Chrome's own copy, which can miss the last change
  (a token rotated just before the close): its cookies then go back over the ones Chrome kept
  with another value. While a session runs the file is marked as not written at a close, so
  after a process that died before closing the next start trusts Chrome's copy. `save()`
  also writes `cookies.json` with the jar known as of the last start or close.
  To log a session out by hand, delete `cookies.json` along with the profile's cookies.
- `Cookie.partition_key`: the CHIPS partition (`partitionKey` of `Storage.getCookies`), kept
  by `to_json()`/`from_json()` and sent back by `set_cookies()`, so a partitioned cookie
  stays in its partition; a cookie with the same name, domain and path in another partition
  is another cookie for the session's `cookies.json`.
- MCP `session-open` on a named session another process holds (the CLI, a script, another
  server) is refused before any launch with the holder's PID, and the name is not left
  claimed; a `SessionBusyError` from a launch that lost the race says the same.
- `tellurium mcp --http HOST:PORT [--allow-eval] [--idle-timeout S] [--allow-remote]
  [--max-sessions-per-client N] [--max-sessions N]`: the MCP server over Streamable HTTP (the SDK's session manager under
  uvicorn, endpoint `/mcp`; port 0 picks a free one, the address is printed on stderr). Each
  MCP client (MCP session) gets its own browsers: it never sees another client's sessions or
  tabs. A client's sessions are closed and saved when it ends its MCP session cleanly, after
  `--idle-timeout` seconds without a tool call (default 300, 0 never; also what holds the
  browsers of a client that died without ending its session), and when the server stops. `eval` is off on HTTP unless `--allow-eval`. The default bind is loopback; any
  other address needs `--allow-remote` and prints a warning. Only handshake-era protocol
  versions are served (they carry the MCP session); a 2026-07-28 request gets the supported
  versions back and SDK clients fall back to `initialize`.
  At most `--max-sessions-per-client` browsers per client (default 4) and `--max-sessions`
  for the server (default 16); past them `session-open` says which cap was hit.
  `--idle-timeout` refuses `inf`, `nan` and negative values with a message (exit 2).
  The README documents it, with a Claude Code and a Python client example.
- `tellurium mcp --http`: request guard. The token lives in `~/.tellurium/mcp-token`
  (32 random bytes, base64url; created atomically with mode 0600; a file other users can
  read, a symlink, a non-regular file or a malformed token is refused, checked on the
  descriptor that is read; a home folder owned by another user or writable by others is
  refused too). Every request needs
  `Authorization: Bearer <token>`, loopback included, compared in constant time; a
  token in the URL is refused; any `Origin` is refused (MCP clients are not web pages, no
  CORS) and `Host` must
  name the bind address (loopback names on loopback), against DNS rebinding.
  A request repeating `Host`, `Origin`, `Authorization`, `Mcp-Session-Id` or
  `MCP-Protocol-Version` is refused (400): a `DELETE` naming two sessions cannot end another
  client's browsers.
  A request head must arrive whole within 5 s and its body within 10 s more (slowloris), a
  refused request closes its connection at once (`Connection: close`, body unread), and at
  most 100 requests that passed the token check are served at once (503 past that);
  connections without the token take no place.
- `tellurium mcp`: a named session is held by one MCP client at a time; another client
  opening the same name gets a clear error instead of a second Chrome on the profile.
- `tellurium mcp` `screenshot`: at most 5 MB of base64 per image. A PNG over the cap is
  captured again as JPEG (lower quality, then smaller scale) and the result says so; the
  structured result reports `format` and `scale`. Each capture and page-metrics call has its own
  timeout, and the JPEG attempts share a 25 s budget: each is cut when it ends, none starts
  with less than 2 s left (past it: an error suggesting `ref=`).
  Over HTTP, replies are plain JSON rather than SSE: SDK clients refuse an SSE event over
  1 MiB, which a screenshot easily is.
  Over HTTP every tool call ends within 240 s (the SDK client gives up after 300 s without
  data) and `download` accepts a `timeout` of at most 110 s, with an error saying so.
- `tellurium mcp [--headed] [--allow-local-urls]`: tellurium as an MCP server over stdio (extra
  `tellurium[mcp]`, official `mcp` SDK; without the extra the command prints the
  install line). Twenty kebab-case tools: `session-open/list/close`,
  `tab-open/list/close`, `navigate`, `snapshot`, `click`, `fill`, `press`,
  `select-option`, `check`, `hover`, `scroll`, `wait-for`, `get-text`,
  `screenshot` (image content; a full page is cut to 8000 px per side, said in
  the result), `download` (returns the saved path) and `eval`.
  The whole tool listing is about 6.6 KB of schema. Page tools take a required `targetId`; arguments are a whitelist checked
  against each tool's schema (an unknown argument is an error); actions return
  `{ok, url, title, navigated}` and use human-like input unless `human: false`
  (`select-option` presses arrow keys on the focused list). `press` sends the key
  codes Chrome acts on (Enter submits) and refuses an unknown key.
  A named session is a `Session` in `~/.tellurium/sessions/<name>` (same
  cookies, storage and seed next time); downloads go to `~/.tellurium/downloads/` (each name reserved
  atomically, so parallel downloads of `report.csv` keep both files);
  `TELLURIUM_HOME` moves both. `navigate`/`tab-open` refuse non-web URLs
  (`file:`, `chrome:`, `chrome-extension:`, `devtools:`, `view-source:`,
  `javascript:`, …; only http, https, `about:blank` and `data:` pass) unless the
  server runs with `--allow-local-urls`. Domain errors come back as `isError` results that
  tell the agent what to do next (stale ref: take a new snapshot; covered
  element: what is on top; page too large: use `selector=` or
  `interactive=true`; an element that cannot take focus, an invalid URL, a
  selector with no match, a session whose profile another process holds).
  Closing stdin, closing only the reading end of the server's stdout,
  SIGTERM or SIGINT closes every browser
  and saves every named session, those still launching included (a launch gets
  30 s, then is cancelled and rolled back); a `session-close` cut by its timeout
  keeps closing and the session leaves the pool only once closed.
- `Tab.snapshot()` reads cross-site iframes (OOPIFs) too: their content is
  stitched under their `iframe` line, read through the frame's own CDP session
  (the one stealth auto-attach holds, else one attached for it, which Chrome
  detaches with the frame or the tab). The `- iframe "<url>" [oopif]` line is
  left only for a frame that cannot be reached; a frame whose renderer does not
  answer within the time left of `snapshot_timeout` (a script stuck in a loop)
  shows as `- iframe "<url>" [oopif: not responding]` and the rest of the page
  still arrives within the limit. `max_nodes` bounds the cross-site iframes too:
  each frame is counted before its tree is read and gets what the page left;
  one over it shows as `- iframe "<url>" [oopif: too large, N nodes]` and the
  rest of the page still arrives (over the limit in the page's own renderer,
  `SnapshotTooLargeError` as before). Refs of OOPIF nodes resolve and
  act through that session and are bound to the frame's document (a ref whose
  frame went away, or loaded another document, even in a new renderer whose
  backend ids start again, raises `StaleElementError`; later snapshots hand out
  new refs); `Element` boxes are mapped up to the tab through the
  affine map of each `<iframe>` content quad (border, padding, CSS zoom and 2D
  transforms such as `scale()` or `rotate()` alike), and the hit check before a
  pointer press (`human=True` clicks, `hover`, `drag_to`) checks every document
  on the way at the point mapped back into it: the press reaches the target or
  raises `ElementNotHittableError`, never another element. A cross-site iframe
  drawn in perspective or edge-on takes no pointer action
  (`ElementNotHittableError`).
- CDP transport: `Session.session_id`, `Session.router`, `Session.closed` and
  `Session.auto_attaches` (whether `Target.setAutoAttach` is on);
  `SessionRouter.session_for_target(target_id)` and `wait_for_target()` (the
  router records the target of every attached session); `SessionRouter.attach()`
  takes `via=` (attach through a page session) and `timeout=` (a session Chrome
  opens after the deadline or a cancellation is detached), `detach()` takes
  `via=` and closes the session at once.
- The handle of an `Element` in a cross-site iframe is released on that
  iframe's session (dropped, `release()`, or with its group on navigation and
  `Tab.close()`), not on the tab's, where it stayed alive with its document.
- `Tab.snapshot()` / `Tab.snapshot_nodes()`: the accessibility snapshot of the
  tab (`interactive=`, `selector=`, `depth=`, `max_chars=`, plus `max_nodes=`
  and `snapshot_timeout=`). `Tab.ref("e3")` and `Tab.select("@e3")` turn a
  snapshot ref into a normal `Element` (human input included): the same node
  keeps its ref across snapshots of one document, a main-frame navigation
  makes every earlier ref raise `StaleElementError`, an unknown ref raises
  `LookupError` at once (a ref is never polled for), as does a malformed
  `"@…"` selector. A ref passed where CSS is expected (`select_all`,
  `wait_for`, `eval_on`, `snapshot(selector=)`, `Element.select`/`select_all`)
  raises `LookupError` pointing at `Tab.select()`/`Tab.ref()`.
- `Tab.expect_download(timeout=30)`: `async with tab.expect_download() as
  info: ...` then `download = await info.value`. It takes the downloads of the
  tab's main frame and of its same-process iframes (tracked from
  `Page.frameAttached`/`frameNavigated`/`frameDetached`, so an iframe whose src
  is a download or another site counts too; a removed iframe leaves the set;
  iframes nested in a cross-site iframe are not covered), never another tab's
  (`Downloads.expect_frames()`), and saves them in the folder of the tab's
  browser context.
- Exported from `tellurium`: `BrowserContext`, `Download`, `DownloadError`,
  `SnapshotNode`, `SnapshotTooLargeError`, `ElementNotHittableError`.

- `tellurium.browser.snapshot`: accessibility snapshot of a page for LLM
  agents. `take_snapshot()` renders a compact tree (`- button "Sign in"
  [ref=e3]`, `- textbox "Email" [ref=e5]: "ada@example.com"`, with
  `checked`/`disabled`/`expanded`/`level` states) with `interactive=`,
  `selector=`, `depth=` and `max_chars=` (always kept, cut with an explicit
  `[truncated: N more lines]` line); `take_snapshot_nodes()` returns the same
  as `SnapshotNode` trees. Page text, names and values are always quoted, with
  control and bidi characters escaped and a `[+N chars]` cap, so a page cannot
  forge lines or refs. Built on `Accessibility.getFullAXTree` (`queryAXTree`
  for `selector=`, at the cost of the subtree), without `Runtime.enable`, and
  `Accessibility.disable` afterwards; pruning runs off the event loop. Pages
  over `max_nodes=` DOM nodes (default 50000, counted by Chrome in the live
  documents only; `None` for no limit) raise `SnapshotTooLargeError` with the
  count, unless `selector=` names a small enough part (a slow subtree fails
  after 5 s with the same error). The whole snapshot is also bounded by
  `snapshot_timeout=` (default 5 s, for what the count cannot see, such as
  shadow DOM, or a renderer still busy): past it, `SnapshotTooLargeError` says
  which limit fired and to raise `snapshot_timeout=`. `selector="body"`/`"html"` give the whole
  page; a selector on an element outside the accessibility tree raises
  `LookupError`. Same-process iframes are stitched in, OOPIFs show as
  `- iframe "<url>" [oopif]`; the AX nesting walked is bounded across stitched
  iframes, so a hostile page cannot exhaust the recursion.
- `tellurium.browser.refs`: per-tab `RefMap` (`ref ↔ backendDOMNodeId`, stable
  within a document, stale after a main-frame navigation, numbers never reused)
  and `resolve_ref()` into a normal `Element`; a ref whose node was detached
  (SPA re-render, `document.open()`) raises `StaleElementError`, checked in the
  isolated world of the node's frame so page JS cannot fake `isConnected`.
- Generated CDP bindings for the `Accessibility` domain
  (`tellurium.cdp.domains.accessibility`).
- Downloads: `Browser.launch(downloads_dir=None)` and
  `Browser.new_context(downloads_dir=None)` accept every download into a
  folder per browser context (a temporary one, removed on `close()`, unless a
  folder is given; `BrowserContext.downloads_dir` tells which).
  `tellurium.browser.download` adds `Download` (`url`, `suggested_filename`,
  `state`, `path()`, `save_as()`, `cancel()`), `DownloadError` and
  `DownloadWaiter`, which waits for the next download of the frames it
  accepts. `Browser.close()` and `BrowserContext.close()` cancel unfinished
  downloads first (no partial `.crdownload` file is left in a kept folder) and
  fail their waits with `DownloadError`; so does Chrome exiting or crashing,
  at once instead of at the timeout. `Download.context_id` names the context
  a download comes from; a relative `downloads_dir` is made absolute; a
  waiter's filter that raises fails that waiter alone.

- `tellurium download-browser --browser patched --allow-unverified` installs a
  release without a matching `SHA256SUMS` (mirrors, local builds); the same
  flag on `update-browser` and `verify-browser --reinstall`, and
  `reinstall(..., allow_unverified=True)`.
- `BrowserContext.clear_cookies(domain=None)` deletes the context's cookies
  (or one domain's) without touching the default context.
- `Tab.eval_on(..., timeout=)`, `Tab.screenshot(..., timeout=)` and
  `Tab.pdf(..., timeout=)` bound their CDP commands per call (a tall full-page
  screenshot or a slow promise could only be extended through the session-wide
  30 s default). `screenshot` and `pdf` write the file off the event loop.
- `Browser.launch(dialogs="dismiss" | "accept" | "manual")` sets the dialog
  policy of every tab (initial, `new_tab`, popups, context tabs).
- `tellurium` exports `Dialog`, `LaunchError`, `NavigationError`,
  `NavigationTimeoutError`, `StaleElementError` and `TargetCrashedError`.
- `Browser.launch(chrome_log=path)` appends Chrome's stdout and stderr to a
  file. By default the output is discarded, keeping only its tail in memory.
- `Element.release()` frees an element's handle in the page; later calls on it
  raise `StaleElementError`.
- `Tab.on_dialog(handler)` and `tellurium.browser.dialog.Dialog` (`type`,
  `message`, `accept(text)`, `dismiss()`): every tab now answers JavaScript
  dialogs. A handler that has not decided within 10 s, or that raises, yields
  to the policy. Without a handler the tab policy applies (`"dismiss"` by default,
  `beforeunload` accepted so navigations are never cancelled); before, an
  `alert()` froze every later command on the tab.
- Patched-binary auto-install: `tellurium download-browser --browser patched
  [--version]`, `update-browser` (installs; `--security-only`), `verify-browser
  --reinstall` now wired. Releases are fetched from GitHub Releases of
  `chromium-telluride`, checked against `SHA256SUMS`, extracted safely and the
  `chrome` binary verified against `MANIFEST.json`.
- `Browser.launch(auto_security_update=True)` installs security releases found
  by the daily check (was `NotImplementedError`).
- `TELLURIUM_CACHE_DIR` environment override for the browser cache.
- `tellurium stealth-test`: fixed (`async with` on a coroutine), adds toString
  shape invariants, `--full` visits sannysoft/browserscan, `--headed`.
- OOPIF and worker stealth patching: `Target.setAutoAttach` with
  `waitForDebuggerOnStart=True`, wired on **every page session** (a
  browser-root-only auto-attach never fires for a page's OOPIFs or dedicated
  workers), `Page.enable` on OOPIF sessions so scripts run at document-start,
  and `Runtime.runIfWaitingForDebugger` only after the patches land — an
  anti-bot inside a cross-origin frame never sees an unpatched value.
- `tellurium/stealth/scripts/worker_navigator.js`: worker targets get
  `hardwareConcurrency` parity with the main world. `navigator.webdriver` is
  deliberately left undefined in workers — real Chrome's `WorkerNavigator` has
  no such property, so defining one would be a new fingerprint (closes the
  T7.6 F6 candidate by deciding against it).
- `Tab.window_offset()` and P0.4 screen parity: Chrome already derives
  `screenX`/`screenY` from the window origin, so tellurium only repairs the
  degenerate placement (window at `(0,0)` without a frame, where
  `screenX === clientX`). All mouse dispatch now goes through
  `Tab._dispatch_mouse()`; no-op on backends advertising `native_cdp_fix`.
- `Browser.launch(stealth_idle=True)`: `Tab.wait()` emits low-amplitude mouse
  micro-movements via `IdleSimulator` instead of a perfectly still cursor.
- `ActionTimer` wired into `human=True` click / type / scroll / navigate, with
  a log-normal fallback (median ~270 ms, capped at 2 s) for action pairs that
  `ACTION_TRANSITION_DELAYS` does not list.
- `tellurium download-geoip`: installs DB-IP Country Lite (CC BY 4.0, no
  account) or MaxMind GeoLite2-Country with `--maxmind-license-key` into
  `~/.tellurium/geolite2/`. `resolve_geoip()` also searches
  `$TELLURIUM_GEOIP_DB` and falls back to a one-shot online IP→country lookup
  when no database is installed (a bundled database is not licensable).
  `tellurium info` reports the database in use.
- `tests/integration/test_patched_e2e.py`: patched-backend end-to-end coverage
  (skipped unless a `chromium-telluride` binary is installed in the cache or
  via `TELLURIUM_PATCHED_EXECUTABLE`) — `--fingerprint` flag, random-seed
  default, per-seed canvas determinism, `stealth=True` on the native backend.
- CI/tooling: `ci.yml` activated (ruff lint non-blocking, unit matrix
  3.10–3.13, integration + stealth under xvfb with Chrome stable, build +
  `twine check`), `release.yml` (tag `v*` → build → PyPI trusted publishing →
  GitHub Release with the CHANGELOG section as body), `nightly-creepjs.yml`
  (weekly parity gate, results uploaded as an artifact), `[tool.ruff]` in
  `pyproject.toml`, and a `Makefile` (`test`, `lint`, `fmt`, `build`,
  `parity`, `clean`).
- `docs/RELEASE.md`: end-to-end publishing procedure for tellurium and for
  `chromium-telluride`.
- Popup tracking: every new page (`new_tab`, context tabs, `target=_blank`,
  `window.open`) is auto-attached frozen from the browser root, patched
  (stealth scripts, overrides) and only then resumed; popups appear in
  `browser.tabs`. `Browser.wait_for_tab(url)` waits for one.
- `Tab.close()` / `Tab.closed`; tabs closed by the page leave `browser.tabs`.
- `Tab.get(wait_until=...)` now honours `"commit"`, `"domcontentloaded"`,
  `"load"` and `"networkidle"` (via `Page.lifecycleEvent`, tied to the
  navigation's loader); unknown values raise `ValueError`.

### Changed

- `Tab.keyboard_press` of a character typed with Shift on the US layout, pressed alone
  (`"!"`, `"?"`, `"+"`), is now pressed as a keyboard does it: Shift held (`shiftKey`
  true, modifier bit 8) on its physical key (`Digit1`, keycode 49), the same events as
  `"Shift+1"`; it used to send keycode 0 and no Shift. `"Control++"` is therefore
  Control and Shift on `=`. Letters keep their modifiers (`"Control+A"` has no Shift).
- `Tab.eval_on`: only a value whose getter throws while Chrome serializes it (CDP
  `-32603` on returning the value) raises `RuntimeError`; any other `-32603` of
  `Runtime.callFunctionOn` now comes out as the `CDPError` Chrome gave. The function runs
  once, as before; its result is read back by value in a second call.

- `Browser.launch(proxy=<with credentials>)`: Chrome answers the forwarder's challenge
  through CDP `Fetch` on the browser session (`handleAuthRequests`, every URL), enabled
  before `launch` returns and covering every context, popup, worker and service worker.
  Each request is paused once and continued at once (about 0.14 ms a request); the
  forwarder's challenge gets its secret once per request (a second round is cancelled),
  any other challenge (a site's `401`, another proxy) Chrome's default answer.
  `tab.intercept()` keeps working. Always on with credentials in the proxy; without
  them there is no forwarder and no `Fetch`. Chrome's background traffic, which does
  not go through DevTools, gets `407`. New `tellurium.browser.proxy_auth.ProxyAuth`,
  owned by the launch's `BrowserProcess` and stopped by its `close()`.
- Multiplexer relay: it can keep browser sessions of its own on a Chrome's pipe
  (`tellurium.multiplexer.own_session.OwnSession`, opened with
  `Target.attachToBrowserTarget`, with the relay's ids like the health probes, kept from
  the client by `OwnSessions`). Their replies, their events and the
  `Target.attachedToTarget`/`detachedFromTarget` events naming them never reach the
  client; Chrome announces a new session before its id is known, so while one attaches
  what goes to the client is held, in order, for that round trip. A client command on
  such a session, or a `Target.detachFromTarget` of it by session or target id, is
  answered with Chrome's "Session with given id not found." error and never reaches
  Chrome. New `Relay.call()` and `CommandError`.
- `RawChrome` with credentials in the proxy: new `raw.needs_proxy_auth` and
  `await raw.answer_proxy_auth(session)`. RawChrome does not read the pipe, so whoever
  speaks CDP on it must call `answer_proxy_auth` with a browser session of its own
  (`send`/`on`/`off`, from `Target.attachToBrowserTarget`) before navigating; until then
  the forwarder answers `407` and nothing reaches the proxy. The answer is owned by the
  Chrome's process and stopped by `raw.close()`. No-op without credentials. Once per
  Chrome: a second call while the answer is on, or a call after `close()`, raises
  `RuntimeError` and changes nothing (another call may follow a failed one). The
  session's `send` returns the reply's `result`; its `on` handlers get the event's
  `params`. New `ProxyAuth.active`.
- `tellurium.Multiplexer` behind a proxy with credentials: each Chrome answers the
  forwarder's challenge through `Fetch` on a browser session of the relay's own, enabled
  before the place is handed to a client (warm places included). The client sees none
  of it (no `Fetch` event, no reply, no `Target` event of that session). A Chrome that
  cannot enable it counts as a failed launch; a crash, a restart or a shutdown stops it
  with the Chrome. Without credentials nothing changes.
- **Breaking:** `tellurium.stealth.geoip.exit_geo`, `resolve_exit_ip` and
  `resolve_geoip` take the credential forwarder itself (`forwarder=`, was
  `forwarder_port=`) and ask it with its secret (`ProxyForwarder.auth_header`); a port
  passed as before fails with `AttributeError`. The `Proxy-Authorization` value of a
  lookup is kept out of `repr`.

- **Breaking:** Python 3.10 is no longer supported; tellurium needs Python 3.11 or newer.
  The `multiplex` extra needs `websockets>=17`, the first release that hands a method
  other than `GET` to the server (`POST /admin/slots/<id>/restart`), and 17 needs 3.11.
- Internal: code written for Python 3.11+ (`TimeoutError` instead of `asyncio.TimeoutError`,
  `datetime.UTC`); `NavigationTimeoutError` subclasses `TimeoutError` directly. CI drops 3.10.

- `Browser.launch` composes Chrome's command line with `tellurium.browser.launch_plan.LaunchPlan`
  (engine, executable, extensions, proxy forwarder, profile, GeoIP, stealth profile, flags);
  signature, errors and flags passed to Chrome are unchanged. The plan can also take the
  proxy's time zone and languages (`geoip=True`) and keep WebRTC's UDP inside the proxy
  (`proxied_webrtc_only=True`) without the stealth engine.

- `browser.close()` first asks Chrome to close with the CDP command `Browser.close` and
  waits up to 5 s for it to exit, then sends SIGTERM and SIGKILL as before. The orderly exit
  writes the cookie store, so a cookie written right before `close()` is there at the next
  launch on the same `user_data_dir` even without `Session` (SIGTERM alone lost it about
  one time in four). `close()` can take up to 5 s longer when Chrome does not answer
  `Browser.close`; it is skipped when the pipe is already broken.
- The RFC 9309 parser and matcher of robots.txt moved from `tellurium.browser.robots`
  to `tellurium.browser.robots_rules` (no behaviour change; `parse`, `RobotsRules`,
  `ALLOW_ALL` and `DISALLOW_ALL` are still importable from `robots`). New public name
  `robots_rules.PRODUCT_TOKEN` (was `robots._AGENT`), the product-token pattern that
  `Robots` checks `robots_agent` against.
- The pruning of the AX tree into `SnapshotNode` trees (`build_nodes`) moved from
  `tellurium.browser.snapshot` to `tellurium.browser.snapshot_text`, next to the
  rendering (no behaviour change; `SnapshotNode`, `build_nodes` and `render` are still
  importable from `snapshot`). New public names in `snapshot_text`, used by `snapshot`:
  `Unread` (was `snapshot._Unread`, the URL of a cross-site iframe left out, with its
  `state`), `ax_role` and `ax_props` (were `snapshot._role` and `snapshot._props`, the
  role and properties of an AX node).
- `tellurium.browser.geometry.frame_chain(session)` is public (it was `_chain`): the
  `(session, parent session, frame id)` of each cross-site frame up to the tab; the
  trap-link check uses it instead of the private name.
- The style checks of the trap-link script (focus rules, CSS lengths) moved from
  `stealth/scripts/trap_link.js` to `stealth/scripts/trap_link_style.js`, spliced back
  into the same function when it is loaded (no behaviour change: still one
  `Runtime.callFunctionOn`).
- With `stealth=True` on the stock backend Chrome is launched with
  `--user-agent=<profile User-Agent>` (the profile aligned first with the binary's
  `--version`; no flag when that cannot be read, so flag and override never name two
  versions), so what the browser process loads
  itself, such as robots.txt, carries the same User-Agent as the pages instead of
  `HeadlessChrome/…`. A `--user-agent` in `args` with `stealth=True` raises `ValueError` at
  launch, before anything starts (it would reach robots.txt while the pages kept the
  profile's, or empty the patched backend's client hints); without stealth it is kept. The full version stays the
  profile's everywhere (`getHighEntropyValues` `uaFullVersion` in pages and workers,
  `Sec-CH-UA-Full-Version`), as `fullVersionList` and `Sec-CH-UA-Full-Version-List`, instead
  of the empty string Chrome leaves under `--user-agent`. The patched backend gets no such
  flag: it would empty its native client hints and undo its reduced User-Agent
  (`Chrome/146.0.0.0`).

- Internal: `Tab.screenshot` and its full-page helpers moved to `tellurium/browser/screenshot.py`,
  the `Browser` cookie methods to the `CookieJar` mixin in `tellurium/browser/cookie_jar.py`.
  No behaviour change; `Tab.screenshot` and `Browser.get_cookies` & co. are where they were.
- `Element.drag_to` moved into `tellurium/browser/drag.py`; the method delegates to it,
  behaviour unchanged.
- Internal moves, no change in behaviour: the window controls of `Tab` (`set_viewport`,
  `maximize`, `minimize`, `bring_to_front`) live in `tellurium/browser/window.py`, and
  `tellurium update-cdp` in `tellurium/cdp/update_command.py`.
- `Cookie.from_json()` leaves `same_site` at `None` when the data has no `sameSite` (Chrome
  reports none for a cookie set without it), and `to_json()` then omits it, instead of
  turning it into an explicit `Lax`. `Cookie(...)` still defaults to `Lax`.
- `Browser.downloads`: internal accessor of the browser's download tracker;
  `Tab.expect_download` and `BrowserContext` use it instead of reading `Browser._downloads`.
- `NavigationError` for an aborted navigation (`net::ERR_ABORTED`, as for a
  download) now points at `Tab.expect_download()`.
- `Tab.back()` / `Tab.forward()` bound their CDP calls (5 s each); the XPath
  search of `Tab.xpath()` / `Tab.xpath_all()` is shared, unchanged in behaviour.
- `launch_chrome` and `launch_chrome_posix` moved from
  `tellurium.browser.launcher` to `tellurium.browser.process` (with the Chrome
  process lifecycle); the old import path still works.
- `Session.send()` without `timeout` now waits at most
  `SessionRouter.default_timeout` (30 s) instead of forever; pass
  `timeout=math.inf` to wait indefinitely. The `asyncio.TimeoutError` names
  the CDP method. This also bounds every setup command of `Browser.launch()`.
- Single cache layout shared by engine, CLI and installer:
  `~/.tellurium/chromium/<chromium-version>/chrome` (+ `MANIFEST.json`,
  `current` symlink). CLI previously looked in `chromium-patched-<v>/`.
  The legacy binary name `tellurium-chromium` is still accepted.
- CLI reads `binary_sha256[<platform>]` from `MANIFEST.json` (was flat `sha256`,
  which never matched the fork's manifest).
- `PatchedEngine` always passes `--fingerprint=<seed>` (random seed if none
  given: the fork requires it) and no longer emits `--fingerprint-timezone` /
  `--fingerprint-locale`, which no chromium-telluride patch implements.
- Update-check and release URLs point at `github.com/miczza/chromium-telluride`.
- Repo housekeeping: architecture specs migrated into `docs/superpowers/specs/architecture/`,
  build noise untracked, the one-off `diagnose_*` fingerprint scripts archived
  out of `examples/fingerprint_tests/`.
- `Slots.total` (the cap of `SessionPool` and `Multiplexer` slots) is read-only: raising
  it would have woken nobody already queued.
- `timezone=` (`Browser.launch`, `RawChrome.launch`, the multiplexer's launch options)
  must be an IANA time zone known to Python's `zoneinfo`, else `ValueError` before
  anything starts; Chrome used to take any string and report `Etc/Unknown`. Not checked
  where Python has no time zone database.
- `RawChrome.close()` first sends `Browser.close` on the pipe and gives Chrome up to
  5 s (`CLOSE_GRACE`) to exit on its own, then SIGTERM and SIGKILL as before.
- `tellurium.mcp.auth` no longer re-exports `hmac` and `os` (kept only for old tests).

### Fixed

- `Download.cancel()` (and closing a context or the browser with a download running) no
  longer returns while the partial `<guid>.crdownload` file is still in the folder: Chrome
  reports the cancel before its file thread deletes it, so the call now waits for the file
  to go, and removes it itself if it is still there when the timeout ends.
- macOS: `Tab.keyboard_press("Control+A")` (and `+C`, `+V`, `+X`, `+Z`) selects all, copies,
  pastes, cuts and undoes as on Linux and Windows: the key down carries Chrome's editing
  command (`selectAll`, `copy`, `paste`, `cut`, `undo`) on every system, since macOS binds
  them to Command.
- Windows: switching the patched cache's `current` version no longer fails with
  `PermissionError` once a version is current (Windows cannot rename over a directory link:
  the old link moves aside first and comes back if the switch fails).
- Windows: the patched binary's remembered SHA256 is hashed again when the file is rewritten
  in place with its mtime put back (the record used `st_ctime`, which on Windows is the
  creation time; it now uses the file's change time).
- Windows launch: `launch_chrome_windows` (now in `tellurium.browser.launch_windows`) gives
  Chrome a Unicode environment block (the launch's `env`, so `TZ` and the rest reach it;
  `TMP` and `TEMP` on a temporary folder of ours, removed at close) and standard handles
  (`STARTF_USESTDHANDLES`): `chrome_log=` now works on Windows (with
  `--enable-logging=stderr` added unless the arguments choose a logging mode), and without
  it Chrome's output tail explains a failed launch as on POSIX. The child inherits only its
  pipe ends and standard handles (`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`). The process
  wrapper closes its handle once the exit code is read.
- Windows CDP pipe: reads and writes run on two threads of the transport instead of
  asyncio's shared executor, where every running Chrome held a worker for good (with a
  few browsers `asyncio.to_thread` stalled) and two large writes could interleave.
- `BrowserProcess.spawn` waits for Chrome's first answer (`Browser.getVersion`) up to
  `READY_TIMEOUT` (60 s) before the first command of the launch: a first start on a cold
  machine took more than the 30 s of that command (`Browser.setDownloadBehavior got no
  reply`).
- Stealth on stock Chrome whose version no file tells: Chrome is started, asked
  (`Browser.getVersion`), closed and started once more with the `--user-agent` of that
  version, so service and shared workers and what the browser fetches itself no longer
  show `HeadlessChrome`. The warning stays only for a product string without a version.
- The multiplexer kills a crashed or hung Chrome through its process object
  (`BrowserProcess.kill()`: SIGKILL, `TerminateProcess` on Windows) instead of
  `os.kill(pid, SIGKILL)`, which does not exist on Windows and could hit a reused pid.
- `timezone=` is refused when unknown also where Python has no time zone database
  (Windows without `tzdata`): Windows' own ICU (`icu.dll`) is asked.
- Chrome's version is read without `chrome --version` where that cannot work: on Windows
  from the install layout, then the executable's `VERSIONINFO` (never by running
  `chrome.exe`, which opens a window and does not exit); on macOS from the bundle's
  `Info.plist` when `--version` prints nothing. `find_chrome()` reads it off the event loop.
  The detection moved to `tellurium.browser.chrome_version.detect_chrome_version`.
- A launch that fails because Chrome exits with code 21 (`RESULT_CODE_PROFILE_IN_USE`,
  what Windows gives for a profile another Chrome holds) says that the profile is in use.
- `trap_link`: a `mask-image` gradient that fades into an `oklch()`, `lab()` or `color()`
  color is no longer taken for a transparent mask (a link was flagged `transparent`),
  and one whose colors all have alpha 0 in those forms is; a color whose alpha cannot be
  told counts as showing.
- `trap_link`: a `:focus` rule brings a hidden link back only if it wins the cascade
  against the rules that hide it (`!important`, `@layer`, specificity, order): a link
  hidden with `!important` or by a more specific selector stays a trap.
- Stock stealth, headless: when `chrome --version` cannot be read, the launch logs a
  warning on `tellurium` that Chrome starts without `--user-agent`, so robots.txt (and
  anything else the browser loads itself) leaves with `HeadlessChrome` while the pages
  show the profile's User-Agent.
- Stock stealth: service and shared workers report the page's client hints
  (`architecture`, `bitness`, `fullVersionList`, `uaFullVersion`, brands): their targets
  get the same `Emulation.setUserAgentOverride` as the page (with `--user-agent` they were
  empty, and the brands were Chrome's own). A service worker is no longer held 10 s at
  start and is patched before its script runs: frozen, it answers no command, so its patch
  is sent and the worker resumed before the replies are read.
- `Browser.close()` cancels the work it still runs in the background: the waits with no
  clock of their own for a late Chrome reply (the early script of `wait_for_human` on a
  busy page, the hidden robots.txt target) and the banner's cleanup are tasks of the
  browser, so none is left once it is closed, even mid-wait.
- A hidden robots.txt target whose `Target.createTarget` reply comes after the caller gave
  up is closed as soon as the reply lands, however late (it was watched for 30 s only);
  the wait for it lasts as long as the pipe, which is also the hidden target's lifetime.
- `wait_for_human` keeps one deadline: every CDP call takes at most what is left of the
  wait (5 s at most), so `timeout=3` on a page busy in 2 s ticks ends in under 4 s, and a
  timeout that expires inside `until` says `within N s` too. The banner's cleanup waits at
  most 0.5 s once the time is over and ends in the background, each call bounded. The
  early script Chrome confirms only after the wait (a busy page) is taken away as soon as
  its identifier arrives, also when `close()` is cancelled: no inert isolated world per
  document for the rest of the tab's life.
- The `wait_for_human` banner shows on SVG and XML documents (its elements are made in the
  HTML namespace); an exception of the banner's script is logged once as a warning
  instead of being swallowed.
- `Tab.expect_download()` takes a download started by an iframe nested inside a
  cross-site iframe (same site as it or a third one, at any depth, or one whose src is
  the download), stealth or not: such frames are reported to the cross-site iframe's
  own session only, so when a download of a frame no tab knows begins, each waiting
  tab looks it up in the frame trees of its cross-site iframes (`Target.getTargets`,
  then `Page.getFrameTree` through the session already attached or one attached then,
  which Chrome detaches with the frame), within 5 s. Progress reported meanwhile is
  kept; another tab's waiter does not take it.
- Snapshots of one document share its `Accessibility.getFullAXTree`: concurrent
  `snapshot(selector=...)` calls on a page whose tree must be read whole (shadow DOM)
  send one request, and a snapshot abandoned past `snapshot_timeout` leaves its request
  to the next one instead of queueing a second ~120k-node tree behind it. A request is
  shared only while nothing but snapshots was sent to Chrome after it (a click, a key,
  an eval, a navigation: the next snapshot asks again), only if no other command was
  still awaiting its answer when it went out (an input answered while the tree is built
  may act on the page after it, e.g. a cross-site iframe posting to its parent), and
  only for the same document.
  A snapshot command refused by a closed session (a cross-site iframe or a tab gone)
  sent nothing and does not count as sent, so an input after it still makes the next
  snapshot ask again. Concurrent snapshots of one tab no longer fail with "Could not find node with given
  id": their `DOM.getDocument` and selector lookups take turns.
- The `max_nodes` budget of a snapshot's cross-site iframes goes in document order: the
  iframes of a document are counted, then admitted one after the other, so with several
  large ones the same one is left out (`[oopif: too large, N nodes]`) whichever renderer
  answers first. One that is not counted within half of the time left (a stuck renderer)
  shows as not responding and does not hold the ones after it.
- A human click (and `hover()`) into an iframe drawn in 3D (`perspective`, `rotateX/Y`,
  `matrix3d`), cross-site or not and at any depth, reaches its element instead of raising
  `ElementNotHittableError`: a cross-site frame's points are mapped through the
  projective map from its box's four corners to where Chrome draws them, exact in
  perspective too, and for a mirrored frame (`scaleX(-1)`, `scaleY(-1)`). A frame seen
  edge-on (no area, or folded) still takes no click.
- A human click into a same-process iframe under a CSS `zoom` on one of its ancestors
  lands on its element: Chrome reports that frame's boxes divided by its zoom, which is
  now undone (each frame's `devicePixelRatio` is read in its own isolated world, so a
  frame of another origin than the tab's is read too); it used to aim at the wrong
  point and raise `ElementNotHittableError`.
- A human click into a cross-site iframe held by a same-process frame under a CSS zoom
  no longer lands on another element: the `<iframe>`'s box, which Chrome divides by the
  zoom of the frame holding it, is scaled back before it is mapped. When that zoom
  cannot be read, the click is refused with `ElementNotHittableError`, never sent.
- A human click on a node of another origin than the hit frame's world no longer fails
  with `KeyError: 'objectId'`: Chrome resolves it to no object, read as "not inside".
- `Tab.screenshot(full_page=True)` before the tab's first navigation has the CSS size
  under a device pixel ratio and gives the scrollbar back, as after a navigation: the
  main frame's id, not yet known from a `Page.frameNavigated`, is asked of Chrome.

- The local forwarder in front of an authenticated proxy is no longer an open proxy on
  `127.0.0.1`: every request head (plain requests and `CONNECT`, each one on a keep-alive
  connection) must carry `Proxy-Authorization: Basic tellurium:<secret>`, with a random
  secret drawn per forwarder (32 bytes, compared in constant time). Without it the client
  gets `407` with `Proxy-Authenticate: Basic realm="tellurium"` and `Connection: close`,
  and nothing reaches the upstream proxy. New `ProxyForwarder.auth_header` (the header
  value for tellurium's own clients) and `ProxyForwarder.credentials`. The secret never
  shows in `repr`, logs or errors. A new connection that sends no complete request head
  within 30 s (`ProxyForwarder.head_timeout`) is closed. Header names are read one way
  for the check and for the removal of `Proxy-Authorization`: a head with a folded line
  (obs-fold), whitespace before a colon or a line without one gets `407`, so no spelling
  of the header carries the secret upstream.

- `tellurium.access.allowed_hosts` treats every spelling of a wildcard bind (`0`, `::0`,
  `[::]`) as one, and a loopback bind other than 127.0.0.1 (`127.0.0.2`) accepts its own
  name: the MCP HTTP server no longer answers 403 to everything on those binds. New
  `access.token_leaked(target, token)` finds the token in a request's path or query, even
  percent-encoded twice.
- A proxy URL that cannot be parsed (unknown scheme, bad port) no longer quotes its
  user name and password in the error, for `Browser.launch` too. A password may hold
  unencoded `/`, `@`, `:`, `#`, `?` or `://`: the user info ends at the last `@`, and only
  a well-formed scheme counts as one before `://`, so such a
  proxy now works and its password never shows in messages or the multiplexer's status.
- `webrtc_ip='auto'`: the DNS lookup of the proxy host runs on a thread of its own, bounded
  by `launch_plan.DNS_TIMEOUT` (10 s, then `ValueError`), no longer in the event loop; a
  proxy URL without a host no longer puts the URL (and its password) in the `ValueError`.
  `webrtc_ip` given to stock Chrome without stealth, where nothing applies it, now logs a
  warning instead of being dropped in silence.

- The GeoIP step of a launch (`Browser.launch(stealth=True)` or `geoip=True` with a proxy)
  is bounded as a whole by `launch_plan.GEOIP_TIMEOUT` (10 s; then Chrome's default locale,
  with a warning): a proxy that accepts and never answers cost up to 40 s per launch. It
  runs on a daemon thread of its own, not on asyncio's default executor, and a cancelled
  launch returns at once: lookups given up on no longer starve the executor that `close()`
  uses to stop Chrome and remove the profile.

- GeoIP never asks a third party from the host's own address: with a proxy and no local
  database, the online country lookup (`ipapi.co`, `api.country.is`) used to be sent
  directly, with the proxy's exit IP in the URL. Every lookup request (exit IP and country)
  now goes through a `CONNECT` tunnel of the proxy's credential forwarder or of the plain
  HTTP proxy; a proxy it cannot tunnel through (SOCKS, HTTPS without credentials) and no
  proxy at all mean no online request, only the local database. `resolve_geoip()` takes
  `proxy=` and `forwarder_port=` for that; new `exit_geo(proxy, forwarder_port)` does both
  steps. Affects `Browser.launch(stealth=True, proxy=...)` too.

- `SessionPool`: the browser slots are handed out first come, first served, with no polling.
  Whoever releases a slot gives it to the oldest waiter (in any loop or thread) instead of
  freeing it for whoever polls first, so a task that closes and opens again in a loop no
  longer starves the others (with `max_browsers=1` and three such tasks a waiter could wait
  over a second). A waiter cancelled in the queue leaves it; one cancelled after the slot was
  given to it passes the slot on.

- Patched backend: cancelling `Browser.launch` while the binary is being resolved stops a
  security download in flight (between release lookup, `SHA256SUMS`, each 64 KiB chunk,
  each extracted file and the swap; network waits of such a download are 5 s) and waits up
  to 10 s for it, removes the partial files and leaves `current` where it was; before, the
  download went on in its thread and could still switch `current`.
  `download_patched(..., stop=)` and `install_from_tarball(..., stop=)` take a
  `threading.Event` for this. The binary is looked up under the cache's
  install lock (shared: launches do not wait for each other), so a forced reinstall
  swapping the version directory no longer makes a concurrent launch fail with "binary not
  found"; a cache whose lock file cannot be opened (read-only mount, image, another user's
  cache) is read without it. A launch waits for an install holding the lock at most 60 s
  (then `TimeoutError` naming the cache, e.g. behind a suspended `tellurium
  download-browser`), and stops waiting as soon as it is cancelled. A filesystem without `flock`
  raises its own error at once instead of waiting. With `auto_security_update=True`, a
  security download that fails on the network (timeout, reset) is logged and the installed
  binary is launched, as for any other download error.
- A `save_now()` cancelled (or a `save()` from a thread that gives up) mid-write no longer
  writes `cookies.json` after the close, over the jar the close saved: the writes of a start
  go one at a time, and a live save begun before the close is dropped. `save_now()` from a loop
  other than the start's raises `RuntimeError` instead of writing the old jar.
- `session.json` and `cookies.json` are written through a temporary file of their own (no
  longer a fixed `<file>.tmp`): two writers at once (a live save and the close) no longer
  leave a corrupt file, or fail renaming the other's.
- `tellurium login` no longer loses a cookie with no expiry written in the last 0.3 s before
  the person closes the sign-in window: a second, minimized window of Chrome keeps its
  browsing session open, so the close reads the whole jar. Closing both windows falls back to
  the jar read while one was open, as before.
- A session saved with its own `--user-agent` among its launch args opens again from
  `tellurium mcp` and `tellurium login`: they launch it without stealth instead of failing
  with a `ValueError` that suggests a `stealth=False` neither offers. The person is told: the
  `session-open` reply carries a `Warning:` line (and `warning` in its data), `tellurium login`
  prints it on stderr.
- `Session.start(on_login_failure="manual")`: without a display (`DISPLAY` and
  `WAYLAND_DISPLAY` unset on Linux) it fails at once with a `SessionLoginFailedError` that
  says so, instead of a `LaunchError` carrying Wayland's log from the headed relaunch; each
  round of the validators gets at most 30 s (`manual_login.VALIDATOR_TIMEOUT`) and within the
  deadline, so a validator that hangs shows the banner again instead of stalling the start.
- `Session.save()` during a start no longer writes the cookie jar read at the start: from
  another thread (`await asyncio.to_thread(session.save)`) it waits for Chrome's jar (at most
  10 s); on the loop of the running start, where it cannot wait, it raises `RuntimeError`
  pointing to `await session.save_now()`. `tellurium mcp` and `tellurium login` use
  `save_now`.
- `SessionPool` works across one `asyncio.run` after another, and its `max_browsers` holds
  across event loops running at once in threads: the slots are a count under a thread lock,
  waited for without blocking the loop, instead of an `asyncio.Semaphore` made in `__init__`
  (it failed with "bound to a different event loop").
- `SessionPool.open`: an identity deleted (by another process) while its open waited for a slot
  no longer starts empty with a seed that is never saved: under the session lock its
  `session.json` is written again with the same seed, or `FileNotFoundError` with
  `create=False` (the empty folder the lock made is then moved away under the lock taken anew,
  never by removing a held lock file).
- `Session.start` waiting for a dead holder's Chrome now recognises it on Linux when its
  rewritten title has arguments after `--user-data-dir` (a URL, headed) or the profile path
  holds ` --`: it no longer starts a second Chrome on a profile still in use (exit 21).
- `Session`: a cookie restore whose answer from Chrome comes after the 5 s timeout (or the
  look at Chrome's jar that comes first) still counts when it arrives, so the close no longer
  puts back a cookie Chrome took (or already had) and the site deleted during the run.
- A `cookies.json` that cannot be parsed, whatever the error (a `RecursionError` on a
  deeply nested file included), no longer fails every `Session.start`: it gives a warning,
  is moved to `cookies.json.bad-<time>` and the next close writes a good one.
- A `Tab.get` (or `new_tab(url)`, `is_allowed`) whose robots.txt cannot be loaded because
  the hidden target it is loaded from cannot be opened (`Target.createTarget` or the
  attach failing or timing out) raises `NavigationError` with the cause chained, instead
  of a bare `TimeoutError` or `CDPError`.
  When `Target.createTarget` timed out but Chrome creates the target later (within 30 s),
  that hidden target is closed as soon as it arrives instead of staying open unowned.

- A new `Session` no longer draws its fingerprint seed from the global `random`: a script
  that called `random.seed()` gave every new identity the same seed.
- A session start waits again for a live Chrome still holding the session profile: on
  Linux Chrome rewrites its process title (`/proc/<pid>/cmdline` becomes one string of
  space-joined arguments) and its `--user-data-dir` was never found, so the start went
  ahead and Chrome failed with "profile in use". Paths with spaces are read too.
- `Tab.eval_on` never runs the code twice: it is retried as a function body only when
  the first form does not compile (a `SyntaxError` before anything runs), and describing
  a thrown value can no longer throw (`throw Object.create(null)` raised inside the
  error handler, so the expression ran again as a body). A body now runs in an `async`
  function, so `await` works in it. A returned value that throws while Chrome
  serializes it (a throwing getter, a Proxy) is a `RuntimeError`, not a `CDPError`.
- `Tab.screenshot(full_page=True)` captures the whole page: the clip uses
  `cssContentSize` (falling back to `contentSize`) with `captureBeyondViewport`, scaled by
  `1/devicePixelRatio` so the image has the page's CSS size. Before, everything past the
  viewport came out blank, and a HiDPI screen doubled the size. The image can now be
  larger than before. The capture lays the page out at its full height, without a
  vertical scrollbar, so the clip is at least `innerWidth` wide (the right edge is in it;
  CDP's content size, floored under a fractional ratio, no longer drops a column).
  Chrome may leave the scrollbar hidden after such a capture until the viewport's
  scroller is laid out again: the screenshot (and the MCP `screenshot` tool, which now
  shares the clip and the capture) relayouts it from tellurium's isolated world, only
  when a scrollbar went, through the element the viewport takes its overflow from, so
  `clientWidth`, `scrollY` and the absence of `scroll` events are as before (also with
  `html, body {height: 100%}` and a scrolling `<body>`, and in quirks mode, where the
  scrollbars are measured on `document.scrollingElement`). Cancelled mid-capture, it
  restores once Chrome answers, in a task of the tab. The page's sizes are read only in
  the isolated world, never in the page's own, and checked before use.
- `Tab.keyboard_press` sends keys Chrome acts on: `rawKeyDown` with the Windows virtual
  key code, a `char` event when the key types text (none with Control/Meta), `keyUp`.
  `"Enter"` now submits the focused form and `"Control+a"` selects all; before, only
  `key` was sent and the page did nothing. An unknown key or modifier raises
  `ValueError` before any event (it was silently ignored). New `human=True` holds the key
  40-110 ms. The key table lives in `tellurium.browser.keys`, shared by the human typing
  path and the MCP tools (their messages are unchanged). `"Control++"` presses `+`,
  `"Shift+a"` types `A`, and `keyboard_type` types a newline as `Enter` (a textarea
  got nothing for it): `\n`, `\r` and `\r\n` are one `Enter` each.
- `Browser.close()` removes the stealth extension's `tellurium_ext_*` temp
  directory right away instead of when the engine is garbage-collected.
- A stealth launch no longer leaves `/tmp/tellurium_ext_*` behind: the stealth
  engine owns its extension directory and deletes it when it goes away with its
  `Browser` (after `close()` or a failed launch) or at interpreter exit;
  `StealthEngine.close()` deletes it at once.
- The hit check before a pointer press (`human=True` clicks, `hover`,
  `drag_to`) asked Chrome about the wrong point once the page was scrolled
  (`DOM.getNodeForLocation` takes document coordinates, not viewport ones), so
  a target below the fold raised `ElementNotHittableError` or was checked
  against another spot; the frame's scroll is now added.
- `Element.click(human=True)`, `hover()`, `drag_to()` and
  `scroll_into_view(human=True)` take the element's box from Chrome's layout
  (`DOM.getContentQuads`, new `tellurium.browser.geometry`): page coordinates
  also for a node inside a same-process iframe (the frame-relative
  `getBoundingClientRect` sent the click elsewhere on the page), and a value
  page JS cannot fake. A node without a box raises `StaleElementError` instead
  of clicking near (0, 0); the human click reads the box again right before
  the press and sends nothing if the node was replaced or moved meanwhile.
  Before the press (and before `hover()` moves the pointer) Chrome hit-tests the
  point (`DOM.getNodeForLocation`, as a click would: `pointer-events: none`
  overlays let through): unless the node there is the element, one of its
  labels (custom checkboxes; not through another control inside the label,
  such as a link), or inside them (through frames and shadow roots),
  no event is sent and
  `ElementNotHittableError` names what is on top (an overlay, or a frame under
  CSS `zoom`, whose quads Chrome reports unscaled). `drag_to()` checks both
  ends before pressing.
- `reinstall()` (and `tellurium verify-browser --reinstall`) no longer deletes
  the installed version before the new copy is downloaded and verified: a failed
  download leaves the install usable.
- Concurrent chromium-telluride installs (two launches with
  `auto_security_update`, the CLI next to a launch) no longer break each
  other: the swap into place and the `current` switch run under a file lock
  (`<cache>/.install.lock`, `fcntl.flock` / `msvcrt.locking`), the `current`
  link is written through a uniquely named temporary, the old install is moved
  aside before the new one takes its place, and reinstalling the same binary
  keeps the install Chrome may be running from. Filesystem errors while
  installing raise `DownloadError` with the reason. The returned entry is read
  under the lock (concurrent forced installs raised `KeyError`); if the new
  copy cannot be moved in, the old one is put back; installs moved aside by an
  interrupted swap are deleted by the next install and by `prune-browsers`,
  which also removes versions under the lock.
- `Tab.eval_on(selector, "el => el.id")` passes the element as the first
  argument as well as `this`: arrow functions got `undefined` for `el`. The
  expression is no longer rewritten as text: it is evaluated inside a function
  bound to the element, so `"() => this.id"`, `"async el => …"`,
  `"(el => el.id)"`, plain expressions (`"this.id"`) and function bodies
  (`"return this.id"`, as documented) all work, and a trailing `//` comment is
  harmless. A JavaScript exception or a syntax error raises `RuntimeError`
  instead of returning `None`.
- `BrowserContext.get_cookies(domain)` matches the domain and its subdomains
  instead of any substring, like `Browser.get_cookies`.
- `Browser.launch(stealth=True, proxy=...)` looks up the proxy exit IP and its
  GeoIP data in a worker thread: run on the event loop, the lookup through an
  authenticated proxy starved the forwarder it was waiting for.
- `Browser.launch` resolves the browser binary off the event loop: with
  `browser="patched"` the daily update check (HTTP), an automatic security
  download and the binary hash no longer freeze the event loop.
- The patched binary is no longer rehashed (~300 MB) on every launch: its
  SHA256 is remembered beside it until the file changes (size, inode, mtime,
  ctime) and reused by the MANIFEST check. A `chromium_sha256` pin is always
  checked against a full hash: the record sits beside the binary and could be
  rewritten with it.
  `PatchedEngine.get_executable()` resolves the binary in a worker thread.
  `tellurium verify-browser` still hashes the file in full.
- The initial tab enables the `Page` domain at launch, so a dialog opened
  before its first `get()` (e.g. by `tab.eval("alert(1)")`) is answered
  instead of blocking the tab.
- `new_tab()` raises the builtin `TimeoutError` with the target id when the
  new page is not ready in time (on Python 3.10 it was `asyncio.TimeoutError`).
- Chrome for Testing extraction checks every symlink once the archive is
  unpacked, resolving it as the kernel does: a chain of links (`s1 -> ../..`,
  `l -> s1/../../../x`) that looked inside the install dir lexically but led
  out of it was accepted.
- Installing a chromium-telluride release can no longer write or delete outside
  the cache: the install directory named by the tarball's `MANIFEST.json` (and
  the version given to `reinstall` / `set_current`) must be a chromium version
  such as `146.0.7680.188`; `../../Documents` or an absolute path is refused
  before anything is removed. Hardlinks inside the tarball install correctly
  (their target kept the stripped top directory).
- `download_patched` refuses a release whose `SHA256SUMS` is missing,
  unreachable or does not list the tarball (`DownloadError`), since the MANIFEST
  that checks the binary ships in the same tarball; `allow_unverified=True`
  opts out.
- The credential forwarder for authenticated proxies copies request bodies
  (a POST hung), serves every request of a keep-alive connection (the second
  one hung), replaces client-sent credentials, and passes a refused `CONNECT`
  (407, 502…) through to Chrome instead of claiming the tunnel was up (Chrome
  reported an SSL error), chunked refusal bodies included. An unreachable
  upstream answers 502, one that never answers a `CONNECT` 504 (after 30 s).
  Request heads are capped at 64 KiB and bodies are streamed, never buffered
  whole. `stop()` closes the connections still open, also one accepted a
  moment before whose handler had not started (it used to hang).
- `Browser.launch(proxy=...)` keeps the scheme: `socks5://`, `socks4://` and
  `https://` proxies were passed to Chrome as plain HTTP proxies. IPv6 hosts are
  bracketed, a bare `host:port` means HTTP, unknown schemes and SOCKS URLs with
  credentials (Chrome cannot authenticate to SOCKS) raise `ValueError` before
  Chrome starts. Percent-encoded proxy credentials are decoded, and an
  authenticated `https://` proxy is reached over TLS by the forwarder.
- `Browser.clear_cookies()` and `clear_cookies(domain)` work: they used the
  `Network` domain on the browser session, which has none, and always failed.
- `Browser.get_cookies(domain)` (and `save_cookies(domain=...)`) match the
  domain and its subdomains instead of any substring: `"example.com"` no longer
  returns `notexample.com` cookies. A subdomain also gets the parent-domain
  cookies it receives (`.example.com` for `sub.example.com`); a domain without
  a dot (`"intranet"`, `"com"`) matches only itself, so `"com"` no longer
  returns every site. `clear_cookies(domain)` keeps the parent domain's cookies.
- Netscape cookie files keep `#HttpOnly_` lines on import (they were skipped as
  comments, dropping the session cookies) and write the prefix on export.
- `save_cookies` / `load_cookies` read and write the file off the event loop.
- `Tab.get(timeout=...)` longer than 30 s is no longer cut short by the new
  per-command default: `Page.navigate` is bounded only by the navigation
  deadline. `Tab.eval(expression, timeout=None)` takes an explicit timeout for
  long promises (default: the session's 30 s).
- A crashed tab stayed open in Chrome and `main_tab` kept pointing at it, so
  `browser.get()` failed for good. The crashed target is now closed, `main_tab`
  moves to another open tab, and `browser.get()` opens a new main tab when
  none is left.
- A launch cancelled a second time while rolling back (or `asyncio.run`
  ending right after) skipped the remaining cleanup: the pipe, the proxy
  forwarder and the temporary profile were left behind. `Browser.close()` now
  runs every step, each bounded by a timeout, and re-raises the cancellation
  at the end.
- Every launch/close cycle left Chrome's shared-memory files and singleton
  socket dir (`.com.google.Chrome.*`, about 400 KB, RAM on tmpfs) in the
  system temp dir. Chrome now gets a private `TMPDIR`, removed on close
  (POSIX).
- Tellurium-managed Chrome for Testing installs were ranked by directory name,
  so `chrome-99…` beat `chrome-140…`; they are ranked by version now.
- `download_cft` extracted with `zipfile.extractall`, losing exec bits
  (`chrome_crashpad_handler`) and symlinks (macOS framework links); modes and
  links are kept now; entries and symlinks pointing outside the install dir
  are refused. The archive is extracted in a hidden staging dir and renamed
  into place, so a failed download never leaves a half-extracted install.
  Download and extraction run off the event loop.
- Windows: the Chrome version (used to refuse extensions on branded Chrome
  137+) is read from the install layout; `chrome.exe --version` prints
  nothing there, so the check silently passed.
- Chrome's stdout and stderr went to pipes nobody read: once about 64 KiB of
  log piled up (failed TLS handshakes, `--enable-logging=stderr`) Chrome
  blocked and every CDP command hung. The output is now drained on a thread
  (or written to `chrome_log`).
- `Browser.launch()` is all-or-nothing: on failure or cancellation (e.g.
  `asyncio.wait_for` timing out) the Chrome process is reaped and the pipe,
  temporary profile and proxy forwarder are released. When Chrome exits during
  launch, `LaunchError` reports its exit code and last output (a profile
  already in use, a missing library) instead of `ConnectionError('Browser pipe
  closed')`.
- `Browser.close()` stops Chrome before closing its pipe (on Windows closing a
  pipe with a pending read can block), reaps it without blocking the event
  loop, and still releases everything when cancelled.
- The CDP pipe did not reach Chrome when the parent's pipe ends landed on fds
  3 or 4 (an embedder with few open fds): the child closed the end it had just
  set up.
- A crashed renderer (OOM, killed process) left its tab in `browser.tabs` and
  every command on it waiting forever. `Target.targetCrashed` now fails the
  tab's pending and future commands with `TargetCrashedError` (a
  `ConnectionError`, in `tellurium.cdp.types`) and drops the tab.
- The pipe transport re-scanned its whole receive buffer for the message
  terminator on every chunk, so one large reply (full-page screenshot, big
  response body) cost quadratic time with the event loop blocked: 64 MB took
  about 1.5 s. Only new bytes are scanned now.
- `PipePosixTransport.close()` left the read end of the CDP pipe open: one fd
  leaked per launch/close cycle.
- Element handles no longer pin DOM nodes: every query resolves into the tab's
  `objectGroup`, an `Element` dropped by Python releases its handle (batched),
  result arrays are released right after use, and the group is released on
  each main-frame navigation and on `Tab.close()` (bounded to 0.5 s, so a
  frozen page does not delay the close). Before, 20 rounds of
  `select_all` over a 300-row feed kept ~12000 removed nodes alive.
- Commands on an element are bounded (30 s): a page frozen by an open dialog
  raises `TimeoutError` instead of hanging.
- A stale element (its document navigated away, or it was released) raises
  `StaleElementError` (a `CDPError`) instead of a bare
  `CDP error -32000: Cannot find context with specified id`.
- `Tab.select` and `wait_for` keep polling when a navigation replaces the
  document between `DOM.getDocument` and `DOM.querySelector` (a popup swapping
  `about:blank` for its page) instead of raising `CDPError`.
- `Tab.select_all`, `xpath` and `xpath_all` skip a node removed between the
  query and its resolution instead of raising `CDPError`.
- `Tab.get(timeout=...)` now bounds the whole navigation, `Page.navigate`
  included: a server that holds the response raised nothing before. On expiry
  the load is stopped and `NavigationTimeoutError` (a builtin `TimeoutError`,
  also on Python 3.10) names the URL and the phase (`commit`, `load`…). A
  refused navigation raises `NavigationError` (a `RuntimeError`) with the URL
  and a hint for `net::ERR_ABORTED` (204 responses, downloads). Enabling the
  lifecycle events, `Page.stopLoading` on expiry and reading the title all
  stay inside the same deadline.
- `Tab.wait_for_navigation()` ignores iframe navigations, waits for the `load`
  of the main-frame document that matches the pattern (not of an earlier page
  in a redirect chain), returns on a back/forward-cache restore, and no longer
  sets `tab.url` to an iframe URL.
- Elements went stale after any later query: every `select`/`xpath`/`find`
  refreshes the DOM agent (`DOM.getDocument`), voiding all earlier nodeIds,
  so `h1 = select("h1"); select("p"); h1.text()` raised "No node with given
  id". Elements are now addressed by their `objectId`, resolved as soon as
  they are found; `html()`, `attributes()`, `upload()`, `focus()` and the
  relative `select()`/`select_all()` no longer use nodeIds.
- CDP dispatch could hang every pending command: an event handler that raised
  killed the dispatch loop silently; a detached target left its commands
  waiting forever; a malformed message ended the loop without failing them.
  Handler errors are now logged, detached sessions fail their pending and
  future commands with `ConnectionError`, and any end of the loop fails all
  pending commands.
- `webrtc_ip="auto"` with `browser="patched"` passed the literal `auto` to
  `--fingerprint-webrtc-ip`, which the fork took as the IP to advertise. The
  resolved IP is passed now; `"disable"` leaves the flag out.
- `Tab.get()` ignored `wait_until` and timed out on same-document
  (`#fragment`) navigations; `Tab.title` was always `""`; `Tab.url` kept the
  requested URL after a redirect.
- `BrowserContext.new_tab()` applied no stealth or overrides and loaded the
  URL before any patching.
- `Tab.select()`/`wait_for()` raised instead of retrying when a navigation
  removed the node between the query and its resolution.
- CHANGELOG/README claimed 3 residual CreepJS lies on the patched binary; the
  2026-04-27 triage measured `totalLies = 0`.
- Accept-Language: `Emulation.setUserAgentOverride.acceptLanguage` leaked the
  raw q-value string into `navigator.languages` (`["en-US", "en;q=0.9"]`),
  produced a malformed header (`"en-US, en;q=0.9;q=0.9"`) and a window/worker
  mismatch — a value real Chrome never emits. Chrome now derives both from
  `--accept-lang=<profile languages>`: header `en-US,en;q=0.9`,
  `navigator.languages` `["en-US","en"]` in window and workers. Measured on
  Chrome 153; CreepJS gate re-run 8/8, lies 0.
- `Tab.xpath()`: dropped an unused root id, always calls
  `DOM.discardSearchResults`, uses `get_running_loop()` in callbacks, and
  removed a no-op `native_client_hints` branch.
- Stealth documentation in `README.md` described the pre-T7/T7.5 posture
  (extension-only delivery, WebGL spoofing, `toString` masking); realigned
  with the shipped engine.
- A reinstall of the patched browser waiting for the cache's install lock is no longer
  starved by readers whose shared holds overlap: while an install waits, no new reader
  gets in (an `.install.gate` file next to `.install.lock`).
- A `Slots` slot handed to a waiter whose loop was stopped, then closed without
  cancelling the task, is no longer lost: the next caller finding no slot free takes it
  back and hands it on.
- Multiplexer: a request with a body (`Content-Length` other than 0, or a
  `Transfer-Encoding`) gets HTTP 400; websockets used to close it without an answer.
- Multiplexer: a client that hangs up while its Chrome is launching no longer throws that
  launch away: its place is free at once, the next client in the queue takes the Chrome
  being launched (and its proxy); with nobody waiting and no warm Chrome wanted, it is
  closed once up.
- Multiplexer: the relay's own-session attach has one deadline for its two commands
  (`health.TIMEOUT` in all, not each); what is held for the client during it counts
  against `HIGH_WATER`, and with no client nothing is held.
- GeoIP lookups through an HTTP proxy are bounded as a whole, not per read: a proxy that
  sends a byte now and then no longer keeps the lookup's thread and socket alive for
  hours (the socket is shut down at the request's deadline).
- The proxy forwarder no longer writes its 407 after a response cut short: when a later
  request of a keep-alive connection lacks the credentials, the responses already on
  their way go through first (until the upstream is quiet for 1 s, at most 30 s).
- `Multiplexer.serve()` raises `ValueError` for a `timezone` launch option that is no IANA
  time zone, before anything starts (the places used to retry the launch for ever).
- `RawChrome.close()` closes Chrome and its profile even when asking it to close fails
  with an unexpected error, then raises that error.

## [0.1.0] - 2026-04-26

First release-ready version of tellurium as an independent Python library.
Stock-Chrome path is fully functional; patched-binary path is experimental
(manual install workflow).

### Added

- T1: CDP layer (pipe transport, no observable WebSocket port)
- T2: Browser core (launch, tab management, navigation, element selection)
- T3: Stealth engine (Chrome-extension-based stealth patches; no detectable script injection)
- T4: Human input simulation (Wind Mouse, biomechanically correct typing dynamics)
- T5: Network capture (CDP-based request/response interception)
- T6: Testing & packaging baseline (294 unit tests + 28 stealth tests)
- T7: Runtime stealth via CDP `Page.addScriptToEvaluateOnNewDocument`
  (works on Chrome branded ≥137 where `--load-extension` is rejected)
- T7.5: Stealth scripts cleanup (consolidated, marker scheme for cross-realm masking)
- T7.6: Stealth hardening — 8/8 CreepJS parity with nodriver, 0 lies, headless=0%
- Stock-Chrome path: first-class, fully documented in README
- Patched-binary path: experimental, manual install via `executable=` kwarg
  or `~/.tellurium/chromium/<version>/` cache layout (see README)
- Optional `[geoip]` dependency for proxy-exit-IP-based timezone/locale resolution

### Verified

- **Build dry-run**: `uv build` produces clean sdist (337 KB after explicit
  `[tool.hatch.build.targets.sdist]` whitelist) + wheel (309 KB). Both
  install cleanly in a fresh Python 3.13 venv. `tellurium.__version__`
  returns `0.1.0`. `[geoip]` optional dep installs `maxminddb==3.1.1` and
  imports. `tellurium --help` post-install shows all 8 subcommands.
  LICENSE and METADATA verified in wheel `dist-info/`.
- **Multi-Python**: unit suite (296 tests = 294 baseline + 2 new CLI
  messaging tests) passes on Python 3.10.20 (uv-installed) and Python
  3.13.13 (uv-installed). No syntax or library incompatibilities surfaced.
- **3.10 syntax compatibility**: pre-flight grep for Python 3.11+ idioms
  (`typing.Self`, `ExceptionGroup`/`except*`, `@override`, `TypeAliasType`,
  PEP 695 `type` statement) found zero hits across the `tellurium/` package.
- **Stealth regression**: `tests/stealth` 28/28 green in 12.78s. Live
  CreepJS comparative (`examples/fingerprint_tests/comparative_test.py`)
  shows tellurium parity **8/8** with the nodriver baseline,
  `headless=0%`, `like_headless=38%`, `stealth=0%`, `lies=0`,
  `webdriver=False`, sannysoft 0 fails, browserscan no bot. No regression
  vs T7.6 baseline. Chrome version: 147.0.7727.101.
- **CI workflow**: `.github/workflows/ci.yml` YAML syntax valid (parses via
  `yaml.safe_load`), draft state documented in `.github/workflows/README.md`,
  ready-to-activate on first GitHub push.

### Known limitations

- `like_headless ~38%` on CreepJS is environmental (display/GPU/audio fingerprint), no lies
- Patched binary is experimental in v0.1; auto-download tooling deferred to v0.1.x
- 3 lies on CreepJS when using the experimental patched binary —
  tracked in chromium-telluride repository

### Deferred (future)

- (closed in Unreleased) Auto-download tooling for the patched binary
  (`download-browser --browser patched`, `update-browser`,
  `verify-browser --reinstall`); F6 worker-scope masking — resolved by
  patching `hardwareConcurrency` only and deliberately *not* defining
  `navigator.webdriver` in workers; periodic baseline re-validation cadence —
  now the weekly `nightly-creepjs.yml` parity gate.
- T8 Honeypot + robots.txt detection (renamed from "T7" on 2026-09-15 to avoid
  colliding with the T7 runtime stealth layer)
- F7 dynamic same-origin iframe injection
- `_NATIVE_SHAPES` array refactor (T7.6 reviewer note)
- CreepJS bundle content hashing for drift detection (T7.6 reviewer note)
- Multi-OS CI matrix (macOS, Windows) — CI is Linux-only

### Notes

- CI workflow `.github/workflows/ci.yml` existed in draft state at v0.1 release
  time (no GitHub remote); activated in Unreleased
- Pre-migration history of C-series specs (chromium-telluride patches) reachable from `tellurium@ace0afa`
