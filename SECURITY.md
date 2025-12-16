# AE Tuition API Security Documentation

This document describes the security measures implemented in the AE Tuition backend API to protect against automated attacks and unauthorized access.

## Table of Contents

- [Overview](#overview)
- [Security Architecture](#security-architecture)
- [Attack Patterns Blocked](#attack-patterns-blocked)
- [Configuration](#configuration)
- [Monitoring Security Events](#monitoring-security-events)
- [Testing Security Measures](#testing-security-measures)
- [Incident Response](#incident-response)
- [Troubleshooting](#troubleshooting)

---

## Overview

The security system implements a **defense-in-depth** approach with multiple layers of protection. All security measures are **production-only** - the development environment remains unchanged to facilitate testing and debugging.

### Key Features

| Feature | Description |
|---------|-------------|
| Malicious Path Blocking | Blocks requests to known attack paths (PHP exploits, config files, etc.) |
| Rate Limiting | Prevents brute force attacks on authentication endpoints |
| IP Auto-Blocking | Automatically blocks IPs after repeated violations |
| Security Headers | Protects against XSS, clickjacking, and other browser-based attacks |
| Email Alerts | Sends notifications for critical security events |

---

## Security Architecture

### Layer 1: Nginx (Reverse Proxy)

The first line of defense blocks malicious requests before they reach the application.

**Location**: `nginx.conf`

**Capabilities**:
- Path-based blocking using regex patterns
- Rate limiting zones (auth: 1r/s, api: 20r/s, general: 10r/s)
- Connection limits per IP
- Security headers injection
- Request size limits (10MB max)

### Layer 2: FastAPI Security Middleware

Application-level security for requests that pass Nginx.

**Location**: `app/middleware/security.py`

**Capabilities**:
- Pattern matching against 50+ malicious patterns
- IP violation tracking with sliding window
- Automatic IP blocking after threshold exceeded
- Real client IP extraction from proxy headers

### Layer 3: Rate Limiting (slowapi + Redis)

Distributed rate limiting to prevent abuse.

**Location**: `app/middleware/rate_limit.py`

**Capabilities**:
- Redis-backed for distributed deployments
- Per-endpoint rate limits
- Automatic 429 responses when exceeded

### Layer 4: Security Headers

Browser security directives.

**Location**: `app/middleware/headers.py`

**Headers Applied**:
```
Content-Security-Policy: default-src 'self'; script-src 'self'; ...
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=(), ...
```

### Layer 5: Email Alerts

Real-time notifications for security events.

**Location**: `app/middleware/alerts.py`

**Alert Types**:
- IP blocked notifications
- High volume attack detection
- Critical security events

---

## Attack Patterns Blocked

### PHP Exploits
| Pattern | Attack Type |
|---------|-------------|
| `eval-stdin.php` | CVE-2017-9841 (PHPUnit RCE) |
| `vendor/phpunit/*` | PHPUnit vulnerability scanning |
| `*.php`, `*.phtml` | PHP file execution attempts |
| `allow_url_include` | PHP remote file inclusion |
| `auto_prepend_file` | PHP code injection |

### Configuration File Access
| Pattern | Target |
|---------|--------|
| `.env` | Environment variables (secrets) |
| `.git/*` | Git repository credentials |
| `.htaccess` | Apache configuration |
| `wp-config.php` | WordPress database credentials |
| `config.php` | Application configuration |

### Framework-Specific Attacks
| Pattern | Framework |
|---------|-----------|
| `thinkphp`, `invokefunction` | ThinkPHP RCE |
| `artisan`, `.blade.php` | Laravel |
| `yii`, `zend` | Yii/Zend Framework |
| `wp-admin`, `xmlrpc.php` | WordPress |

### Infrastructure Probes
| Pattern | Target |
|---------|--------|
| `containers/json` | Docker API |
| `docker.sock` | Docker socket |
| `luci`, `cgi-bin` | Router admin panels |
| `SDK/webLanguage` | IoT devices |
| `actuator` | Spring Boot endpoints |

---

## Configuration

### Environment Variables

Add these to your production `.env` file:

```bash
# REQUIRED: Enable security middleware
ENVIRONMENT=production

# Redis for distributed rate limiting
REDIS_URL=redis://redis:6379

# Security alert recipient
SECURITY_ALERT_EMAIL=security@ae-tuition.com

# IP blocking configuration
IP_BLOCK_THRESHOLD=10           # Violations before blocking
IP_BLOCK_DURATION_MINUTES=60    # Block duration
IP_TRACK_WINDOW_MINUTES=5       # Violation tracking window

# Trusted proxy IPs (for X-Forwarded-For)
TRUSTED_PROXIES=127.0.0.1
```

### Rate Limits

| Endpoint | Limit | Purpose |
|----------|-------|---------|
| `/api/v1/auth/login` | 5/minute | Prevent brute force |
| `/api/v1/auth/change-password` | 3/minute | Prevent password enumeration |
| `/api/v1/auth/refresh` | 30/minute | Allow reasonable token refresh |
| All other API endpoints | 200/minute | General protection |

### Nginx Rate Limits

| Zone | Rate | Burst | Purpose |
|------|------|-------|---------|
| `auth` | 1r/s | 5 | Authentication endpoints |
| `api` | 20r/s | 20 | API endpoints |
| `general` | 10r/s | 10 | Other endpoints |

---

## Monitoring Security Events

### 1. Application Logs

View real-time security events:

```bash
# All API logs
docker-compose -f docker-compose-prod.yml logs -f api

# Filter for security events
docker-compose -f docker-compose-prod.yml logs -f api | grep -i "security\|blocked\|malicious"
```

**Log Format**:
```
2024-01-15 10:30:45 - SECURITY - WARNING - MALICIOUS_REQUEST: BLOCKED_PATH:\.env | IP: 1.2.3.4 | Path: /.env | Query: | UA: curl/7.68.0
2024-01-15 10:30:50 - SECURITY - WARNING - IP BLOCKED: 1.2.3.4 - exceeded threshold with 10 violations
```

### 2. Nginx Access Logs

```bash
# View Nginx logs
docker-compose -f docker-compose-prod.yml logs -f nginx

# Or access log file directly
docker exec ae-tuition-nginx-prod cat /var/log/nginx/access.log
```

**Log Format**:
```
1.2.3.4 - - [15/Jan/2024:10:30:45 +0000] "GET /.env HTTP/1.1" 404 27 "-" "curl/7.68.0" 0.001 -
```

### 3. Security Statistics Endpoint

**Endpoint**: `GET /api/v1/admin/security/stats`

**Authentication**: Admin JWT token required

**Example Request**:
```bash
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://your-server/api/v1/admin/security/stats
```

**Example Response**:
```json
{
  "status": "ok",
  "security": {
    "currently_blocked": 3,
    "blocked_ips": {
      "1.2.3.4": "2024-01-15T11:30:45",
      "5.6.7.8": "2024-01-15T11:25:00",
      "9.10.11.12": "2024-01-15T11:20:30"
    },
    "permanent_blocks": [],
    "tracked_ips": 15
  }
}
```

### 4. Email Alerts

Security alerts are sent to `SECURITY_ALERT_EMAIL` for:

- **IP Blocked**: When an IP exceeds the violation threshold
- **High Volume Attack**: When unusual attack patterns are detected
- **Critical Events**: Authentication failures, suspicious patterns

**Alert Throttling**: Maximum 1 alert per IP per hour to prevent alert fatigue.

### 5. Redis Monitoring

Check rate limiting data in Redis:

```bash
# Connect to Redis
docker exec -it ae-tuition-redis-prod redis-cli

# View all rate limit keys
KEYS *

# Check specific key
GET "LIMITER:1.2.3.4:/api/v1/auth/login"
```

---

## Testing Security Measures

### Test Blocked Paths

```bash
# Should return 404
curl -i http://your-server/.env
curl -i http://your-server/.git/config
curl -i http://your-server/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php
curl -i http://your-server/index.php?s=/index/think/app/invokefunction
```

### Test Rate Limiting

```bash
# Login rate limit (5/minute) - 6th request should get 429
for i in {1..6}; do
  echo "Request $i: $(curl -s -o /dev/null -w '%{http_code}' \
    -X POST http://your-server/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"identifier":"test","password":"test"}')"
done
```

### Test Security Headers

```bash
curl -I http://your-server/health
```

**Expected Headers**:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; ...
```

### Test IP Blocking

```bash
# Generate 10+ violations rapidly to trigger block
for i in {1..15}; do
  curl -s http://your-server/.env
done

# Subsequent requests should get 403
curl -i http://your-server/api/v1/health
```

---

## Incident Response

### When an IP is Blocked

1. **Check the logs** for the violation pattern:
   ```bash
   docker-compose -f docker-compose-prod.yml logs api | grep "IP_ADDRESS"
   ```

2. **Review the attack type** from the violation pattern

3. **Determine if legitimate**:
   - If a legitimate user was blocked, they will be unblocked after 60 minutes
   - For immediate unblock, restart the API container (clears in-memory blocks)

4. **For persistent attackers**, consider:
   - Adding to permanent block list
   - Implementing firewall rules
   - Reporting to abuse contacts

### When Under Active Attack

1. **Monitor attack volume**:
   ```bash
   docker-compose -f docker-compose-prod.yml logs -f nginx | grep "404\|429"
   ```

2. **Check blocked IP count**:
   ```bash
   curl -H "Authorization: Bearer TOKEN" http://your-server/api/v1/admin/security/stats
   ```

3. **If overwhelmed**, consider:
   - Stricter rate limits in `nginx.conf`
   - CloudFlare or AWS WAF
   - Temporary IP range blocks at firewall level

### Emergency: Disable Security (Not Recommended)

If security middleware causes issues, temporarily disable:

```bash
# In docker-compose-prod.yml, change:
- ENVIRONMENT=production
# To:
- ENVIRONMENT=development

# Then restart:
docker-compose -f docker-compose-prod.yml up -d api
```

---

## Troubleshooting

### Legitimate Users Getting Blocked

**Symptom**: Users report 403 or 429 errors

**Solution**:
1. Check if their IP is blocked: `GET /api/v1/admin/security/stats`
2. Review logs for false positives
3. Adjust `IP_BLOCK_THRESHOLD` if too sensitive
4. Restart API container to clear blocks immediately

### Rate Limiting Not Working

**Symptom**: No 429 responses even after many requests

**Checks**:
1. Verify `ENVIRONMENT=production` is set
2. Check Redis is running: `docker-compose -f docker-compose-prod.yml ps redis`
3. Check Redis connection: `docker exec ae-tuition-redis-prod redis-cli ping`
4. Review API logs for rate limiting initialization

### Security Headers Missing

**Symptom**: Headers not appearing in responses

**Checks**:
1. Verify `ENVIRONMENT=production`
2. Check middleware is loaded in API logs
3. Note: Nginx also adds headers - check both layers

### Email Alerts Not Sending

**Symptom**: No emails received for security events

**Checks**:
1. Verify `SECURITY_ALERT_EMAIL` is set
2. Check `RESEND_API_KEY` is valid
3. Review API logs for email errors
4. Check alert throttling (1 per IP per hour)

---

## Security Checklist for Production

- [ ] `ENVIRONMENT=production` is set
- [ ] `SECRET_KEY` is a strong, unique value
- [ ] `SECURITY_ALERT_EMAIL` is configured
- [ ] Redis is healthy and connected
- [ ] Nginx is using the updated `nginx.conf`
- [ ] Default admin password has been changed
- [ ] AWS credentials are not exposed
- [ ] Database is not publicly accessible
- [ ] HTTPS is enabled (via load balancer or Nginx)
- [ ] Regular log monitoring is in place

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-01 | Initial security implementation |

---

## Contact

For security concerns or to report vulnerabilities, contact: `SECURITY_ALERT_EMAIL`
