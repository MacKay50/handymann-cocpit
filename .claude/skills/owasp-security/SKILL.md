---
name: owasp-security
description: >
  Python security skill covering OWASP Top 10, vulnerability code review, and secure code generation.
  Use this skill whenever the user: (1) asks for a security review or audit of Python code,
  (2) writes or generates Python code that handles authentication, user input, database queries,
  file uploads, sessions, passwords, tokens, HTTP requests, or environment variables,
  (3) asks about secure coding practices or how to fix a vulnerability,
  (4) mentions any OWASP category, CVE, injection, XSS, CSRF, SQLi, auth bypass, or similar.
  Trigger even if the user doesn't explicitly say "security" — if the code touches sensitive
  surfaces (auth, DB, input, crypto, sessions, file I/O, APIs), apply this skill proactively.
---

# OWASP Security Skill for Python

## Core Philosophy

Security is not optional. When generating or reviewing Python code, always:
- Default to the most secure option, not the simplest
- Flag vulnerabilities clearly with severity (Critical / High / Medium / Low)
- Provide a fixed version of any vulnerable code — never just describe the problem
- Add a short explanation of *why* the fix works

---

## Automatic Trigger Surfaces

Apply this skill **without being asked** when code involves:

| Surface | Examples |
|---|---|
| Authentication | login, JWT, sessions, OAuth, API keys |
| User input | forms, query params, CLI args, file uploads |
| Database | SQL queries, ORM raw(), execute() |
| Cryptography | passwords, hashing, encryption, secrets |
| File I/O | open(), os.path, shutil, file uploads |
| HTTP/External | requests, urllib, subprocess, eval/exec |
| Config/Env | os.environ, dotenv, settings files |

---

## OWASP Top 10 — Python Cheat Sheet

### A01 – Broken Access Control
**Signs:** Missing authorization checks, IDOR, privilege escalation.
```python
# ❌ Vulnerable
def get_document(doc_id):
    return db.query(f"SELECT * FROM docs WHERE id={doc_id}")

# ✅ Secure
def get_document(doc_id, current_user):
    doc = db.query("SELECT * FROM docs WHERE id=? AND owner_id=?",
                   doc_id, current_user.id)
    if not doc:
        raise PermissionError("Access denied")
    return doc
```

### A02 – Cryptographic Failures
**Signs:** MD5/SHA1 for passwords, hardcoded secrets, weak RNG, plaintext sensitive data.
```python
# ❌ Vulnerable
import hashlib
hashed = hashlib.md5(password.encode()).hexdigest()

# ✅ Secure
import bcrypt
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
# Or use passlib:
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash(password)
```

### A03 – Injection
**Signs:** String formatting in SQL/shell/LDAP, eval(), exec(), subprocess with shell=True.
```python
# ❌ Vulnerable — SQL injection
cursor.execute(f"SELECT * FROM users WHERE name='{username}'")

# ❌ Vulnerable — Command injection
os.system(f"ping {user_input}")

# ✅ Secure — Parameterized queries
cursor.execute("SELECT * FROM users WHERE name=?", (username,))

# ✅ Secure — Safe subprocess
import subprocess
subprocess.run(["ping", "-c", "1", host], check=True)
```

### A04 – Insecure Design
**Signs:** No rate limiting, no input length limits, predictable IDs, missing security controls by design.
```python
# ✅ Secure — Rate limiting with Flask-Limiter
from flask_limiter import Limiter
limiter = Limiter(app, default_limits=["100 per hour"])

@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login(): ...
```

### A05 – Security Misconfiguration
**Signs:** Debug mode in production, verbose error messages, default credentials, missing security headers.
```python
# ❌ Vulnerable
app.run(debug=True)  # Never in production!

# ✅ Secure Flask config
app.config.update(
    DEBUG=False,
    TESTING=False,
    SECRET_KEY=os.environ["SECRET_KEY"],  # From env, never hardcoded
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
```

### A06 – Vulnerable and Outdated Components
**Action:** Always check `pip audit` or `safety check`. Pin dependencies with hashes.
```bash
pip audit                    # Check for known CVEs
safety check                 # Alternative CVE scanner
pip-compile --generate-hashes requirements.in  # Pin with hashes
```

### A07 – Identification and Authentication Failures
**Signs:** Weak passwords allowed, no MFA support, insecure session tokens, no account lockout.
```python
# ✅ Secure JWT handling
import jwt
from datetime import datetime, timedelta

def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
```

