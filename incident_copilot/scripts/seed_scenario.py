"""Seed a specific incident scenario for demo rehearsal.

Usage:
    python3 scripts/seed_scenario.py <1-5>

Scenarios:
    1 — Payment NPE Spike        (1 service, stack trace, dominant error)
    2 — Auth Redis Failure       (auth service, connection refused, JWT errors)
    3 — Database Timeout Storm   (payment service, DB timeouts, slow queries)
    4 — Cart + User Cascade      (2 services failing simultaneously)
    5 — Full Site Outage         (payment + auth + cart all spiking at once)
"""

import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone

from elasticsearch import AsyncElasticsearch

INDEX = "logs-2026.05.11"
ES_HOST = "http://localhost:9200"


def make_log(service, level, ts, message, stack_trace="", error_code=""):
    doc = {
        "@timestamp": ts.isoformat(),
        "service": {"name": service},
        "log": {"level": level},
        "host": {"name": f"{service}-pod-{random.randint(1, 3)}"},
        "trace": {"id": f"trace{random.randint(1000, 9999)}abc{random.randint(100, 999)}"},
        "kubernetes": {
            "namespace": "production",
            "pod": {"name": f"{service}-{random.randint(1000, 9999)}"},
        },
        "message": message,
    }
    if stack_trace:
        doc["error"] = {"stack_trace": stack_trace, "code": error_code}
    return doc


async def clear_and_seed(docs: list[dict]):
    es = AsyncElasticsearch(hosts=[ES_HOST])
    try:
        await es.indices.delete(index=INDEX, ignore_unavailable=True)
    except Exception:
        pass

    ops = []
    for doc in docs:
        ops.append({"index": {"_index": INDEX}})
        ops.append(doc)

    resp = await es.bulk(operations=ops, refresh=True)
    errors = [item for item in resp["items"] if "error" in item.get("index", {})]
    print(f"Seeded {len(ops)//2} docs, {len(errors)} errors")
    await es.close()


# ─── Scenario 1: Payment NPE Spike ──────────────────────────────────────────

async def scenario_1():
    """payment-service NullPointerException spike — single service, clear stack trace."""
    print("Seeding Scenario 1: Payment NPE Spike")
    now = datetime.now(timezone.utc)
    docs = []

    # Baseline: payment-service mostly healthy for last 60 min
    for i in range(120):
        ts = now - timedelta(minutes=60) + timedelta(seconds=i * 28)
        level = "ERROR" if random.random() < 0.03 else "INFO"
        if level == "ERROR":
            docs.append(make_log("payment-service", "ERROR", ts,
                "NullPointerException in PaymentProcessor.charge() at PaymentProcessor.java:142",
                "java.lang.NullPointerException\n  at com.shop.payment.PaymentProcessor.charge(PaymentProcessor.java:142)\n  at com.shop.payment.CheckoutService.processOrder(CheckoutService.java:87)",
                "NPE_CHARGE"))
        else:
            docs.append(make_log("payment-service", "INFO", ts, "Payment processed successfully"))

    # Spike: last 8 min, 75% error rate
    for i in range(80):
        ts = now - timedelta(minutes=8) + timedelta(seconds=i * 6)
        level = "ERROR" if random.random() < 0.75 else "INFO"
        if level == "ERROR":
            docs.append(make_log("payment-service", "ERROR", ts,
                "NullPointerException in PaymentProcessor.charge() at PaymentProcessor.java:142",
                "java.lang.NullPointerException\n  at com.shop.payment.PaymentProcessor.charge(PaymentProcessor.java:142)\n  at com.shop.payment.CheckoutService.processOrder(CheckoutService.java:87)",
                "NPE_CHARGE"))
        else:
            docs.append(make_log("payment-service", "INFO", ts, "Payment processed successfully"))

    # Other services healthy
    for svc in ["auth-service", "cart-service", "user-service"]:
        for i in range(15):
            ts = now - timedelta(minutes=random.randint(1, 30))
            docs.append(make_log(svc, "INFO", ts, f"{svc} healthy"))

    await clear_and_seed(docs)
    print("✅ Scenario 1 ready — type: 'Check all services for incidents right now'")


# ─── Scenario 2: Auth Redis Failure ─────────────────────────────────────────

