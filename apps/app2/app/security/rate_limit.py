import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# Janela deslizante em memória por IP + rota (adequado para instância única).
_buckets: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(request: Request, *, key: str, limit: int, window_seconds: int) -> None:
    client_ip = request.client.host if request.client else "unknown"
    bucket_key = f"{client_ip}:{key}"
    now = time.monotonic()
    bucket = _buckets[bucket_key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        )

    bucket.append(now)
