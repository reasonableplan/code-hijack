# PR Decisions -- what the senior team explicitly rejected or reverted

> Mined from 100 PRs/issues of https://github.com/pallets/werkzeug: closed-unmerged proposals, incident reverts, and reviewer preferences
> recorded in GitHub PR/issue history. Rejection and incident decisions
> are cited-evidence-grade -- MUST rules may cite them directly.

## Recurring decision patterns (by occurrence)

1. **regression** (11 items)
   - "Fixes #3189 ## Summary - Preserve empty-but-present usernames and passwords when rebuilding URLs in `uri_to_iri` and `ir"
   - "`uri_to_iri()` and `iri_to_uri()` rebuild the userinfo part of a URL using a truthiness check on the username and passwo"
   - "`uri_to_iri()` and `iri_to_uri()` currently check `SplitResult.username` and `.password` by truthiness when reconstructi"
2. **instead of** (4 items)
   - "`parse_options_header` parses a header value with `key=value` parameters (e.g. `Content-Type`, `Content-Disposition`). I"
   - "Corrected subject-verb agreement in error description ("fields exceed" instead of "fields exceeds"). <!-- Before opening"
   - "## Summary - Fix `Rule.compile()` to use greedy regex `/{2,}` instead of non-greedy `/{2,}?` when `merge_slashes=True` -"
3. **rather than** (1 items)
   - "## What Fixes to allow empty hosts when is not configured. This aligns with HTTP/0.9 and HTTP/1.0 where the Host header "
4. **rejected** (1 items)
   - "Sorry for the confusion in the previous version of the patch. When I first tried to add the fix, I accidentally removed "
5. **to prevent** (1 items)
   - "Sorry for the confusion in the previous version of the patch. When I first tried to add the fix, I accidentally removed "
6. **tried** (1 items)
   - "Sorry for the confusion in the previous version of the patch. When I first tried to add the fix, I accidentally removed "

## Rejected proposals (closed without merge)

- `PR#3143` (2026-03-26) **fix: allow empty host when trusted_hosts is not set**
  matched: `rather than`
  > ## What Fixes to allow empty hosts when is not configured. This aligns with HTTP/0.9 and HTTP/1.0 where the Host header is optional and may appear as an empty string. ## Why Previously, an empty host would always raise , even when was not set. Now, when is not set, empty or invalid hosts are returned as empty string rather than raising an error. This matches the expected behavior described in issue #3142. ## How When is not set, the function now returns empty string for empty or invalid hosts (via returning False) rather than raising . When is set, the strict validation behavior is preserved. ## Testing Updated tests to reflect the new behavior: - : Empty host returns empty string - : Unix socket with empty host returns empty string - : Invalid characters return empty string when is not se
  Rejected code:
  ```diff
  --- src/werkzeug/sansio/utils.py
  @@ -108,8 +108,9 @@ def get_host(
       :raise .SecurityError: If the host is not trusted.
   
       .. versionchanged:: 3.2
  -        The characters of the host value are validated. The empty string is no
  -        longer allowed if no header value is available.
  +        The characters of the host value are validated. If
  +        ``trusted_hosts`` is not set, the host is not validated and an
  +        empty string is allowed.
   
       .. versionchanged:: 3.2
           When using the server address, Unix sockets are ignored.
  @@ -137,6 +138,14 @@ def get_host(
       elif scheme in {"https", "wss"}:
           host = host.removesuffix(":443")
   
  +    if not trusted_hosts:
  +        # When trusted_hosts is not set, be lenient: return empty string
  +        # for empty or invalid hosts rather than failing. This matches the
  +        # behavior described in the issue.
  +        if not host_is_trusted(host, None):
  +            return ""
  +        return host
  +
       if not host_is_trusted(host, trusted_hosts):
           raise SecurityError(f"Host {host!r} is not trusted.")
   
  ```
