# Analysis Metadata

- **Session ID**: `2026-05-06_starlette`
- **Target**: https://github.com/encode/starlette
- **Model**: `claude-code-skill-mode`
- **Timestamp**: 2026-05-06T03:53:55.637950+00:00
- **Duration**: 0.0s
- **Files analyzed**: 67

## Selected Files

- `starlette/applications.py`
- `starlette/authentication.py`
- `starlette/background.py`
- `starlette/concurrency.py`
- `starlette/config.py`
- `starlette/convertors.py`
- `starlette/datastructures.py`
- `starlette/endpoints.py`
- `starlette/exceptions.py`
- `starlette/formparsers.py`
- `starlette/requests.py`
- `starlette/responses.py`
- `starlette/routing.py`
- `starlette/schemas.py`
- `starlette/staticfiles.py`
- `starlette/status.py`
- `starlette/templating.py`
- `starlette/testclient.py`
- `starlette/types.py`
- `starlette/websockets.py`
- `starlette/_exception_handler.py`
- `starlette/_utils.py`
- `starlette/__init__.py`
- `tests/conftest.py`
- `tests/test_applications.py`
- `tests/test_authentication.py`
- `tests/test_background.py`
- `tests/test_concurrency.py`
- `tests/test_config.py`
- `tests/test_convertors.py`
- `tests/test_datastructures.py`
- `tests/test_endpoints.py`
- `tests/test_exceptions.py`
- `tests/test_formparsers.py`
- `tests/test_requests.py`
- `tests/test_responses.py`
- `tests/test_routing.py`
- `tests/test_schemas.py`
- `tests/test_staticfiles.py`
- `tests/test_status.py`
- `tests/test_templates.py`
- `tests/test_testclient.py`
- `tests/test_websockets.py`
- `tests/test__utils.py`
- `tests/types.py`
- `tests/__init__.py`
- `tests/middleware/test_base.py`
- `tests/middleware/test_cors.py`
- `tests/middleware/test_errors.py`
- `tests/middleware/test_gzip.py`
- `tests/middleware/test_https_redirect.py`
- `tests/middleware/test_middleware.py`
- `tests/middleware/test_session.py`
- `tests/middleware/test_trusted_host.py`
- `tests/middleware/test_wsgi.py`
- `tests/middleware/__init__.py`
- `starlette/middleware/authentication.py`
- `starlette/middleware/base.py`
- `starlette/middleware/cors.py`
- `starlette/middleware/errors.py`
- `starlette/middleware/exceptions.py`
- `starlette/middleware/gzip.py`
- `starlette/middleware/httpsredirect.py`
- `starlette/middleware/sessions.py`
- `starlette/middleware/trustedhost.py`
- `starlette/middleware/wsgi.py`
- `starlette/middleware/__init__.py`

## Layer Distribution

```
Layer distribution:
  frontend: 0 files
  backend: 0 files
  db: 0 files
  devops: 0 files
  shared: 67 files
```

## Project Structure

```
093929dec2f16c95/
starlette/
  __init__.py
  _exception_handler.py
  _utils.py
  applications.py
  authentication.py
  background.py
  concurrency.py
  config.py
  convertors.py
  datastructures.py
  endpoints.py
  exceptions.py
  formparsers.py
  middleware/
    __init__.py
    authentication.py
    base.py
    cors.py
    errors.py
    exceptions.py
    gzip.py
    httpsredirect.py
    sessions.py
    trustedhost.py
    wsgi.py
  requests.py
  responses.py
  routing.py
  schemas.py
  staticfiles.py
  status.py
  templating.py
  testclient.py
  types.py
  websockets.py
tests/
  __init__.py
  conftest.py
  middleware/
    __init__.py
    test_base.py
    test_cors.py
    test_errors.py
    test_gzip.py
    test_https_redirect.py
    test_middleware.py
    test_session.py
    test_trusted_host.py
    test_wsgi.py
  test__utils.py
  test_applications.py
  test_authentication.py
  test_background.py
  test_concurrency.py
  test_config.py
  test_convertors.py
  test_datastructures.py
  test_endpoints.py
  test_exceptions.py
  test_formparsers.py
  test_requests.py
  test_responses.py
  test_routing.py
  test_schemas.py
  test_staticfiles.py
  test_status.py
  test_templates.py
  test_testclient.py
  test_websockets.py
  types.py
```

## Category Results

- **architecture**: 4 rules ✅
- **coding_style**: 4 rules ✅
- **api_design**: 4 rules ✅
- **testing**: 4 rules ✅

## Scope Distribution

- **cross_project**: 16 (100%)
- **framework_internal**: 0 (0%)
- **domain_specific**: 0 (0%)

## Evidence Coverage

How many rules cite real artifacts (commit SHA / PR# / quoted revert / ADR)
versus generic justifications. Higher cited-ratio = less LLM opinion.
Fake citations are commit SHAs the LLM invented — they were not in the input.

- **Cited**: 6 (37%)
- **No-evidence (flagged)**: 10 (62%)
- **Fake citation (hallucinated SHA)**: 0 (0%)
- **Generic justification**: 0 (0%)
- **Other (uncited)**: 0 (0%)
- **Total rules**: 16

### By Category

| Category | Cited | No-evidence | Fake | Generic | Other | Total | Cited % |
|---|---:|---:|---:|---:|---:|---:|---:|
| architecture | 3 | 1 | 0 | 0 | 0 | 4 | 75% |
| coding_style | 1 | 3 | 0 | 0 | 0 | 4 | 25% |
| api_design | 0 | 4 | 0 | 0 | 0 | 4 | 0% |
| testing | 2 | 2 | 0 | 0 | 0 | 4 | 50% |