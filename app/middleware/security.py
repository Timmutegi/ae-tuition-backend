"""
Security middleware for blocking malicious requests and tracking suspicious IPs.
This middleware is production-only.
"""
import re
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Set, Dict
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Configure security logger
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.WARNING)

# Create console handler for security events
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
))
security_logger.addHandler(console_handler)


class MaliciousPatterns:
    """Patterns indicating malicious requests."""

    # Paths that should NEVER be accessed on a FastAPI app
    BLOCKED_PATHS = [
        # Git/Version Control
        r"\.git",
        r"\.svn",
        r"\.hg",
        r"\.bzr",

        # Configuration files
        r"\.env",
        r"\.htaccess",
        r"\.htpasswd",
        r"wp-config\.php",
        r"config\.php",
        r"settings\.php",
        r"credentials",

        # PHP-specific exploits (CVE-2017-9841 and similar)
        r"vendor/phpunit",
        r"eval-stdin\.php",
        r"phpunit",
        r"\.php$",
        r"\.php\?",
        r"\.phtml",
        r"\.php3",
        r"\.php4",
        r"\.php5",
        r"\.php7",
        r"\.phps",

        # Framework-specific attacks
        r"think[pP]hp",
        r"thinkphp",
        r"index\.php",
        r"public/index\.php",
        r"invokefunction",
        r"call_user_func",

        # Laravel/Yii/Zend attacks
        r"laravel",
        r"yii",
        r"zend",
        r"artisan",
        r"\.blade\.php",

        # Docker/Container exposure
        r"containers/json",
        r"docker\.sock",
        r"_ping",
        r"v1\.\d+/containers",

        # Router/IoT exploitation
        r"luci",
        r"cgi-bin",
        r"webLanguage",
        r"/SDK",
        r"goform",
        r"formLogin",
        r"developmentserver",
        r"metadatauploader",

        # WordPress attacks
        r"wp-admin",
        r"wp-content",
        r"wp-includes",
        r"wp-login",
        r"xmlrpc\.php",

        # Shell/Remote code execution
        r"shell",
        r"cmd\.php",
        r"c99",
        r"r57",

        # Backup/sensitive files
        r"\.sql$",
        r"\.bak$",
        r"\.old$",
        r"\.backup$",
        r"\.tar$",
        r"\.tar\.gz$",
        r"\.rar$",
        r"dump",

        # Admin panels (non-API)
        r"phpmyadmin",
        r"adminer",
        r"manager/html",
        r"admin\.php",

        # Other scripting languages
        r"\.asp$",
        r"\.aspx$",
        r"\.jsp$",
        r"\.cgi$",
        r"\.pl$",

        # Misc probes
        r"well-known/security",
        r"actuator",
        r"service/api-docs",
        r"/bins/",
    ]

    # Query string patterns that indicate attacks
    BLOCKED_QUERY_PATTERNS = [
        r"allow_url_include",
        r"auto_prepend_file",
        r"php://input",
        r"php://filter",
        r"expect://",
        r"data://text",
        r"file://",
        r"glob://",
        r"phar://",
        r"zip://",
        r"union\s+select",
        r"<script",
        r"javascript:",
        r"onerror\s*=",
        r"onclick\s*=",
        r"onload\s*=",
        r"onmouseover\s*=",
        r"eval\(",
        r"base64_decode",
        r"exec\(",
        r"system\(",
        r"passthru\(",
        r"pearcmd",
    ]

    # User-Agent patterns for known malicious scanners
    BLOCKED_USER_AGENTS = [
        r"sqlmap",
        r"nikto",
        r"nmap",
        r"masscan",
        r"zgrab",
        r"gobuster",
        r"dirbuster",
        r"wpscan",
        r"nessus",
        r"openvas",
        r"acunetix",
        r"qualys",
        r"nuclei",
        r"httpx",
        r"python-requests.*scan",
        r"curl.*scan",
    ]

    _path_patterns = None
    _query_patterns = None
    _ua_patterns = None

    @classmethod
    def compile_patterns(cls):
        """Compile regex patterns for performance."""
        if cls._path_patterns is None:
            cls._path_patterns = [re.compile(p, re.IGNORECASE) for p in cls.BLOCKED_PATHS]
            cls._query_patterns = [re.compile(p, re.IGNORECASE) for p in cls.BLOCKED_QUERY_PATTERNS]
            cls._ua_patterns = [re.compile(p, re.IGNORECASE) for p in cls.BLOCKED_USER_AGENTS]

    @classmethod
    def get_path_patterns(cls):
        if cls._path_patterns is None:
            cls.compile_patterns()
        return cls._path_patterns

    @classmethod
    def get_query_patterns(cls):
        if cls._query_patterns is None:
            cls.compile_patterns()
        return cls._query_patterns

    @classmethod
    def get_ua_patterns(cls):
        if cls._ua_patterns is None:
            cls.compile_patterns()
        return cls._ua_patterns