- `PR#3132` (2026-03-22) **Fix grammar in RequestHeaderFieldsTooLarge description**
  matched: `instead of`
  > Corrected subject-verb agreement in error description ("fields exceed" instead of "fields exceeds"). <!-- Before opening a PR, open a ticket describing the issue or feature the PR will address. An issue is not required for fixing typos in documentation, or other simple non-code changes. Replace this comment with a description of the change. Describe how it addresses the linked ticket. --> <!-- Link to relevant issues or previous PRs, one per line. Use "fixes" to automatically close an issue. fixes #<issue number> --> <!-- Ensure each step in CONTRIBUTING.rst is complete, especially the following: - Add tests that demonstrate the correct behavior of the change. Tests should fail without the change. - Add or update relevant docs, in the docs folder and in code. - Add an entry in CHANGES.rst 
  Rejected code:
  ```diff
  --- src/werkzeug/exceptions.py
  @@ -718,7 +718,7 @@ class RequestHeaderFieldsTooLarge(HTTPException):
       """
   
       code = 431
  -    description = "One or more header fields exceeds the maximum size."
  +    description = "One or more header fields exceed the maximum size."
   
   
   class UnavailableForLegalReasons(HTTPException):
  ```
- `PR#3126` (2026-03-19) **fix: use greedy regex for merge_slashes to collapse all consecutive slashes**
  matched: `instead of`
  > ## Summary - Fix `Rule.compile()` to use greedy regex `/{2,}` instead of non-greedy `/{2,}?` when `merge_slashes=True` - The non-greedy quantifier only matches exactly 2 slashes, leaving paths like `///foo` partially unmerged ## Root Cause In `Rule.compile()`, the regex replacement `/{2,}?` is non-greedy, meaning it matches the minimum (2 slashes) instead of all consecutive slashes. ## Testing - Verified that `///foo///bar` correctly collapses to `/foo/bar` after the fix - Added test case for `///foo///bar///` -> `/foo/bar/` - Existing test suite passes Fixes #3121 Made with [Cursor](https://cursor.com)
  Rejected code:
  ```diff
  --- src/werkzeug/routing/rules.py
  @@ -722,7 +722,7 @@ def compile(self) -> None:
           self._trace.append((False, "|"))
           rule = self.rule
           if self.merge_slashes:
  -            rule = re.sub("/{2,}?", "/", self.rule)
  +            rule = re.sub("/{2,}", "/", self.rule)
           self._parts.extend(self._parse_rule(rule))
   
           self._build: t.Callable[..., tuple[str, str]]
  ```
- `PR#3053` (2025-07-02) **This pull request fixes a Denial of Service (DoS) vulnerability in Werkzeug's handling of HTTP requests with chunked Transfer-Encoding.**
  matched: `rejected`, `to prevent`, `tried`
  maintainer: "I truly hope you accept this patch, as it's my humble attempt to contribute to this amazing and well-crafted project. ❤️ Thank you so much for all your incredible work it's truly inspiring! I'm gratef"
  > Sorry for the confusion in the previous version of the patch. When I first tried to add the fix, I accidentally removed the original comments and forgot to include them back. That was a mistake. I have now restored all the original comments and typing annotations, and added the necessary explanations and comments related to the DoS fix. The patch is complete and correctly documented now. Thank you for your understanding and your time reviewing this ### Problem When handling chunked Transfer-Encoding requests, Werkzeug's previous `DechunkedInput` implementation did not properly enforce limits or validate the chunked data stream. This allowed malicious clients to send malformed or infinite chunked data streams that caused the server to hang or exhaust resources. Notably, the protection via `
  Rejected code:
  ```diff
  --- src/werkzeug/serving.py
  @@ -96,61 +96,70 @@ class ForkingMixIn:  # type: ignore
   class DechunkedInput(io.RawIOBase):
       """An input stream that handles Transfer-Encoding 'chunked'"""
   
  -    def __init__(self, rfile: t.IO[bytes]) -> None:
  +    def __init__(self, rfile, max_content_length=16 * 1024 * 1024):
           self._rfile = rfile
           self._done = False
           self._len = 0
  +        self._total_read = 0
  +        self._max_total_read = max_content_length
   
  -    def readable(self) -> bool:
  +    def readable(self):
           return True
   
  -    def read_chunk_len(self) -> int:
  +    def read_chunk_len(self):
  +        # Read the length of the next chunk from the input stream
  +        line = self._rfile.readline().decode("latin1")
  +        if not line.strip():
  +            # Empty line is invalid chunk header
  +            raise OSError("Empty chunk header line received")
           try:
  -            line = self._rfile.readline().decode("latin1")
               _len = int(line.strip(), 16)
  -        except ValueError as e:
  -            raise OSError("Invalid chunk header") from e
  +        except ValueError as err:
  +            # Invalid chunk length header, raise with original error context
  +            raise OSError("Invalid chunk header") from err
           if _len < 0:
               raise OSError("Negative chunk length not allowed")
           return _len
   
  -    def readinto(self, buf: bytearray) -> int:  # type: ignore
  +    def readinto(self, buf):
  +        if self._done:
  +
  ```

