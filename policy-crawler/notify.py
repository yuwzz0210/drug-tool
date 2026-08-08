# -*- coding: utf-8 -*-
"""邮件告警（规格：403/验证码等异常时告警）。未配置 SMTP_HOST 时静默跳过。"""
import os
import smtplib
from email.mime.text import MIMEText


def send_alert_email(subject, body, smtp_host=None, from_addr=None, to_addrs=None):
    smtp_host = smtp_host or os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        return False
    from_addr = from_addr or os.environ.get("SMTP_FROM", "crawler@localhost")
    to_addrs = to_addrs or os.environ.get("SMTP_TO", "").split(",")
    to_addrs = [a.strip() for a in to_addrs if a.strip()]
    if not to_addrs:
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    try:
        with smtplib.SMTP(smtp_host, timeout=10) as s:
            s.sendmail(from_addr, to_addrs, msg.as_string())
        return True
    except Exception:
        return False
