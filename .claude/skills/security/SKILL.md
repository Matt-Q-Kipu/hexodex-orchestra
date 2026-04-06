---
name: security
description: Scan a repository for security vulnerabilities — SSRF, injection (SQL, command, query-language), path traversal, unsafe deserialization, secret exposure, GitHub Actions injection, and missing rate-limit handling. Uses grep patterns plus contextual code reading to reduce false positives.
---

Scan the repository for security vulnerabilities. Use Grep and Read tools to inspect code — do not execute the code under review.

## How It Works

This skill applies **pattern-then-context** analysis:

1. **Pattern**: Grep for code shapes associated with each vulnerability class
2. **Context**: Read 10-15 surrounding lines to determine if the match is actually exploitable
3. **Report**: Group findings by severity with concrete, fix-ready recommendations

This approach leverages Claude's ability to understand code semantics — distinguishing a hardcoded URL (safe) from a user-interpolated one (vulnerable) in a way that pure regex-based SAST tools cannot.

## Vulnerability Classes

Scan for each class below. For every finding, report: file path, line number(s), the vulnerable pattern, what an attacker could do, and severity (critical / high / medium / low).

### 1. SSRF (Server-Side Request Forgery)

User-controlled input used to construct URLs for HTTP requests.

**Grep patterns:**
- Python: `requests.get(`, `requests.post(`, `urllib.request.urlopen(`, `httpx.`
- JavaScript/TypeScript: `fetch(`, `axios(`, `axios.get(`, `http.get(`, `got(`
- Ruby: `Net::HTTP`, `open-uri`, `Faraday`
- Go: `http.Get(`, `http.Post(`

**What to check:** Is the URL or any part of it (host, path, query) derived from user input (CLI args, query params, request body, file contents)? Is the host validated against an allowlist?

**Fix pattern:** Construct URLs from a hardcoded base URL + validated path component. Reject requests where the resolved host is not on an explicit allowlist.

```python
# Vulnerable
url = f"https://{user_input}/api/data"
requests.get(url)

# Fixed
ALLOWED_HOSTS = {"api.example.com", "internal.example.com"}
parsed = urllib.parse.urlparse(f"https://{user_input}/api/data")
if parsed.hostname not in ALLOWED_HOSTS:
    raise ValueError(f"Host not allowed: {parsed.hostname}")
requests.get(parsed.geturl())
```

### 2. Injection — Query Language (SQL, JQL, GraphQL, LDAP, etc.)

User-controlled input interpolated into query strings without escaping or parameterization.

**Grep patterns:**
- SQL: `execute(.*f"`, `execute(.*f'`, `.format(` near `SELECT|INSERT|UPDATE|DELETE`
- JQL (Jira): `f'.*jql`, `f".*jql`, f-strings containing `=` combined with `jql`
- GraphQL: `f'.*query`, `f".*mutation` with variable interpolation
- LDAP: `f'.*filter`, string concatenation near `ldap.search`

**What to check:** Is the query parameterized (safe) or string-interpolated with user input (unsafe)?

**Fix pattern:** Always use parameterized queries or language-specific escaping functions.

```python
# Vulnerable — SQL
cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")

# Fixed — parameterized
cursor.execute("SELECT * FROM users WHERE name = %s", (user_input,))

# Vulnerable — JQL
jql = f'project = EMR AND assignee = "{username}"'

# Fixed — escaped
from some_helper import escape_jql_value
jql = f'project = EMR AND assignee = "{escape_jql_value(username)}"'
```

### 3. Injection — Command

User input flowing into shell execution.

**Grep patterns:**
- Python: `subprocess.run(.*shell=True`, `subprocess.call(.*shell=True`, `os.system(`, `os.popen(`, `exec(`, `eval(`
- JavaScript: `child_process.exec(`, `execSync(`
- Ruby: backticks, `system(`, `%x(`

**What to check:** Does user input reach the command string? Are arguments passed as a list (safe) or concatenated into a string (unsafe)?

**Fix pattern:** Use list-form subprocess calls. Never pass user input through a shell.

```python
# Vulnerable
subprocess.run(f"grep {user_input} /var/log/app.log", shell=True)

# Fixed
subprocess.run(["grep", user_input, "/var/log/app.log"])
```

### 4. Path Traversal

User input used to construct file paths without sanitization.

**Grep patterns:**
- Python: `open(.*+`, `os.path.join(.*input`, `Path(` combined with user input, `send_file(`
- JavaScript: `fs.readFile(`, `res.sendFile(`, `path.join(` with user input
- Go: `os.Open(`, `filepath.Join(` with user input

**What to check:** Can `../` sequences escape the intended directory? Is the resolved path validated against an allowed root?

**Fix pattern:** Resolve the full path, then verify it starts with the intended root directory.

```python
# Vulnerable
path = os.path.join(UPLOAD_DIR, user_filename)
return open(path).read()

# Fixed
path = os.path.realpath(os.path.join(UPLOAD_DIR, user_filename))
if not path.startswith(os.path.realpath(UPLOAD_DIR)):
    raise ValueError("Path traversal detected")
return open(path).read()
```

### 5. Unsafe Deserialization

Deserializing untrusted data with dangerous loaders.