## Incidents (revert/rollback signals)

- `PR#3203` (2026-07-05) **AI junk**
  matched: `regression`
  > Fixes #3189 ## Summary - Preserve empty-but-present usernames and passwords when rebuilding URLs in `uri_to_iri` and `iri_to_uri`. - Add regression tests for empty username, empty password, empty username with password, and empty username with empty password. - Add a changelog entry for the fix. ## Root cause `urlsplit` represents missing userinfo as `None`, but present empty userinfo as an empty string. The URL conversion helpers used truthiness checks, so empty-but-present components were treated as missing and dropped from the rebuilt netloc. ## Checks - `.venv/bin/python -m pytest tests/test_urls.py -q` - `.venv/bin/python -m ruff check src/werkzeug/urls.py tests/test_urls.py` - `.venv/bin/python -m ruff format --check src/werkzeug/urls.py tests/test_urls.py` - `.venv/bin/python -m myp
  Rejected code:
  ```diff
  --- CHANGES.rst
  @@ -91,6 +91,8 @@ Version 3.2.0
       ETag will be different. :pr:`3164`
   -   ``generate_password_hash`` uses ``secrets.token_urlsafe`` to generate salt.
       The private ``gen_salt`` method is removed. :pr:`3167`
  +-   ``uri_to_iri`` and ``iri_to_uri`` preserve empty usernames and passwords in
  +    URL userinfo. :issue:`3189`
   
   
   Version 3.1.8
  --- src/werkzeug/urls.py
  @@ -98,10 +98,10 @@ def uri_to_iri(uri: str) -> str:
       if parts.port:
           netloc = f"{netloc}:{parts.port}"
   
  -    if parts.username:
  +    if parts.username is not None:
           auth = _unquote_user(parts.username)
   
  -        if parts.password:
  +        if parts.password is not None:
               password = _unquote_user(parts.password)
               auth = f"{auth}:{password}"
   
  @@ -153,10 +153,10 @@ def iri_to_uri(iri: str) -> str:
       if parts.port:
           netloc = f"{netloc}:{parts.port}"
   
  -    if parts.username:
  +    if parts.username is not None:
           auth = quote(parts.username, safe="%!$&'()*+,;=")
   
  -        if parts.password:
  +        if parts.password is not None:
               password = quote(parts.password, safe="%!$&'()*+,;=")
               auth = f"{auth}:{password}"
   
  ```
