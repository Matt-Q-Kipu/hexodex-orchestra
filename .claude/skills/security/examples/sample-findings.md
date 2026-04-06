# Example: Security Scan Findings

This is an example of what `/security` scan output looks like when vulnerabilities are found.

---

### Security Scan Results

**4 findings** across 3 files

| Severity | File | Line | Class | Description |
|----------|------|------|-------|-------------|
| HIGH | api/handlers/proxy.py | 23 | SSRF | User-supplied `target_url` query param passed directly to `requests.get()` without host validation |
| HIGH | api/handlers/search.py | 47 | Query Injection | f-string interpolation of `request.args["q"]` into SQL WHERE clause |
| MEDIUM | api/handlers/export.py | 112 | Path Traversal | `filename` from request body joined to export dir without path resolution check |
| LOW | scripts/sync_data.py | 89 | Rate Limit | Pagination loop calls `requests.get()` with no 429 handling or inter-request delay |

#### Recommended Fixes

**proxy.py:23 — SSRF**
Validate `target_url` hostname against an allowlist before making the request:
```python
ALLOWED_HOSTS = {"api.internal.example.com"}
parsed = urllib.parse.urlparse(target_url)
if parsed.hostname not in ALLOWED_HOSTS:
    return {"error": "Host not allowed"}, 403
```

**search.py:47 — Query Injection**
Use parameterized queries instead of f-string interpolation:
```python
# Before
cursor.execute(f"SELECT * FROM items WHERE name LIKE '%{query}%'")
# After
cursor.execute("SELECT * FROM items WHERE name LIKE %s", (f"%{query}%",))
```

**export.py:112 — Path Traversal**
Resolve the path and verify it stays within the export directory:
```python
resolved = os.path.realpath(os.path.join(EXPORT_DIR, filename))
if not resolved.startswith(os.path.realpath(EXPORT_DIR)):
    raise ValueError("Invalid filename")
```

**sync_data.py:89 — Rate Limit**
Low priority — CLI script, not web-facing. Consider adding backoff for robustness if this runs on a schedule.