class IPTracker:
    """Track suspicious IPs for rate limiting and blocking."""

    def __init__(
        self,
        block_threshold: int = 10,
        block_duration_minutes: int = 60,
        track_window_minutes: int = 5
    ):
        self.block_threshold = block_threshold
        self.block_duration = timedelta(minutes=block_duration_minutes)
        self.track_window = timedelta(minutes=track_window_minutes)

        # Track violations: IP -> list of timestamps
        self.violations: Dict[str, list] = defaultdict(list)
        # Blocked IPs: IP -> unblock_time
        self.blocked_ips: Dict[str, datetime] = {}
        # Permanent block list
        self.permanent_blocks: Set[str] = set()
        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def record_violation(self, ip: str, violation_type: str) -> bool:
        """
        Record a security violation for an IP.
        Returns True if IP is now blocked.
        """
        async with self._lock:
            now = datetime.utcnow()

            # Clean old violations
            cutoff = now - self.track_window
            self.violations[ip] = [t for t in self.violations[ip] if t > cutoff]

            # Add new violation
            self.violations[ip].append(now)

            # Check if threshold exceeded
            if len(self.violations[ip]) >= self.block_threshold:
                self.blocked_ips[ip] = now + self.block_duration
                security_logger.warning(
                    f"IP BLOCKED: {ip} - exceeded threshold with "
                    f"{len(self.violations[ip])} violations in {self.track_window.seconds}s"
                )
                return True

            return False

    async def is_blocked(self, ip: str) -> bool:
        """Check if an IP is currently blocked."""
        if ip in self.permanent_blocks:
            return True

        async with self._lock:
            if ip in self.blocked_ips:
                if datetime.utcnow() < self.blocked_ips[ip]:
                    return True
                else:
                    # Block expired
                    del self.blocked_ips[ip]

            return False

    def add_permanent_block(self, ip: str):
        """Add IP to permanent block list."""
        self.permanent_blocks.add(ip)
        security_logger.warning(f"IP PERMANENTLY BLOCKED: {ip}")

    def get_stats(self) -> dict:
        """Get current blocking statistics."""
        now = datetime.utcnow()
        # Clean expired blocks
        active_blocks = {
            ip: unblock_time.isoformat()
            for ip, unblock_time in self.blocked_ips.items()
            if unblock_time > now
        }

        return {
            "currently_blocked": len(active_blocks),
            "blocked_ips": active_blocks,
            "permanent_blocks": list(self.permanent_blocks),
            "tracked_ips": len(self.violations),
        }


# Global IP tracker instance
ip_tracker = IPTracker()


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware to block malicious requests before they reach the application.
    """

    def __init__(self, app, alert_service=None):
        super().__init__(app)
        self.alert_service = alert_service
        # Compile patterns on initialization
        MaliciousPatterns.compile_patterns()

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Get client IP (handle proxies)
        client_ip = self._get_client_ip(request)
        path = request.url.path.lower()
        query = str(request.url.query).lower() if request.url.query else ""
        user_agent = request.headers.get("user-agent", "").lower()

        # Check if IP is blocked
        if await ip_tracker.is_blocked(client_ip):
            security_logger.info(f"BLOCKED_IP_REQUEST: {client_ip} -> {path}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied"}
            )

        # Check for malicious patterns
        violation_type = self._check_request(path, query, user_agent)

        if violation_type:
            # Log the suspicious request
            security_logger.warning(
                f"MALICIOUS_REQUEST: {violation_type} | "
                f"IP: {client_ip} | Path: {request.url.path} | "
                f"Query: {query[:100]} | UA: {user_agent[:100]}"
            )

            # Record violation and potentially block
            is_now_blocked = await ip_tracker.record_violation(client_ip, violation_type)

            # Send alert if IP was just blocked
            if is_now_blocked and self.alert_service:
                await self.alert_service.send_ip_blocked_alert(
                    ip=client_ip,
                    violation_type=violation_type,
                    path=path
                )

            # Return 404 to not reveal information
            return JSONResponse(
                status_code=404,
                content={"detail": "Not found"}
            )

        # Process legitimate request
        response = await call_next(request)

        # Add request timing header (useful for debugging)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(round(process_time, 4))

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, accounting for proxies."""
        # Check X-Forwarded-For header (set by Nginx)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # First IP in the list is the client
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"

    def _check_request(
        self,
        path: str,
        query: str,
        user_agent: str
    ) -> Optional[str]:
        """
        Check request against malicious patterns.
        Returns violation type string if malicious, None if clean.
        """
        # Check path patterns
        for pattern in MaliciousPatterns.get_path_patterns():
            if pattern.search(path):
                return f"BLOCKED_PATH:{pattern.pattern}"

        # Check query string patterns
        for pattern in MaliciousPatterns.get_query_patterns():
            if pattern.search(query):
                return f"BLOCKED_QUERY:{pattern.pattern}"

        # Check user agent patterns
        for pattern in MaliciousPatterns.get_ua_patterns():
            if pattern.search(user_agent):
                return f"BLOCKED_UA:{pattern.pattern}"

        return None