- `PR#3196` (2026-06-28) **AI junk**
  matched: `regression`
  > `uri_to_iri()` and `iri_to_uri()` rebuild the userinfo part of a URL using a truthiness check on the username and password. `urllib.parse.urlsplit` distinguishes a present-but-empty component (`""`) from a missing one (`None`), but because an empty string is falsy, an empty-but-present username or password was silently dropped. The most severe case is a non-empty password being dropped entirely when the username is empty, which is data loss during what should be a lossless normalization: ```pycon >>> from werkzeug.urls import uri_to_iri >>> uri_to_iri("http://:pass@example.com/path") 'http://example.com/path' # before: password silently dropped 'http://:pass@example.com/path' # after >>> uri_to_iri("http://user:@example.com/path") 'http://user@example.com/path' # before: empty password sep
  Rejected code:
  ```diff
  --- CHANGES.rst
  @@ -91,6 +91,9 @@ Version 3.2.0
       ETag will be different. :pr:`3164`
   -   ``generate_password_hash`` uses ``secrets.token_urlsafe`` to generate salt.
       The private ``gen_salt`` method is removed. :pr:`3167`
  +-   ``uri_to_iri`` and ``iri_to_uri`` keep an empty but present username or
  +    password rather than dropping it. Only a missing component is omitted.
  +    :issue:`3189`
   
   
   Version 3.1.8
  --- src/werkzeug/urls.py
  @@ -68,6 +68,10 @@ def uri_to_iri(uri: str) -> str:
   
       :param uri: The URI to convert.
   
  +    .. versionchanged:: 3.2
  +        An empty but present username or password is preserved. Only a
  +        missing component is omitted.
  +
       .. versionchanged:: 3.0
           Passing a tuple or bytes, and the ``charset`` and ``errors`` parameters,
           are removed.
  @@ -98,10 +102,10 @@ def uri_to_iri(uri: str) -> str:
       if parts.port:
           netloc = f"{netloc}:{parts.port}"
   
  -    if parts.username:
  +    if parts.username is not None:
           auth = _unquote_user(parts.username)
   
  -        if parts.password:
  +        if parts.password is not None:
               password = _unquote_user(parts.password)
               auth = f"{auth}:{password}"
   
  @@ -119,6 +123,10 @@ def iri_to_uri(iri: str) -> str:
   
       :param iri: The IRI to convert.
   
  +    .. versionchanged:: 3.2
  +        An empty but present username or password is preserved. Only a
  +        missing component is omitted.
  +
       .. versionchanged:: 3.0
           Passing a tuple or b
  ```
- `PR#3195` (2026-06-24) **AI spam**
  matched: `regression`
  > `uri_to_iri()` and `iri_to_uri()` currently check `SplitResult.username` and `.password` by truthiness when reconstructing userinfo. `urlsplit()` uses `None` for a missing component and `""` for a present-but-empty component, so empty usernames or passwords are dropped. This changes those checks to `is not None`, preserving empty userinfo components while still omitting missing ones. It also adds regression coverage for empty username, empty password, and empty userinfo round-trips. fixes #3189 Tests: - `python -m pytest tests\\test_urls.py -q` - `python -m ruff check src\\werkzeug\\urls.py tests\\test_urls.py` - `python -m ruff format --check src\\werkzeug\\urls.py tests\\test_urls.py` - `python -m mypy src\\werkzeug\\urls.py` - `git diff --check`
  Rejected code:
  ```diff
  --- CHANGES.rst
  @@ -71,6 +71,8 @@ Version 3.2.0
       :pr:`3101`
   -   Raise a ``DuplicateRuleError`` when attempting to add a rule to a map with
       an equal rule. :issue:`3037`
  +-   ``uri_to_iri`` and ``iri_to_uri`` preserve empty usernames and passwords in
  +    URLs. :issue:`3189`
   -   Add ``Request.sec_fetch_site``, ``sec_fetch_mode``, ``sec_fetch_user``, and
       ``sec_fetch_dest`` header properties. :pr:`3082`
   -   ``Response.make_conditional`` sets the ``Accept-Ranges`` header even if it
  --- src/werkzeug/urls.py
  @@ -98,10 +98,10 @@ def uri_to_iri(uri: str) -> str:
       if parts.port:
           netloc = f"{netloc}:{parts.port}"
   
  -    if parts.username:
  +    if parts.username is not None:
           auth = _unquote_user(parts.username)
   
  -        if parts.password:
  +        if parts.password is not None:
               password = _unquote_user(parts.password)
               auth = f"{auth}:{password}"
   
  @@ -153,10 +153,10 @@ def iri_to_uri(iri: str) -> str:
       if parts.port:
           netloc = f"{netloc}:{parts.port}"
   
  -    if parts.username:
  +    if parts.username is not None:
           auth = quote(parts.username, safe="%!$&'()*+,;=")
   
  -        if parts.password:
  +        if parts.password is not None:
               password = quote(parts.password, safe="%!$&'()*+,;=")
               auth = f"{auth}:{password}"
   
  ```
