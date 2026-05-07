# R7 Phase 1 — starlette IntentCluster smoke output

Generated from `https://github.com/encode/starlette` (history_depth=30, post-G8 noise filter).

- Commits scanned: **566**
- Commits with decision signal: **18**
- IntentClusters: **14**

Each cluster groups commits sharing `(intent_kind, primary_path)`. Phase 2 will feed each cluster to the LLM with a "what rule do these commits jointly establish?" prompt.

## Clusters (size DESC, then intent priority)

### #1 — PREFERENCE · `starlette/middleware/cors.py` · 3 commits

- **`995d70c7c6de`** — Set explicit Origin in CORS preflight response if allow_credentials is True and allow_origins is wildcard (#1113)
  - patterns: ['due to', 'instead of']
  - body: * Set explicit Origin in CORS preflight response if allow_credentials is True and allow_origins is wildcard When making a preflight request, the browser makes no indication as to whether the actual subsequent request will pass up credentials. However, unless the preflight resp...
- **`602212613c07`** — Add Origin to Vary header on credentialed CORS response (#1111)
  - patterns: ['as opposed to', 'rather than']
  - body: * Add Origin to Vary header on credentialed CORS response According to the [MDN CORS docs] (https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS#Access-Control-Allow-Origin), the `Origin` item should be added to the `Vary` header when the `Access-Control-Allow-Origin` is set...
- **`7a0f89abb860`** — Respond to credentialed requests with specific origin (#105)
  - patterns: ['instead of']
  - body: * Respond with specific origin instead of wildcard for credentialed requests * Add test case for credentialed standard request * Add tests for setting vary header

### #2 — PREFERENCE · `starlette/config.py` · 2 commits

- **`48dea4ddf1ed`** — add typing overloads for Config.__call__ (#1097)
  - patterns: ['instead of']
  - body: * add typing overloads for Config.__call__ This allows for more precise return types instead of the current `Any`. We have 3 overload cases here: 1. handles cases where the user provides an explicit `cast` argument. ``` reveal_type(config("POOL_SIZE", cast=int)) # note: Reveal...
- **`b95acea973c2`** — Update CI scripts to match httpcore (#1043)
  - patterns: ['instead of']
  - body: * Update CI scripts to match httpcore * Run test suite on pushes to master * Update scripts README * Don't bother with flake8 extensions for now * Remove unnecessary PYTHONPATH from build, publish * test_routing: Use a stub app instead of ellipsis * Add link to issue about typ...

### #3 — PREFERENCE · `starlette/middleware/errors.py` · 2 commits

- **`55cbba945636`** — Support Python 3.13 (#2662)
  - patterns: ['instead of']
  - body: * Support Python 3.13 * Use `exc_type_str` instead of `exc_type.__name__` * Close GzipFile * min changes
- **`faea6c290a69`** — Use format_exception instead of format_tb (#1031)
  - patterns: ['instead of']
  - body: * Use format_exception instead of format_tb This gives much more information about the exception, including causes, and the exception message itself, in addition to the trackback * Update test Co-authored-by: Jamie Hewland <jhewland@gmail.com>

### #4 — REJECTION · `starlette/responses.py` · 1 commit

- **`93e74a4d2f17`** — Support the WebSocket Denial Response ASGI extension (#2041)
  - patterns: ['rejected']
  - body: * supply asgi_extensions to TestClient * Add WebSocket.send_response() * Add response support for WebSocket testclient * fix test for filesystem line-endings * lintint * support websocket.http.response extension by default * Improve coverate * Apply suggestions from code revie...

### #5 — PREFERENCE · `starlette/concurrency.py` · 1 commit

- **`42592d68e5d7`** — anyio integration (#1157)
  - patterns: ['due to', 'instead of']
  - body: * First whack at anyio integration * Fix formatting * Remove debug messages * mypy fixes * Update README.md Co-authored-by: Marcelo Trylesinski <marcelotryle@gmail.com> * Fix install_requires typo * move_on_after blocks if deadline is too small * Linter fixes * Improve WSGI st...

### #6 — PREFERENCE · `starlette/formparsers.py` · 1 commit

- **`789b9269fd3f`** — Use `bytearray` for field accumulation in `FormParser` (#3179)
  - patterns: ['to avoid']
  - body: Replace immutable `bytes` concatenation with mutable `bytearray.extend()` in `FormParser.parse()` to avoid O(n²) copying when accumulating field names and values.

### #7 — PREFERENCE · `starlette/middleware/base.py` · 1 commit

- **`3d77a1c3e370`** — Fix high memory usage when using BaseHTTPMiddleware middleware classes and streaming responses (#1018)
  - patterns: ['to prevent']
  - body: * BaseHTTPMiddleware add maxsize arg to Queue constructor - Limit queue size to 1 to prevent loading entire streaming response into memory

### #8 — PREFERENCE · `starlette/middleware/gzip.py` · 1 commit

- **`b48b80f41e43`** — docs: fix simple typo, ougoging -> outgoing (#1120)
  - patterns: ['rather than']
  - body: There is a small typo in starlette/middleware/gzip.py. Should read `outgoing` rather than `ougoging`. Co-authored-by: Jamie Hewland <jhewland@gmail.com>

### #9 — PREFERENCE · `starlette/routing.py` · 1 commit

- **`07427f86474b`** — Fix `routing.get_name()` not to assume all routines have `__name__` (#2648)
  - patterns: ['rather than']
  - body: Fix `routing.get_name()` to use the `__name__` attribute only if it is actually present, rather than assuming that all routine and class types have it, and use the fallback to class name otherwise. This is necessary for `functools.partial()` that doesn't have a `__name__` attr...

### #10 — PREFERENCE · `starlette/staticfiles.py` · 1 commit

- **`51057d57449c`** — Handle null bytes in `StaticFiles` path (#3139)
  - patterns: ['instead of']
  - body: * Handle null bytes in StaticFiles path * Add test for null byte in path * Return 404 instead of 400 for null bytes in path

### #11 — PREFERENCE · `tests/conftest.py` · 1 commit

- **`d222b87cb460`** — TestClient accepts backend and backend_options as arguments to constructor (#1211)
  - patterns: ['as opposed to']
  - body: as opposed to ClassVar assignment Co-authored-by: Jamie Hewland <jhewland@gmail.com> Co-authored-by: Jordan Speicher <jordan@jspeicher.com> Co-authored-by: Jordan Speicher <uSpike@users.noreply.github.com>

### #12 — PREFERENCE · `tests/middleware/test_errors.py` · 1 commit

- **`df2985f50e92`** — Missing annotations debug module (#68)
  - patterns: ['instead of']
  - body: * fix(Missing annotation): missing annotations added on debug module. * fix(debug.py): linting fixed. * fix(debug annotations): annotations fixed. * fix(): ASGIInstance annotation type should be used on return of _DebugResponder __call__ method. * fix(): Exception type should ...

### #13 — PREFERENCE · `tests/test_testclient.py` · 1 commit

- **`254d0d97e463`** — ensure TestClient requests run in the same EventLoop as lifespan  (#1213)
  - patterns: ['rather than']
  - body: * ensure TestClient requests run in the same EventLoop as lifespan * for lifespan task verification, use native task identity rather than anyio.abc.TaskInfo equality https://github.com/agronholm/anyio/issues/324 * remove redundant pragma: no cover * it's now a loop_id not a th...

### #14 — CONSTRAINT · `tests/conftest.py` · 1 commit

- **`78fcd54c0798`** — Create types module inside tests (#2502)
  - patterns: ['due to']
  - body: * Create types module inside tests * Apply suggestions from code review * Apply suggestions from code review * Fix check errors * Change testclientfactory due to autotest * No cover fix * Apply suggestions from code review * Skip code coverage for TestClientFactory protocol * ...