**Grep patterns:**
- Python: `pickle.load`, `pickle.loads`, `yaml.load(` (without `Loader=SafeLoader`), `marshal.load`, `shelve.open`
- JavaScript: `eval(.*JSON`, `serialize-javascript`, `node-serialize`
- Ruby: `Marshal.load`, `YAML.load` (without `safe_load`)
- Java: `ObjectInputStream`, `readObject()`

**What to check:** Is the data source trusted (local config committed to repo) or untrusted (user upload, network response, message queue)?

**Fix pattern:** Use safe loaders. For YAML, always specify `Loader=yaml.SafeLoader`. Avoid pickle for any data that crosses a trust boundary.

### 6. Secret Exposure

Credentials hardcoded in source files.

**Grep patterns:** `password\s*=\s*["']`, `token\s*=\s*["']`, `secret\s*=\s*["']`, `api_key\s*=\s*["']`, `AWS_SECRET`, `PRIVATE.KEY`

**What to check:** Is the value loaded from environment variables or a secrets manager (safe) or hardcoded as a literal string (unsafe)?

**Exclude from findings:** `.env` files (they *should* hold secrets — just verify `.env` is in `.gitignore`), `*.example` files, documentation comments, test fixtures with dummy values.

**Fix pattern:** Load credentials from environment variables or a secrets manager. Never commit real credentials.

```python
# Vulnerable
API_KEY = "sk-live-abc123..."

# Fixed
API_KEY = os.environ["API_KEY"]
```

### 7. GitHub Actions Script Injection

Untrusted GitHub Actions context values interpolated into `run:` blocks.

**Grep patterns (in `.github/**/*.yml`):** `\$\{\{ github.event` inside `run:` steps

**Attacker-controlled fields:**
- `github.event.pull_request.title`
- `github.event.pull_request.body`
- `github.event.issue.title`
- `github.event.issue.body`
- `github.event.comment.body`
- `github.event.review.body`
- `github.event.head_commit.message`

**Safe contexts:** Using these expressions in `if:` conditionals or `with:` inputs (passed as environment variables) is not injectable.

**Fix pattern:** Pass event data through environment variables instead of inline interpolation.

```yaml
# Vulnerable
- run: echo "PR title: ${{ github.event.pull_request.title }}"

# Fixed
- run: echo "PR title: $PR_TITLE"
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
```

### 8. Missing Rate-Limit Handling

HTTP request loops or API calls that lack 429 retry/backoff logic, risking cascading failures and upstream throttling.

**Grep patterns:** Same HTTP client patterns as SSRF (class 1) — then check whether the call site has retry/backoff logic nearby.

**What to check:**
- Does the function handle HTTP 429 responses with retry + backoff, or just crash / `raise_for_status()`?
- Is the call inside a pagination loop or bulk-fetch without inter-request delays?
- Is it invoked from a web server (higher concurrency risk) vs. a one-shot CLI script (lower risk)?

**Severity guide:**
- **Medium**: Web server code making multiple API calls per request with no 429 handling — concurrent users can stack requests and trigger upstream throttling
- **Low**: CLI scripts making single-shot requests that crash on 429 but can't amplify load

**Fix pattern:** Implement exponential backoff with jitter on 429 and 5xx responses.

```python
# Reference pattern
import time, random

def request_with_backoff(url, max_retries=5):
    for attempt in range(max_retries + 1):
        resp = requests.get(url)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise Exception(f"Failed after {max_retries} retries")
```

## Extending With Custom Classes

To add a vulnerability class for your codebase, follow this pattern:

```markdown
### N. Class Name
One-line description of the vulnerability.

**Grep patterns:** `pattern1`, `pattern2`
**What to check:** How to distinguish true positives from false positives.
**Fix pattern:** How to remediate, with a code example.
```

Good candidates for custom classes: framework-specific issues (e.g., Django `mark_safe()`, React `dangerouslySetInnerHTML`), domain-specific query languages, or org-specific API patterns.

## Scan Procedure

1. For each vulnerability class, run the grep patterns across relevant file types:
   - Python: `**/*.py`
   - JavaScript/TypeScript: `**/*.js`, `**/*.ts`, `**/*.jsx`, `**/*.tsx`
   - Ruby: `**/*.rb`
   - Go: `**/*.go`
   - Workflows: `.github/**/*.yml`
2. Exclude: `node_modules/`, `.venv/`, `vendor/`, `__pycache__/`, `dist/`, `build/`, and test fixture directories.
3. For each match, read 10-15 surrounding lines to determine if the input is actually user-controlled.
4. Cross-reference against existing safe patterns already in the repo (look for helper functions, middleware, or wrappers that may already handle the vulnerability).
5. Report findings grouped by severity, then by vulnerability class.

## Output Format

If findings exist:

> ### Security Scan Results
>
> **N findings** across M files
>
> | Severity | File | Line | Class | Description |
> |----------|------|------|-------|-------------|
> | HIGH | path/to/file.py | 42 | SSRF | User input in URL construction without host validation |
>
> #### Recommended Fixes
> (concrete fix for each finding, referencing the fix patterns above or existing safe helpers in the repo)

If no findings:

> Clean scan. No vulnerabilities detected across N files.