- `PR#3183` (2026-06-11) **AI spam**
  matched: `regression`
  > `ContentRange.set()` is a public method (also called from `ContentRange.__init__`) that validates a user-supplied byte range with a bare `assert`: ```python def set(self, start, stop, length=None, units="bytes"): """Simple method to update the ranges.""" assert is_byte_range_valid(start, stop, length), "Bad range provided" ``` Two problems: `assert` is stripped under `python -O`, so an invalid range is accepted silently in optimized builds; and when it does fire it raises `AssertionError`, while the sibling `Range` class raises `ValueError` (and documents it) for the same kind of invalid range. ```python ContentRange("bytes", 100, 50, 200) # start > stop: AssertionError, or silently accepted under -O Range("bytes", [(100, 50)]) # raises ValueError, as documented ``` This raises `ValueError
  Rejected code:
  ```diff
  --- CHANGES.rst
  @@ -3,6 +3,8 @@
   Version 3.2.0
   -------------
   
  +-   ``ContentRange.set`` raises ``ValueError`` instead of using ``assert`` for an
  +    invalid range, so validation is not skipped under ``python -O``. :pr:`3183`
   -   Drop support for Python 3.9. :pr:`3098`
   -   Remove previous deprecated code: :pr:`3099`
   
  --- src/werkzeug/datastructures/range.py
  @@ -268,7 +268,8 @@ def set(
           units: str | None = "bytes",
       ) -> None:
           """Simple method to update the ranges."""
  -        assert is_byte_range_valid(start, stop, length), "Bad range provided"
  +        if not is_byte_range_valid(start, stop, length):
  +            raise ValueError("Bad range provided")
           self._units: str | None = units
           self._start: int | None = start
           self._stop: int | None = stop
  ```
- `PR#3182` (2026-06-11) **AI spam**
  matched: `instead of`, `regression`
  > `parse_options_header` parses a header value with `key=value` parameters (e.g. `Content-Type`, `Content-Disposition`). It currently runs in quadratic time, `O(n**2)`, in the number/size of parameters, for two reasons: 1. The parameter-collection loop slices the remaining string from the front on every parameter (`rest = rest[m.end():]` and `rest = rest[end + 1:].lstrip()`). Each slice copies all remaining characters, so `n` parameters cost `n + (n-1) + ... = O(n**2)`. 2. RFC 2231 continuation handling rebuilds the value with `options[pk] = options.get(pk, "") + pv` on each part. Since `key*0`, `key*1`, ... collapse to the same key, this concatenates a growing string, also `O(n**2)` in the combined value length. This makes parsing a large `Content-Type`/`Content-Disposition` value dispropor
  Rejected code:
  ```diff
  --- src/werkzeug/http.py
  @@ -617,43 +617,60 @@ def parse_options_header(value: str | None) -> tuple[str, dict[str, str]]:
           # empty (invalid) value, or value without options
           return value, {}
   
  -    # Collect all valid key=value parts without processing the value.
  +    # Collect all valid key=value parts without processing the value. Scan with a
  +    # moving index rather than slicing `rest` from the front on every parameter:
  +    # each such slice copies all remaining characters, making parsing O(n**2) in
  +    # the number of parameters.
       parts: list[tuple[str, str]] = []
  +    pos = 0
  +    length = len(rest)
   
  -    while True:
  -        if (m := _parameter_key_re.match(rest)) is not None:
  +    while pos < length:
  +        # The search for the next `;` starts from the current position, unless a
  +        # key=value part is consumed below, in which case it resumes after the
  +        # consumed value.
  +        search_from = pos
  +
  +        if (m := _parameter_key_re.match(rest, pos)) is not None:
               pk = m.group(1).lower()
  -            rest = rest[m.end() :]
  +            value_start = m.end()
  +            search_from = value_start
   
               # Value may be a token.
  -            if (m := _parameter_token_value_re.match(rest)) is not None:
  +            if (m := _parameter_token_value_re.match(rest, value_start)) is not None:
                   parts.append((pk, m.group()))
   
               # Value may be a quoted string, find the closing quote.
  -       
  ```
