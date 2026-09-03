from __future__ import annotations

import html
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _escape_html(text: str) -> str:
    return html.escape(str(text), quote=False)


async def send_telegram_alert(payload: dict[str, Any]) -> bool:
    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()
    if not token or not chat_id:
        logger.debug("Telegram skipped — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    txn = payload.get("transaction", {})
    reasons = payload.get("reasons", [])
    reason_lines = "\n".join(f"• {_escape_html(r)}" for r in reasons) or "• —"
    text = (
        f"🚨 <b>RingWatch Alert</b>\n\n"
        f"<b>Txn:</b> <code>{_escape_html(txn.get('transaction_id', ''))}</code>\n"
        f"<b>Amount:</b> ₹{float(txn.get('amount_inr', 0)):,.2f}\n"
        f"<b>Risk:</b> {payload.get('risk_score')} (threshold {payload.get('threshold_used')})\n"
        f"<b>Band:</b> {_escape_html(payload.get('decision_band', ''))}\n\n"
        f"<b>Top reasons:</b>\n{reason_lines}\n\n"
        f"<i>{_escape_html(payload.get('network_note', ''))}</i>"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            if resp.status_code != 200:
                logger.warning("Telegram API error %s: %s", resp.status_code, resp.text[:300])
                return False
            return True
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False
