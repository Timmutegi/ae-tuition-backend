"""
Security alerts service for email notifications.
This middleware is production-only.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Set
import resend

from app.core.config import settings

logger = logging.getLogger("security_alerts")


class SecurityAlertService:
    """
    Service for sending security-related email alerts.
    Implements throttling to prevent alert fatigue.
    """

    def __init__(self):
        resend.api_key = settings.RESEND_API_KEY
        self.from_email = settings.FROM_EMAIL
        self.alert_email = getattr(settings, 'SECURITY_ALERT_EMAIL', 'support@ae-tuition.com')

        # Track sent alerts to implement throttling
        # Key: alert_type:identifier, Value: last_sent_time
        self._sent_alerts: Dict[str, datetime] = {}
        self._throttle_duration = timedelta(hours=1)

    def _should_send_alert(self, alert_key: str) -> bool:
        """Check if we should send this alert (throttling)."""
        now = datetime.utcnow()
        if alert_key in self._sent_alerts:
            last_sent = self._sent_alerts[alert_key]
            if now - last_sent < self._throttle_duration:
                return False

        self._sent_alerts[alert_key] = now
        return True

    def _cleanup_old_alerts(self):
        """Clean up old alert records."""
        now = datetime.utcnow()
        cutoff = now - self._throttle_duration * 2
        self._sent_alerts = {
            k: v for k, v in self._sent_alerts.items()
            if v > cutoff
        }

    async def send_ip_blocked_alert(
        self,
        ip: str,
        violation_type: str,
        path: str
    ) -> bool:
        """Send alert when an IP is blocked."""
        alert_key = f"ip_blocked:{ip}"

        if not self._should_send_alert(alert_key):
            logger.info(f"Throttled alert for blocked IP: {ip}")
            return False

        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #dc3545; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f8f9fa; }}
                    .detail {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #dc3545; }}
                    .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Security Alert: IP Blocked</h1>
                    </div>
                    <div class="content">
                        <p>An IP address has been automatically blocked due to suspicious activity.</p>

                        <div class="detail">
                            <strong>IP Address:</strong> {ip}<br>
                            <strong>Violation Type:</strong> {violation_type}<br>
                            <strong>Last Request Path:</strong> {path}<br>
                            <strong>Blocked At:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
                        </div>

                        <p>The IP will be automatically unblocked after 60 minutes unless additional violations occur.</p>

                        <p><strong>Recommended Actions:</strong></p>
                        <ul>
                            <li>Monitor logs for continued attack attempts</li>
                            <li>Consider permanent blocking if attacks persist</li>
                            <li>Review firewall rules</li>
                        </ul>
                    </div>
                    <div class="footer">
                        <p>AE Tuition Security System</p>
                        <p>This is an automated message. Do not reply.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            email_data = {
                "from": self.from_email,
                "to": [self.alert_email],
                "subject": f"[SECURITY ALERT] IP Blocked: {ip}",
                "html": html_content
            }

            try:
                response = resend.Emails.send(email_data)
                logger.info(f"Security alert sent for blocked IP {ip}: {response}")
                return True
            except Exception as e:
                logger.error(f"Failed to send security alert email: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"Error sending IP blocked alert: {str(e)}")
            return False

    async def send_high_volume_attack_alert(
        self,
        attack_count: int,
        unique_ips: int,
        top_paths: list
    ) -> bool:
        """Send alert for high volume attack detection."""
        alert_key = "high_volume_attack"

        if not self._should_send_alert(alert_key):
            logger.info("Throttled high volume attack alert")
            return False

        try:
            paths_html = "".join([f"<li>{path}</li>" for path in top_paths[:10]])

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #ffc107; color: #333; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f8f9fa; }}
                    .stat {{ display: inline-block; padding: 15px; margin: 5px; background: white; border-radius: 5px; text-align: center; }}
                    .stat-number {{ font-size: 24px; font-weight: bold; color: #dc3545; }}
                    .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>High Volume Attack Detected</h1>
                    </div>
                    <div class="content">
                        <p>The system has detected an unusually high volume of malicious requests.</p>

                        <div style="text-align: center;">
                            <div class="stat">
                                <div class="stat-number">{attack_count}</div>
                                <div>Total Attacks</div>
                            </div>
                            <div class="stat">
                                <div class="stat-number">{unique_ips}</div>
                                <div>Unique IPs</div>
                            </div>
                        </div>

                        <h3>Most Targeted Paths:</h3>
                        <ul>
                            {paths_html}
                        </ul>

                        <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

                        <p><strong>Recommended Actions:</strong></p>
                        <ul>
                            <li>Review server logs for additional context</li>
                            <li>Consider enabling stricter rate limiting</li>
                            <li>Monitor server resources</li>
                        </ul>
                    </div>
                    <div class="footer">
                        <p>AE Tuition Security System</p>
                    </div>
                </div>
            </body>
            </html>
            """

            email_data = {
                "from": self.from_email,
                "to": [self.alert_email],
                "subject": f"[SECURITY WARNING] High Volume Attack - {attack_count} requests",
                "html": html_content
            }

            try:
                response = resend.Emails.send(email_data)
                logger.info(f"High volume attack alert sent: {response}")
                return True
            except Exception as e:
                logger.error(f"Failed to send high volume alert email: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"Error sending high volume attack alert: {str(e)}")
            return False

    async def send_critical_security_event_alert(
        self,
        event_type: str,
        details: str,
        severity: str = "HIGH"
    ) -> bool:
        """Send alert for critical security events."""
        alert_key = f"critical:{event_type}"

        if not self._should_send_alert(alert_key):
            logger.info(f"Throttled critical security alert: {event_type}")
            return False

        severity_colors = {
            "CRITICAL": "#dc3545",
            "HIGH": "#fd7e14",
            "MEDIUM": "#ffc107",
            "LOW": "#17a2b8"
        }
        color = severity_colors.get(severity, "#6c757d")

        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: {color}; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f8f9fa; }}
                    .detail {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid {color}; }}
                    .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Critical Security Event</h1>
                        <p>Severity: {severity}</p>
                    </div>
                    <div class="content">
                        <div class="detail">
                            <strong>Event Type:</strong> {event_type}<br>
                            <strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                        </div>

                        <h3>Details:</h3>
                        <pre style="background: white; padding: 15px; overflow-x: auto;">{details}</pre>

                        <p>Please investigate this event immediately.</p>
                    </div>
                    <div class="footer">
                        <p>AE Tuition Security System</p>
                    </div>
                </div>
            </body>
            </html>
            """

            email_data = {
                "from": self.from_email,
                "to": [self.alert_email],
                "subject": f"[{severity}] Security Event: {event_type}",
                "html": html_content
            }

            try:
                response = resend.Emails.send(email_data)
                logger.info(f"Critical security alert sent: {response}")
                return True
            except Exception as e:
                logger.error(f"Failed to send critical alert email: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"Error sending critical security alert: {str(e)}")
            return False


# Global security alerts instance
security_alerts = SecurityAlertService()