- `PR#3181` (2026-06-08) **Fix routing priority across same-weight converters**
  matched: `regression`
  > Fixes #3156 ## Summary - Preserve routing priority when unrelated non-matching rules share dynamic prefixes. - Add regression coverage for same-weight converters and cross-converter specificity. ## Tests - Reproduced before the fix with `PYTHONPATH=src .venv/bin/python -m pytest tests/test_routing.py -q -k 'consistent_relative_priority or cross_converter_rule_specificity'`: 2 failed. - After the fix: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_routing.py -q`: 150 passed in 0.93s. ## Risk Medium. This touches route matching priority behavior, so the patch is intentionally scoped to the smallest matcher change needed for the regression. ## AI assistance disclosure This PR was prepared with AI assistance and manually checked before submission.
  Rejected code:
  ```diff
  --- src/werkzeug/routing/matcher.py
  @@ -34,6 +34,7 @@ class State:
   class StateMachineMatcher:
       def __init__(self, merge_slashes: bool) -> None:
           self._root = State()
  +        self._rule_order: dict[int, int] = {}
           self.merge_slashes = merge_slashes
   
       def add(self, rule: Rule) -> None:
  @@ -56,6 +57,7 @@ def add(self, rule: Rule) -> None:
               if rule.is_duplicate(existing):
                   raise DuplicateRuleError(existing, rule)
   
  +        self._rule_order[id(rule)] = len(self._rule_order)
           state.rules.append(rule)
   
       def update(self) -> None:
  @@ -84,7 +86,7 @@ def match(
   
           def _match(
               state: State, parts: list[str], values: list[str]
  -        ) -> tuple[Rule, list[str]] | None:
  +        ) -> tuple[Rule, list[str], list[tuple[t.Any, ...]]] | None:
               # This function is meant to be called recursively, and will attempt
               # to match the head part to the state's transitions.
               nonlocal have_match_for, websocket_mismatch
  @@ -100,7 +102,7 @@ def _match(
                       elif rule.websocket != websocket:
                           websocket_mismatch = True
                       else:
  -                        return rule, values
  +                        return rule, values, [(2, self._rule_order[id(rule)])]
   
                   # Test if there is a match with this path with a
                   # trailing slash, if so raise an exception to report
  @@ -113,18 +115,34 @@ def _match(
         
  ```
- `PR#3180` (2026-06-06) **AI spam**
  matched: `regression`
  > Fixes #3156.\n\n## Summary\n- only merge a dynamic matcher state with the immediately previous equivalent dynamic part\n- preserve relative rule priority when an earlier unrelated dynamic route shares the same converter as a later route\n- add a regression test for unmatched dynamic rules affecting priority\n\n## Tests\n- RED: . [100%] 1 passed in 1.88s failed before the matcher change\n- GREEN: . [100%] 1 passed in 1.20s\n- ........................................................................ [ 48%] ........................................................................ [ 96%] ..... [100%] 149 passed in 1.96s\n- All checks passed!\n-
  Rejected code:
  ```diff
  --- src/werkzeug/routing/matcher.py
  @@ -43,10 +43,8 @@ def add(self, rule: Rule) -> None:
                   state.static.setdefault(part.content, State())
                   state = state.static[part.content]
               else:
  -                for test_part, new_state in state.dynamic:
  -                    if test_part == part:
  -                        state = new_state
  -                        break
  +                if state.dynamic and state.dynamic[-1][0] == part:
  +                    state = state.dynamic[-1][1]
                   else:
                       new_state = State()
                       state.dynamic.append((part, new_state))
  ```
