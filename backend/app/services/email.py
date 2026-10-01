import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("shopsathi.email")


class EmailService:
    """Sends mail through SMTP from env settings; with no SMTP_HOST it logs the email instead."""

    def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        if not s.smtp_host:
            logger.warning(
                "EMAIL (not sent, SMTP not configured)\nTo: %s\nSubject: %s\n\n%s", to, subject, body
            )
            return
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            if s.smtp_use_tls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)

    def send_password_reset(self, to: str, reset_link: str) -> None:
        self.send(
            to,
            "Reset your ShopSathi password",
            f"Use this link to set a new password:\n{reset_link}\n\n"
            "If you did not ask for this, ignore this email.",
        )


def get_email_service() -> EmailService:
    return EmailService()
