# Extended OWASP Python Reference

## Django-Specific Security

### CSRF Protection
```python
# settings.py — always enabled by default, never disable:
MIDDLEWARE = [
    'django.middleware.csrf.CsrfViewMiddleware',  # ✅ Keep this
    ...
]

# For API views using DRF, use token auth instead:
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

### Django ORM — Safe vs Unsafe
```python
# ✅ Safe — ORM handles parameterization
User.objects.filter(username=username)

# ❌ Dangerous — raw() with string formatting
User.objects.raw(f"SELECT * FROM auth_user WHERE username='{username}'")

# ✅ Safe raw() with params
User.objects.raw("SELECT * FROM auth_user WHERE username=%s", [username])

# ❌ Dangerous — extra() with format strings
User.objects.extra(where=[f"username='{username}'"])
```

### Django Security Settings Checklist
```python
# production settings.py
DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = ["yourdomain.com"]

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
```

---

## FastAPI-Specific Security

### Input Validation with Pydantic
```python
from pydantic import BaseModel, validator, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @validator("username")
    def username_valid(cls, v):
        if not v.isalnum():
            raise ValueError("Username must be alphanumeric")
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be 3-50 characters")
        return v

    @validator("password")
    def password_strong(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        return v  # Hash AFTER validation, not here
```

### FastAPI Auth with OAuth2
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    return get_user(user_id)
```

---

## File Upload Security

```python
import os
import magic  # pip install python-magic
from pathlib import Path

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
ALLOWED_MIMETYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_upload(file, upload_dir: Path) -> Path:
    # 1. Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        raise ValueError("File too large")

    # 2. Check extension (not sufficient alone!)
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension {ext} not allowed")

    # 3. Check actual MIME type (magic bytes)
    header = file.read(2048)
    file.seek(0)
    mime = magic.from_buffer(header, mime=True)
    if mime not in ALLOWED_MIMETYPES:
        raise ValueError(f"File type {mime} not allowed")

    # 4. Sanitize filename — never use original filename directly
    import secrets
    safe_name = secrets.token_hex(16) + ext
    safe_path = upload_dir / safe_name

    # 5. Ensure path stays within upload_dir (path traversal protection)
    if not safe_path.resolve().is_relative_to(upload_dir.resolve()):
        raise ValueError("Path traversal detected")

    return safe_path
```

---

## Environment & Secrets Management

```python
# ✅ Use python-dotenv for development
from dotenv import load_dotenv
import os

load_dotenv()  # Loads .env file (never commit .env!)

DATABASE_URL = os.environ["DATABASE_URL"]  # Raises if missing — intentional
SECRET_KEY = os.environ["SECRET_KEY"]

# ✅ Validate secrets on startup
def validate_config():
    required = ["DATABASE_URL", "SECRET_KEY", "JWT_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {missing}")

# .gitignore must contain:
# .env
# *.pem
# *.key
# secrets/
```

---

## Common Python Anti-Patterns → Secure Alternatives

| Anti-pattern | Risk | Fix |
|---|---|---|
| `eval(user_input)` | RCE | Use `ast.literal_eval()` for data, or redesign |
| `exec(user_input)` | RCE | Never — redesign the feature |
| `pickle.loads(data)` | RCE | Use `json.loads()` |
| `yaml.load(data)` | RCE | Use `yaml.safe_load()` |
| `os.system(f"cmd {x}")` | Command injection | `subprocess.run(["cmd", x])` |
| `subprocess.run(cmd, shell=True)` | Command injection | `shell=False` (default) |
| `hashlib.md5(pwd)` | Weak crypto | `bcrypt.hashpw()` |
| `random.random()` for tokens | Predictable | `secrets.token_urlsafe()` |
| Hardcoded `SECRET_KEY = "abc"` | Credential leak | `os.environ["SECRET_KEY"]` |
| `open(user_path)` | Path traversal | Validate with `.resolve().is_relative_to()` |
| `DEBUG = True` in prod | Info disclosure | `DEBUG = False` |
| Logging passwords | Credential leak | Log only non-sensitive fields |

---

## Security Headers (Flask/FastAPI)

```python
# Flask — flask-talisman
from flask_talisman import Talisman

Talisman(app,
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self'",
    },
    force_https=True,
    strict_transport_security=True,
)

# FastAPI — custom middleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["yourdomain.com"])
app.add_middleware(HTTPSRedirectMiddleware)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
```