- `PR#3175` (2026-05-25) **AI junk**
  matched: `regression`
  > Fixes #3156. ## Summary - evaluate dynamic transitions with equal converter weight as a priority group before choosing a match - preserve static specificity and original rule order when equal-weight converters can both match - add regression coverage for unrelated routes changing priority and cross-converter specificity ## Tests - `python -m pytest tests/test_routing.py -q` - `python -m ruff check src\werkzeug\routing\matcher.py tests\test_routing.py` - `python -m ruff format --check src\werkzeug\routing\matcher.py tests\test_routing.py` - `python -m compileall -q src\werkzeug\routing\matcher.py tests\test_routing.py`
  Rejected code:
  ```diff
  --- src/werkzeug/routing/matcher.py
  @@ -15,7 +15,8 @@
   
   
   class SlashRequired(Exception):
  -    pass
  +    def __init__(self, priority: tuple[tuple[t.Any, ...], ...]) -> None:
  +        self.priority = priority
   
   
   @dataclass
  @@ -31,9 +32,17 @@ class State:
       static: dict[str, State] = field(default_factory=dict)
   
   
  +@dataclass
  +class StateMatch:
  +    rule: Rule
  +    values: list[str]
  +    priority: tuple[tuple[t.Any, ...], ...]
  +
  +
   class StateMachineMatcher:
       def __init__(self, merge_slashes: bool) -> None:
           self._root = State()
  +        self._rule_order: dict[int, int] = {}
           self.merge_slashes = merge_slashes
   
       def add(self, rule: Rule) -> None:
  @@ -56,6 +65,7 @@ def add(self, rule: Rule) -> None:
               if rule.is_duplicate(existing):
                   raise DuplicateRuleError(existing, rule)
   
  +        self._rule_order[id(rule)] = len(self._rule_order)
           state.rules.append(rule)
   
       def update(self) -> None:
  @@ -84,7 +94,7 @@ def match(
   
           def _match(
               state: State, parts: list[str], values: list[str]
  -        ) -> tuple[Rule, list[str]] | None:
  +        ) -> StateMatch | None:
               # This function is meant to be called recursively, and will attempt
               # to match the head part to the state's transitions.
               nonlocal have_match_for, websocket_mismatch
  @@ -100,7 +110,9 @@ def _match(
                       elif rule.websocket != websocket:
                           websocket_mismatch = 
  ```
- `PR#3174` (2026-05-23) **AI junk**
  matched: `regression`
  > #### Description of changes My pull request improves 'safe_join' posture by blocking Windows 'nt' system' raletive paths. The changes prevent relative path segments that contain colons (`:`) on utilization of directory traversal elements (`..`), delimiters of various paths (`/`), and trailing termination stream. #### Motive of changes Even though `safe_join` prevents unexpected interaction of relative drive/path letters such as (`C:../filename`), or Windows NTFS ADS streams such as (`filename.txt:stream`), the adjustment enhance proper validation on Windows systems and POSIX platform's environment without affecting path segements. #### Testing changes - Added Windows platform regression assertion tests. - Ensured all existing test cases in `test_security.py` run successfully.
  Rejected code:
  ```diff
  --- src/werkzeug/security.py
  @@ -179,6 +179,13 @@ def safe_join(directory: str, *untrusted: str) -> str | None:
               or part.startswith("/")
               or part == ".."
               or part.startswith("../")
  +            # HARDENING: Catch ADS, relative path/drive anomalies
  +            # example: "C:../secrets.txt" on windows operating systems
  +            or (
  +                os.name == "nt"
  +                and ":" in part
  +                and (".." in part or "/" in part or part.endswith(":"))
  +            )
               or any(sep in part for sep in _os_alt_seps)
               or (
                   os.name == "nt"
  ```
