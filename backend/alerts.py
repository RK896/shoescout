"""
Price Alert System for ShoeScout.

Stores user alerts in MongoDB `alerts` collection and sends email
notifications when a shoe's current price drops to or below the
user's target price.

Email is sent via SMTP (default: Gmail). Set these env vars:
    SMTP_HOST      — default: smtp.gmail.com
    SMTP_PORT      — default: 587
    SMTP_USER      — sender Gmail address
    SMTP_PASSWORD  — Gmail App Password (not your account password)
    SMTP_FROM_NAME — display name, default: ShoeScout

Collection schema:
    {
      "_id": ObjectId,
      "email": "user@example.com",
      "shoe_model": "Nike Pegasus 41",
      "shoe_brand": "Nike",
      "shoe_image": "https://...",
      "target_price": 119.99,     # alert when price <= this
      "current_price": 139.99,    # last seen price at alert creation
      "created_at": ISODate,
      "last_triggered": ISODate | null,
      "active": true
    }
"""

import os
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# SMTP Configuration
# ─────────────────────────────────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "ShoeScout")

SITE_URL = os.getenv("SITE_URL", "https://shoescout.app")


def _parse_price(price_str: str) -> float:
    """Parse a price string like '$129.99' to a float."""
    if not price_str:
        return float("inf")
    match = re.search(r"[\d]+\.?\d*", price_str.replace(",", ""))
    return float(match.group()) if match else float("inf")


# ─────────────────────────────────────────────────────────────────────────────
# Email Sending
# ─────────────────────────────────────────────────────────────────────────────

