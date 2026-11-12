---
type: runbook
title: Runbook - payment gateway timeouts
---
# Runbook - payment gateway timeouts

## Symptoms
Rising `GatewayTimeout` errors from PaymentClient and growing retry counts.

## Steps
1. Check gateway p99 latency on the dashboard.
2. If p99 is above `HTTP_TIMEOUT`, do not lower the timeout; raise it or shed load.
3. Check database connection pool utilisation; pool exhaustion looks like gateway timeouts (see RCA-1003).
