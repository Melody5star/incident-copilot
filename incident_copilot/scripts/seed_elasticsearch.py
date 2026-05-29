"""Seed Elasticsearch with realistic incident sample data for demo."""

import asyncio
import json
import os
import random
from datetime import datetime, timedelta, timezone

from elasticsearch import AsyncElasticsearch

INDEX = "logs-2026.05.11"
ES_HOST = os.getenv("ELASTIC_HOSTS", "http://localhost:9200")
ES_API_KEY = os.getenv("ELASTIC_API_KEY", "")

SERVICES = ["payment-service", "auth-service", "cart-service", "user-service", "notification-service"]

PAYMENT_ERRORS = [
    {
        "message": "NullPointerException in PaymentProcessor.charge() at PaymentProcessor.java:142",
        "stack_trace": "java.lang.NullPointerException\n  at com.shop.payment.PaymentProcessor.charge(PaymentProcessor.java:142)\n  at com.shop.payment.CheckoutService.processOrder(CheckoutService.java:87)",
        "error_code": "NPE_CHARGE",
    },
    {
        "message": "Database connection timeout after 5000ms in PaymentRepository.save()",
        "stack_trace": "com.shop.payment.DatabaseTimeoutException: Timeout after 5000ms\n  at com.shop.payment.PaymentRepository.save(PaymentRepository.java:201)",
        "error_code": "DB_TIMEOUT",
    },
    {
        "message": "Stripe API rate limit exceeded: 429 Too Many Requests",
        "stack_trace": "com.stripe.exception.RateLimitException: Too Many Requests\n  at com.shop.payment.StripeGateway.charge(StripeGateway.java:55)",
        "error_code": "STRIPE_429",
    },
]

AUTH_ERRORS = [
    {
        "message": "JWT signature verification failed: token has been tampered",
        "stack_trace": "io.jsonwebtoken.SignatureException: JWT signature does not match\n  at com.shop.auth.JwtFilter.doFilter(JwtFilter.java:78)",
        "error_code": "JWT_INVALID",
    },
    {
        "message": "Redis connection refused at localhost:6379 — session store unavailable",
        "stack_trace": "redis.clients.jedis.exceptions.JedisConnectionException: Connection refused\n  at com.shop.auth.SessionStore.get(SessionStore.java:44)",
        "error_code": "REDIS_DOWN",
    },
]

TRACE_IDS = [f"abc{i:03d}def{i:04d}" for i in range(1, 21)]


def make_log(service: str, level: str, ts: datetime, error_template: dict | None = None) -> dict:
    doc = {
        "@timestamp": ts.isoformat(),
        "service": {"name": service},
        "log": {"level": level},
        "host": {"name": f"{service}-pod-{random.randint(1, 3)}"},
        "trace": {"id": random.choice(TRACE_IDS)},
        "kubernetes": {
            "namespace": "production",
            "pod": {"name": f"{service}-{random.randint(1000, 9999)}"},
        },
    }
    if error_template:
        doc["message"] = error_template["message"]
        doc["error"] = {
            "stack_trace": error_template["stack_trace"],
            "code": error_template["error_code"],
        }
    else:
        doc["message"] = f"{service} processed request successfully"
    return doc


async def seed():
    es = AsyncElasticsearch(
        hosts=[ES_HOST],
        api_key=ES_API_KEY if ES_API_KEY else None,
    )

    # Clear stale data so the baseline isn't inflated by previous seed runs
    try:
        await es.indices.delete(index=INDEX, ignore_unavailable=True)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    ops = []

    # Baseline period (60 min ago → 10 min ago): low error rate for payment-service
    for i in range(120):
        ts = now - timedelta(minutes=60) + timedelta(seconds=i * 28)
        level = "ERROR" if random.random() < 0.03 else "INFO"
        tmpl = random.choice(PAYMENT_ERRORS) if level == "ERROR" else None
        ops.append({"index": {"_index": INDEX}})
        ops.append(make_log("payment-service", level, ts, tmpl))

    # Spike period (last 8 min): high error rate for payment-service (NPE dominant)
    for i in range(80):
        ts = now - timedelta(minutes=8) + timedelta(seconds=i * 6)
        level = "ERROR" if random.random() < 0.75 else "INFO"
        tmpl = PAYMENT_ERRORS[0] if level == "ERROR" else None  # NPE dominant
        ops.append({"index": {"_index": INDEX}})
        ops.append(make_log("payment-service", level, ts, tmpl))

    # Auth service: some JWT errors in last 15 min
    for i in range(30):
        ts = now - timedelta(minutes=15) + timedelta(seconds=i * 28)
        level = "ERROR" if random.random() < 0.25 else "INFO"
        tmpl = random.choice(AUTH_ERRORS) if level == "ERROR" else None
        ops.append({"index": {"_index": INDEX}})
        ops.append(make_log("auth-service", level, ts, tmpl))

    # Other services: healthy
    for svc in ["cart-service", "user-service", "notification-service"]:
        for i in range(20):
            ts = now - timedelta(minutes=random.randint(1, 30))
            ops.append({"index": {"_index": INDEX}})
            ops.append(make_log(svc, "INFO", ts))

    resp = await es.bulk(operations=ops, refresh=True)
    errors = [item for item in resp["items"] if "error" in item.get("index", {})]
    print(f"Indexed {len(ops)//2} docs, {len(errors)} errors")

    # Verify
    count = await es.count(index="logs-*", query={"terms": {"log.level.keyword": ["ERROR", "CRITICAL", "FATAL"]}})
    print(f"Total error docs in logs-*: {count['count']}")

    await es.close()


asyncio.run(seed())