def _build_alert_email(
    email: str,
    shoe_model: str,
    shoe_brand: str,
    shoe_image: str,
    target_price: float,
    current_price: float,
    retailer: str,
    buy_link: str,
    alert_id: str,
) -> MIMEMultipart:
    """Build a rich HTML email for a triggered price alert."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 Price Drop: {shoe_model} is now ${current_price:.2f}!"
    msg["From"]    = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"]      = email

    discount_pct = round((1 - current_price / target_price) * 100) if target_price > 0 else 0
    unsubscribe_url = f"{SITE_URL}/alerts/unsubscribe?id={alert_id}"

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Price Alert — ShoeScout</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',system-ui,sans-serif;color:#1e293b;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#0f172a;padding:24px 32px;text-align:center;">
            <div style="font-size:28px;font-weight:800;color:#f97316;letter-spacing:-0.5px;">ShoeScout</div>
            <div style="color:rgba(255,255,255,0.6);font-size:13px;margin-top:4px;">Price Alert Triggered</div>
          </td>
        </tr>

        <!-- Alert Banner -->
        <tr>
          <td style="background:linear-gradient(135deg,#f97316,#fb923c);padding:20px 32px;text-align:center;">
            <div style="color:white;font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:1px;">🎉 Price Drop Alert</div>
            <div style="color:white;font-size:36px;font-weight:800;margin:8px 0;">${current_price:.2f}</div>
            <div style="color:rgba(255,255,255,0.85);font-size:13px;">
              You set an alert for <strong>${target_price:.2f}</strong>
              {f'&nbsp;·&nbsp;<span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:999px;">{discount_pct}% below target</span>' if discount_pct > 0 else ''}
            </div>
          </td>
        </tr>

        <!-- Shoe Details -->
        <tr>
          <td style="padding:32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                {'<td width="140" style="padding-right:20px;vertical-align:top;"><img src="' + shoe_image + '" width="120" style="border-radius:8px;background:#f8fafc;object-fit:contain;" alt="' + shoe_model + '"></td>' if shoe_image else ''}
                <td style="vertical-align:top;">
                  <div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{shoe_brand}</div>
                  <div style="font-size:20px;font-weight:700;color:#1e293b;line-height:1.3;margin-bottom:12px;">{shoe_model}</div>
                  <div style="margin-bottom:8px;">
                    <span style="font-size:13px;color:#64748b;">Available at</span>
                    <span style="font-size:13px;font-weight:600;color:#1e293b;margin-left:6px;">{retailer}</span>
                  </div>
                  <a href="{buy_link}" style="display:inline-block;background:#16a34a;color:white;padding:10px 24px;border-radius:999px;font-size:14px;font-weight:700;text-decoration:none;margin-top:8px;">
                    Buy Now — ${current_price:.2f} →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding:0 32px 24px;border-top:1px solid #e2e8f0;background:#fafafa;">
            <p style="color:#64748b;font-size:13px;margin:20px 0 12px;">
              Want to see more deals? Browse the full ShoeScout catalog for more running shoe deals, AI-powered recommendations, and Reddit community reviews.
            </p>
            <a href="{SITE_URL}" style="display:inline-block;background:#0f172a;color:white;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;">
              View All Deals on ShoeScout
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px;text-align:center;border-top:1px solid #e2e8f0;">
            <p style="color:#94a3b8;font-size:11px;margin:0;">
              You're receiving this because you set a price alert on ShoeScout.<br>
              <a href="{unsubscribe_url}" style="color:#64748b;">Unsubscribe from this alert</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    plain = (
        f"Price Drop Alert — ShoeScout\n\n"
        f"{shoe_model} is now ${current_price:.2f} at {retailer} "
        f"(your target was ${target_price:.2f}).\n\n"
        f"Buy now: {buy_link}\n\n"
        f"Unsubscribe: {unsubscribe_url}"
    )

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def send_alert_email(
    email: str,
    shoe_model: str,
    shoe_brand: str,
    shoe_image: str,
    target_price: float,
    current_price: float,
    retailer: str,
    buy_link: str,
    alert_id: str,
) -> bool:
    """
    Send a price-drop alert email.
    Returns True on success, False on failure.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("SMTP credentials not configured — skipping email send.")
        return False

    try:
        msg = _build_alert_email(
            email, shoe_model, shoe_brand, shoe_image,
            target_price, current_price, retailer, buy_link, alert_id,
        )
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [email], msg.as_string())
        print(f"  ✉ Alert email sent to {email} for {shoe_model} @ ${current_price:.2f}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to send alert email to {email}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Alert Checking (called after each scraper run)
# ─────────────────────────────────────────────────────────────────────────────

def check_and_fire_alerts(db) -> int:
    """
    Compare active alerts against the current shoe prices in MongoDB.
    Fires email alerts for any shoe whose best current price has dropped
    to or below the user's target price.

    Cooldown: an alert won't re-fire within 24 hours of the last trigger
    to avoid spamming.

    Returns the number of alerts fired.
    """
    alerts_coll = db["alerts"]
    shoes_coll  = db["shoes"]

    active_alerts = list(alerts_coll.find({"active": True}))
    if not active_alerts:
        return 0

    fired = 0
    now = datetime.now(timezone.utc)
    cooldown = timedelta(hours=24)

    for alert in active_alerts:
        # Cooldown check
        last = alert.get("last_triggered")
        if last:
            if isinstance(last, str):
                try:
                    last = datetime.fromisoformat(last)
                except ValueError:
                    last = None
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last and (now - last) < cooldown:
                continue

        shoe_model  = alert.get("shoe_model", "")
        target_price = float(alert.get("target_price", 0))
        email        = alert.get("email", "")

        if not shoe_model or not email or target_price <= 0:
            continue

        # Find the shoe in the DB
        shoe = shoes_coll.find_one({"model": shoe_model}, {"_id": 0, "retailers": 1, "brand": 1, "image": 1})
        if not shoe:
            continue

        retailers = shoe.get("retailers", [])
        if not retailers:
            continue

        # Find the cheapest retailer right now
        best_price = float("inf")
        best_retailer = None
        best_link = ""
        for r in retailers:
            p = _parse_price(r.get("price", ""))
            if p < best_price:
                best_price    = p
                best_retailer = r.get("retailer", "")
                best_link     = r.get("link", "")

        if best_price == float("inf") or best_retailer is None:
            continue

        # Fire if price is at or below target
        if best_price <= target_price:
            success = send_alert_email(
                email        = email,
                shoe_model   = shoe_model,
                shoe_brand   = shoe.get("brand", ""),
                shoe_image   = shoe.get("image", ""),
                target_price = target_price,
                current_price = best_price,
                retailer     = best_retailer,
                buy_link     = best_link,
                alert_id     = str(alert["_id"]),
            )
            if success:
                fired += 1
                alerts_coll.update_one(
                    {"_id": alert["_id"]},
                    {"$set": {"last_triggered": now}}
                )

    print(f"Alert check complete: {fired} alert(s) fired out of {len(active_alerts)} active.")
    return fired
