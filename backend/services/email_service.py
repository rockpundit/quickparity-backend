import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from typing import List

from backend.models import ReconciliationEntry

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.sender_email = os.getenv("SENDER_EMAIL", self.smtp_user)

    def send_discrepancy_alert(self, to_email: str, discrepancies: List[ReconciliationEntry]):
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not configured. Skipping email.")
            return

        subject = f"Action Required: {len(discrepancies)} Reconciliation Discrepancies Found"
        
        body = "<h3>Reconciliation Alert</h3>"
        body += f"<p>We found {len(discrepancies)} transactions that require your attention:</p><ul>"
        
        for d in discrepancies:
            body += f"<li><b>Date:</b> {d.date} | <b>Payout ID:</b> {d.payout_id} | <b>Variance:</b> ${d.variance_amount:.2f} ({d.variance_type})</li>"
        
        body += "</ul><p>Please log in to your dashboard to resolve these issues.</p>"

        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Discrepancy alert sent to {to_email}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