async def scenario_2():
    """auth-service Redis connection refused — login broken, JWT errors."""
    print("Seeding Scenario 2: Auth Service Redis Failure")
    now = datetime.now(timezone.utc)
    docs = []

    # auth-service baseline healthy
    for i in range(60):
        ts = now - timedelta(minutes=60) + timedelta(seconds=i * 55)
        docs.append(make_log("auth-service", "INFO", ts, "User authenticated successfully"))

    # auth-service spike: Redis down + JWT failures in last 10 min
    redis_errors = [
        ("Redis connection refused at localhost:6379 — session store unavailable",
         "redis.clients.jedis.exceptions.JedisConnectionException: Connection refused\n  at com.shop.auth.SessionStore.get(SessionStore.java:44)\n  at com.shop.auth.AuthService.validateSession(AuthService.java:112)",
         "REDIS_DOWN"),
        ("JWT signature verification failed: token has been tampered",
         "io.jsonwebtoken.SignatureException: JWT signature does not match\n  at com.shop.auth.JwtFilter.doFilter(JwtFilter.java:78)\n  at com.shop.auth.AuthService.validateToken(AuthService.java:56)",
         "JWT_INVALID"),
        ("Session lookup timeout after 3000ms — Redis not responding",
         "com.shop.auth.TimeoutException: Redis timeout after 3000ms\n  at com.shop.auth.SessionStore.get(SessionStore.java:51)",
         "SESSION_TIMEOUT"),
    ]
    for i in range(70):
        ts = now - timedelta(minutes=10) + timedelta(seconds=i * 8)
        level = "ERROR" if random.random() < 0.80 else "INFO"
        if level == "ERROR":
            err = random.choice(redis_errors)
            docs.append(make_log("auth-service", "ERROR", ts, err[0], err[1], err[2]))
        else:
            docs.append(make_log("auth-service", "INFO", ts, "Auth request received"))

    # payment-service and others healthy
    for svc in ["payment-service", "cart-service", "user-service"]:
        for i in range(15):
            ts = now - timedelta(minutes=random.randint(1, 20))
            docs.append(make_log(svc, "INFO", ts, f"{svc} healthy"))

    await clear_and_seed(docs)
    print("✅ Scenario 2 ready — type: 'Users cannot log in — auth-service is throwing errors. Triage it.'")


# ─── Scenario 3: Database Timeout Storm ─────────────────────────────────────

async def scenario_3():
    """payment-service database timeouts — checkout is hanging, slow queries."""
    print("Seeding Scenario 3: Database Timeout Storm")
    now = datetime.now(timezone.utc)
    docs = []

    db_errors = [
        ("Database connection timeout after 5000ms in PaymentRepository.save()",
         "com.shop.payment.DatabaseTimeoutException: Timeout after 5000ms\n  at com.shop.payment.PaymentRepository.save(PaymentRepository.java:201)\n  at com.shop.payment.PaymentService.processPayment(PaymentService.java:88)",
         "DB_TIMEOUT"),
        ("Deadlock detected in payment_transactions table — transaction rolled back",
         "org.springframework.dao.DeadlockLoserDataAccessException: Deadlock found\n  at com.shop.payment.PaymentRepository.save(PaymentRepository.java:201)",
         "DB_DEADLOCK"),
        ("Connection pool exhausted: 0 connections available (max=20)",
         "com.zaxxer.hikari.pool.HikariPool: Connection is not available, request timed out\n  at com.shop.payment.DatabaseConfig.getConnection(DatabaseConfig.java:45)",
         "POOL_EXHAUSTED"),
    ]

    # Baseline: rare timeouts
    for i in range(90):
        ts = now - timedelta(minutes=60) + timedelta(seconds=i * 38)
        level = "ERROR" if random.random() < 0.02 else "INFO"
        if level == "ERROR":
            docs.append(make_log("payment-service", "ERROR", ts, db_errors[0][0], db_errors[0][1], db_errors[0][2]))
        else:
            docs.append(make_log("payment-service", "INFO", ts, "Payment saved to DB successfully"))

    # Spike: DB timeouts exploding in last 7 min
    for i in range(65):
        ts = now - timedelta(minutes=7) + timedelta(seconds=i * 6)
        level = "ERROR" if random.random() < 0.85 else "INFO"
        if level == "ERROR":
            err = random.choice(db_errors)
            docs.append(make_log("payment-service", "ERROR", ts, err[0], err[1], err[2]))
        else:
            docs.append(make_log("payment-service", "INFO", ts, "Payment request received"))

    # Other services healthy
    for svc in ["auth-service", "cart-service", "user-service"]:
        for i in range(15):
            ts = now - timedelta(minutes=random.randint(1, 20))
            docs.append(make_log(svc, "INFO", ts, f"{svc} healthy"))

    await clear_and_seed(docs)
    print("✅ Scenario 3 ready — type: 'Checkout is hanging and payments are failing. Investigate payment-service.'")


# ─── Scenario 4: Cart + User Service Cascade ────────────────────────────────

