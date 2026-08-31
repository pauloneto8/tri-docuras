import uuid

from fastapi import HTTPException
from starlette.requests import Request

from app.security.rate_limit import check_rate_limit


def test_rate_limit_blocks_after_threshold():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "headers": [],
            "client": ("203.0.113.1", 12345),
        }
    )
    key = f"test_{uuid.uuid4().hex}"
    for _ in range(10):
        check_rate_limit(request, key=key, limit=10, window_seconds=60)
    try:
        check_rate_limit(request, key=key, limit=10, window_seconds=60)
        assert False, "expected rate limit"
    except HTTPException as exc:
        assert exc.status_code == 429