- `PR#3172` (2026-05-19) **fix(routing): stable sort by insertion index when dynamic rule weights tie**
  matched: `regression`
  > Fixes #3156. ## Summary When two dynamic converter parts have the same weight (e.g. a custom converter subclassing `BaseConverter` at weight=100 vs the built-in `string` converter also at weight=100), `StateMachineMatcher.update()` sorts `state.dynamic` by weight alone. Because Python's sort is stable, the result preserves `state.dynamic` insertion order — but that order reflects which rule **first created** a path transition, not which rule was **registered first**. An unrelated rule that merely *shares* a dynamic prefix (e.g. `/<string:value>/no_match`) can create the `string` transition before `/<dummy:value>` is registered, placing `string` ahead of `dummy` in `state.dynamic`. A later `/<string:value>` rule then reuses that same transition, meaning the order of two competing rules (`/<
  Rejected code:
  ```diff
  --- src/werkzeug/routing/matcher.py
  @@ -35,9 +35,12 @@ class StateMachineMatcher:
       def __init__(self, merge_slashes: bool) -> None:
           self._root = State()
           self.merge_slashes = merge_slashes
  +        self._rule_count = 0
   
       def add(self, rule: Rule) -> None:
           state = self._root
  +        rule._insertion_index = self._rule_count
  +        self._rule_count += 1
           for part in rule._parts:
               if part.static:
                   state.static.setdefault(part.content, State())
  @@ -60,11 +63,30 @@ def add(self, rule: Rule) -> None:
   
       def update(self) -> None:
           # For every state the dynamic transitions should be sorted by
  -        # the weight of the transition
  +        # the weight of the transition, then by the minimum insertion
  +        # index of any rule that terminates directly at the destination
  +        # state.  Using only the direct rules (state.rules) rather than
  +        # the full subtree prevents unrelated rules that merely share a
  +        # dynamic path prefix from inflating a branch's apparent priority.
  +        # When no rule terminates at a state (e.g. an intermediate state
  +        # on a longer path), the sentinel self._rule_count causes that
  +        # transition to sort after all rule-terminating transitions with
  +        # the same weight, preserving stable insertion order between them.
           state = self._root
   
           def _update_state(state: State) -> None:
  -            state.dynamic.sort(key=lambd
  ```
- `PR#3125` (2026-03-12) **fix: use greedy quantifier for merge_slashes regex**
  matched: `instead of`, `regression`
  > ## Summary - Changes `/{2,}?` (non-greedy) to `/{2,}` (greedy) in both `rules.py` and `matcher.py` - The non-greedy quantifier matches exactly 2 slashes, so `///path` becomes `//path` instead of `/path` - Added parametrized regression test covering double, triple, and quadruple consecutive slashes for both matching and building Closes #3121 ## Test plan
  Rejected code:
  ```diff
  --- src/werkzeug/routing/matcher.py
  @@ -178,7 +178,7 @@ def _match(
   
           if self.merge_slashes and rv is None:
               # Try to match again, but with slashes merged
  -            path = re.sub("/{2,}?", "/", path)
  +            path = re.sub("/{2,}", "/", path)
               try:
                   rv = _match(self._root, [domain, *path.split("/")], [])
               except SlashRequired:
  --- src/werkzeug/routing/rules.py
  @@ -722,7 +722,7 @@ def compile(self) -> None:
           self._trace.append((False, "|"))
           rule = self.rule
           if self.merge_slashes:
  -            rule = re.sub("/{2,}?", "/", self.rule)
  +            rule = re.sub("/{2,}", "/", self.rule)
           self._parts.extend(self._parse_rule(rule))
   
           self._build: t.Callable[..., tuple[str, str]]
  ```