async def scenario_4():
    """Two services failing together — cart errors + user-service 500s."""
    print("Seeding Scenario 4: Cart + User Service Cascade")
    now = datetime.now(timezone.utc)
    docs = []

    cart_errors = [
        ("ItemNotFoundException: product SKU-48291 not found in inventory",
         "com.shop.cart.ItemNotFoundException: SKU-48291 not found\n  at com.shop.cart.InventoryClient.getItem(InventoryClient.java:67)\n  at com.shop.cart.CartService.addItem(CartService.java:134)",
         "ITEM_NOT_FOUND"),
        ("Cart serialization failed: invalid product data structure",
         "com.fasterxml.jackson.databind.JsonMappingException: Unrecognized field 'discount_v2'\n  at com.shop.cart.CartSerializer.deserialize(CartSerializer.java:89)",
         "CART_DESERIALIZE"),
    ]
    user_errors = [
        ("UserProfileService: downstream call to profile-db timed out after 2000ms",
         "com.shop.user.ProfileServiceException: Timeout calling profile-db\n  at com.shop.user.UserProfileService.getProfile(UserProfileService.java:78)",
         "PROFILE_TIMEOUT"),
        ("User preferences update failed: optimistic lock exception",
         "org.springframework.orm.ObjectOptimisticLockingFailureException\n  at com.shop.user.PreferencesRepository.save(PreferencesRepository.java:112)",
         "OPT_LOCK"),
    ]

    # Both services healthy baseline
    for svc, errs in [("cart-service", cart_errors), ("user-service", user_errors)]:
        for i in range(60):
            ts = now - timedelta(minutes=60) + timedelta(seconds=i * 55)
            docs.append(make_log(svc, "INFO", ts, f"{svc} request processed"))

    # Spike: both services failing in last 9 min
    for i in range(55):
        ts = now - timedelta(minutes=9) + timedelta(seconds=i * 9)
        for svc, errs in [("cart-service", cart_errors), ("user-service", user_errors)]:
            level = "ERROR" if random.random() < 0.70 else "INFO"
            if level == "ERROR":
                err = random.choice(errs)
                docs.append(make_log(svc, "ERROR", ts, err[0], err[1], err[2]))
            else:
                docs.append(make_log(svc, "INFO", ts, f"{svc} request received"))

    # payment and auth healthy
    for svc in ["payment-service", "auth-service"]:
        for i in range(15):
            ts = now - timedelta(minutes=random.randint(1, 20))
            docs.append(make_log(svc, "INFO", ts, f"{svc} healthy"))

    await clear_and_seed(docs)
    print("✅ Scenario 4 ready — type: 'Customers are complaining about the shopping cart and their profiles not loading. Triage all affected services.'")


# ─── Scenario 5: Full Site Outage ───────────────────────────────────────────

async def scenario_5():
    """Critical: payment + auth + cart all failing simultaneously."""
    print("Seeding Scenario 5: Full Site Outage")
    now = datetime.now(timezone.utc)
    docs = []

    service_errors = {
        "payment-service": [
            ("NullPointerException in PaymentProcessor.charge() at PaymentProcessor.java:142",
             "java.lang.NullPointerException\n  at com.shop.payment.PaymentProcessor.charge(PaymentProcessor.java:142)",
             "NPE_CHARGE"),
        ],
        "auth-service": [
            ("Redis connection refused at localhost:6379 — session store unavailable",
             "redis.clients.jedis.exceptions.JedisConnectionException: Connection refused\n  at com.shop.auth.SessionStore.get(SessionStore.java:44)",
             "REDIS_DOWN"),
        ],
        "cart-service": [
            ("Cart serialization failed: invalid product data structure",
             "com.fasterxml.jackson.databind.JsonMappingException: Unrecognized field 'discount_v2'\n  at com.shop.cart.CartSerializer.deserialize(CartSerializer.java:89)",
             "CART_DESERIALIZE"),
        ],
    }

    # All services healthy baseline
    for svc in service_errors:
        for i in range(60):
            ts = now - timedelta(minutes=60) + timedelta(seconds=i * 55)
            docs.append(make_log(svc, "INFO", ts, f"{svc} healthy"))

    # Mass failure in last 6 min — all 3 services spiking
    for i in range(60):
        ts = now - timedelta(minutes=6) + timedelta(seconds=i * 6)
        for svc, errs in service_errors.items():
            level = "ERROR" if random.random() < 0.80 else "INFO"
            if level == "ERROR":
                err = random.choice(errs)
                docs.append(make_log(svc, "ERROR", ts, err[0], err[1], err[2]))
            else:
                docs.append(make_log(svc, "INFO", ts, f"{svc} degraded"))

    # user-service still healthy (isolated)
    for i in range(15):
        ts = now - timedelta(minutes=random.randint(1, 20))
        docs.append(make_log("user-service", "INFO", ts, "user-service healthy"))

    await clear_and_seed(docs)
    print("✅ Scenario 5 ready — type: 'CRITICAL: Site is down. Payment, auth, and cart are all failing. Triage everything immediately and file issues for each.'")


# ─── Entry point ─────────────────────────────────────────────────────────────

SCENARIOS = {
    "1": scenario_1,
    "2": scenario_2,
    "3": scenario_3,
    "4": scenario_4,
    "5": scenario_5,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        print(__doc__)
        sys.exit(1)
    asyncio.run(SCENARIOS[sys.argv[1]]())