### A08 – Software and Data Integrity Failures
**Signs:** Deserializing untrusted data with pickle, yaml.load(), no integrity checks on downloads.
```python
# ❌ Vulnerable — pickle from untrusted source allows RCE
data = pickle.loads(user_provided_bytes)

# ❌ Vulnerable — yaml.load() executes Python
config = yaml.load(user_input)

# ✅ Secure alternatives
import json
data = json.loads(user_provided_string)  # For data exchange

import yaml
config = yaml.safe_load(config_string)   # For YAML config
```

### A09 – Security Logging and Monitoring Failures
**Signs:** No audit logging, logging sensitive data (passwords, tokens), no alerting.
```python
# ✅ Secure logging setup
import logging
import structlog  # pip install structlog

# Never log: passwords, tokens, full credit cards, SSNs
logger = structlog.get_logger()

def login(username, password):
    logger.info("login_attempt", username=username)  # ✅ Log username
    # NEVER: logger.info("login", password=password)  ❌
    if authenticate(username, password):
        logger.info("login_success", username=username)
    else:
        logger.warning("login_failure", username=username)
```

### A10 – Server-Side Request Forgery (SSRF)
**Signs:** User-controlled URLs passed to requests.get(), urllib, or any HTTP client.
```python
# ❌ Vulnerable — SSRF allows internal network access
url = request.args.get("url")
response = requests.get(url)  # Attacker can hit http://169.254.169.254/

# ✅ Secure — Allowlist approach
from urllib.parse import urlparse

ALLOWED_HOSTS = {"api.example.com", "cdn.example.com"}

def safe_fetch(url: str) -> requests.Response:
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Host not allowed: {parsed.hostname}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP/HTTPS allowed")
    return requests.get(url, timeout=5)
```

---

## Code Review Protocol

When asked to review code for security:

1. **Scan all OWASP surfaces** — go through the 10 categories systematically
2. **Rate each finding:**
   - 🔴 **Critical** — Direct exploitation, data breach risk (SQLi, RCE, auth bypass)
   - 🟠 **High** — Significant risk but needs specific conditions
   - 🟡 **Medium** — Defense-in-depth issue or requires chaining
   - 🔵 **Low** — Best-practice deviation, low exploit potential
3. **For each finding provide:**
   - What the vulnerability is
   - Where in the code it exists (line reference)
   - A fixed code snippet
   - OWASP category reference
4. **End with a summary** — count by severity, overall risk rating

**Review output format:**
```
## Security Review

### 🔴 Critical: SQL Injection (A03)
**Location:** Line 42, `get_user()` function
**Issue:** ...
**Fix:**
[fixed code]

### Summary
| Severity | Count |
|----------|-------|
| 🔴 Critical | 1 |
| 🟠 High | 0 |
| 🟡 Medium | 2 |
| 🔵 Low | 1 |
**Overall Risk: HIGH**
```

---

## Secure Code Generation Rules

When writing new Python code, **always**:

- [ ] Use parameterized queries — never f-strings or .format() in SQL
- [ ] Hash passwords with bcrypt/argon2 — never MD5/SHA1/SHA256 alone
- [ ] Load secrets from environment — never hardcode credentials
- [ ] Validate and sanitize all user input before use
- [ ] Use `subprocess.run([...], shell=False)` — never `shell=True` with user input
- [ ] Use `yaml.safe_load()` — never `yaml.load()`
- [ ] Avoid `pickle` for untrusted data — use JSON instead
- [ ] Set timeouts on all HTTP requests
- [ ] Add authorization checks — not just authentication
- [ ] Use `secrets` module for tokens — never `random`

```python
# ✅ Secure token generation
import secrets
token = secrets.token_urlsafe(32)  # Cryptographically secure

# ❌ Insecure
import random
token = str(random.random())  # Predictable!
```

---

## Quick Reference: Python Security Libraries

| Need | Library | Install |
|------|---------|---------|
| Password hashing | `bcrypt` or `passlib` | `pip install bcrypt` |
| JWT | `PyJWT` | `pip install PyJWT` |
| Input validation | `pydantic` | `pip install pydantic` |
| SQL (safe ORM) | `SQLAlchemy` | `pip install sqlalchemy` |
| CVE scanning | `pip-audit` | `pip install pip-audit` |
| Secrets | `python-dotenv` | `pip install python-dotenv` |
| Rate limiting | `Flask-Limiter` | `pip install Flask-Limiter` |
| Structured logging | `structlog` | `pip install structlog` |
| SSRF protection | `validators` | `pip install validators` |

---

## Further Reference

For deep dives, see:
- `references/owasp-python-extended.md` — Extended examples per OWASP category
- OWASP Python Security Project: https://owasp.org/www-project-python-security/
- Python Security docs: https://python-security.readthedocs.io/
