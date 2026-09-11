import os
import re
import sqlite3
import requests
import logging
from datetime import datetime, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    raise ValueError("BOT_TOKEN and CHANNEL_ID must be set in environment!")

URL = "https://github.com/newtest2354-commits/Test6iP/raw/refs/heads/main/output/best_ips.txt"

MAX_IPS_PER_POST = 100
MAX_POSTS_PER_RUN = 3
KEEP_HOURS = 720

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

DB_PATH = "sent_ips.db"

STICKER_ID = (
    "CAACAgQAAxkBAAFQIPRqZX1vfKzcJTDOKhYm6L84PiHTPAACnB4AAnBPKVNG_ENzw04GOz0E"
)


class TelegramSender:

    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.api = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()

    def _request(self, method, data):
        try:
            response = self.session.post(
                f"{self.api}/{method}",
                data=data,
                timeout=30
            )

            try:
                result = response.json()
            except ValueError:
                result = {
                    "ok": False,
                    "description": response.text
                }

            if not response.ok or not result.get("ok"):
                logger.error(
                    f"Telegram {method} failed: "
                    f"HTTP {response.status_code} - "
                    f"{result.get('description', 'Unknown error')}"
                )
                return None

            return result

        except requests.RequestException as e:
            logger.error(
                f"Telegram {method} request error: {e}"
            )
            return None

    def send_sticker(self):

        result = self._request(
            "sendSticker",
            {
                "chat_id": self.chat_id,
                "sticker": STICKER_ID
            }
        )

        if result and result.get("ok"):

            message_id = result["result"]["message_id"]

            save_bot_message(
                message_id,
                "sticker"
            )

            logger.info(
                f"Logo sticker sent successfully: {message_id}"
            )

            return message_id

        logger.error(
            "Logo sticker was not accepted by Telegram."
        )

        return None

    def send_message(
        self,
        text,
        parse_mode="HTML",
        disable_web_page_preview=False
    ):

        result = self._request(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": (
                    "true"
                    if disable_web_page_preview
                    else "false"
                )
            }
        )

        if result and result.get("ok"):

            message_id = result["result"]["message_id"]

            save_bot_message(
                message_id,
                "ip"
            )

            logger.info(
                f"IP message sent successfully: {message_id}"
            )

            return message_id

        logger.error(
            "IP message was not accepted by Telegram."
        )

        return None

    def delete_message(self, message_id):

        result = self._request(
            "deleteMessage",
            {
                "chat_id": self.chat_id,
                "message_id": message_id
            }
        )

        if result and result.get("ok"):

            logger.info(
                f"Deleted Telegram message: {message_id}"
            )

            return True

        return False

    def delete_previous_messages(self):

        previous_messages = get_bot_messages()

        if not previous_messages:

            logger.info(
                "No previous bot messages found."
            )

            return True

        logger.info(
            f"Found {len(previous_messages)} "
            f"previous bot messages."
        )

        all_deleted = True

        for message_id, message_type in previous_messages:

            if self.delete_message(message_id):

                delete_bot_message_record(
                    message_id
                )

                logger.info(
                    f"Previous {message_type} removed: "
                    f"{message_id}"
                )

            else:

                all_deleted = False

                logger.warning(
                    f"Could not remove previous "
                    f"{message_type}: {message_id}"
                )

        return all_deleted


def init_db():

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS sent_ips (
                ip TEXT PRIMARY KEY,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_messages (
                message_id INTEGER PRIMARY KEY,
                message_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

    finally:

        conn.close()

    logger.info(
        f"Database initialized at {DB_PATH}"
    )


def clean_old_ips():

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        cutoff = (
            datetime.now()
            - timedelta(hours=KEEP_HOURS)
        )

        c.execute(
            "DELETE FROM sent_ips WHERE sent_at < ?",
            (cutoff,)
        )

        deleted = c.rowcount

        conn.commit()

    finally:

        conn.close()

    if deleted:

        logger.info(
            f"Cleaned {deleted} old IPs."
        )


def get_sent_ips():

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        c.execute(
            "SELECT ip FROM sent_ips"
        )

        rows = c.fetchall()

    finally:

        conn.close()

    sent_count = len(rows)

    logger.info(
        f"Loaded {sent_count} previously sent IPs "
        f"from database"
    )

    return {
        row[0]
        for row in rows
    }


def mark_as_sent_batch(ips):

    if not ips:
        return

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        now = datetime.now()

        data = [
            (ip, now)
            for ip in ips
        ]

        c.executemany(
            """
            INSERT OR IGNORE INTO sent_ips
            (ip, sent_at)
            VALUES (?, ?)
            """,
            data
        )

        conn.commit()

    finally:

        conn.close()

    logger.info(
        f"Marked {len(ips)} IPs as sent."
    )


def save_bot_message(
    message_id,
    message_type
):

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        c.execute(
            """
            INSERT OR REPLACE INTO bot_messages
            (message_id, message_type, created_at)
            VALUES (?, ?, ?)
            """,
            (
                message_id,
                message_type,
                datetime.now()
            )
        )

        conn.commit()

    finally:

        conn.close()

    logger.info(
        f"Saved {message_type} message: "
        f"{message_id}"
    )


def get_bot_messages():

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        c.execute(
            """
            SELECT message_id, message_type
            FROM bot_messages
            ORDER BY message_id ASC
            """
        )

        rows = c.fetchall()

    finally:

        conn.close()

    return rows


def delete_bot_message_record(
    message_id
):

    conn = sqlite3.connect(DB_PATH)

    try:

        c = conn.cursor()

        c.execute(
            """
            DELETE FROM bot_messages
            WHERE message_id = ?
            """,
            (message_id,)
        )

        conn.commit()

    finally:

        conn.close()


def extract_ips_from_text(text):

    pattern = (
        r"\[IP:\s*([\d.]+)\]"
        r"\s*\[PORT:\s*(\d+)\]"
    )

    matches = re.findall(
        pattern,
        text
    )

    valid_ips = []

    for ip, port in matches:

        parts = ip.split(".")

        if (
            len(parts) == 4
            and all(
                p.isdigit()
                and 0 <= int(p) <= 255
                for p in parts
            )
        ):
            valid_ips.append(ip)

    return valid_ips


def fetch_ips_from_url():

    try:

        resp = requests.get(
            URL,
            timeout=30
        )

        resp.raise_for_status()

        text = resp.text

        if not text or not text.strip():

            logger.warning(
                "File is empty or contains no data"
            )

            return []

        all_ips = extract_ips_from_text(
            text
        )

        logger.info(
            f"Extracted {len(all_ips)} "
            f"IPs from file."
        )

        return all_ips

    except requests.exceptions.HTTPError as e:

        if e.response is not None and e.response.status_code == 404:

            logger.warning(
                "File not found (404). "
                "No IPs to fetch."
            )

        else:

            logger.error(
                f"HTTP error: {e}"
            )

        return []

    except Exception as e:

        logger.error(
            f"Error fetching file: {e}"
        )

        return []


def generate_caption(ips):

    ips_text = (
        "\n".join(ips)
        if ips
        else "No new IPs found."
    )

    return f"""🅰️🆁🅸🆂🅰️ 🅸🅿️
<b>🔰 لیست آی‌پی جدید ({len(ips)} IP)</b>
➖➖➖➖➖➖➖➖
<blockquote expandable><code>{ips_text}</code></blockquote>
➖➖➖➖➖➖➖➖
👈 اگر به لیست آی‌‌پی متصل هستید بهش دست نزنید ، فقط زمانی‌که آی‌پی شما فیلتر شد یا از کار افتاد سراغ این آی‌پی‌های جدید بیایید و تست کنید.

‼️ <b>جهت جواب‌دهی هرچه بهتر، قبل از استفاده ipها رو کپی و با Vpn خاموش اسکن کنید.</b>

<blockquote><b>🔹 <a href="https://t.me/aristapanel/47250">اسکنر آریستا</a></b></blockquote>


➖➖➖➖➖➖➖➖
<blockquote>@aristapanel</blockquote>
➖➖➖➖➖➖➖➖
#Arista #ip #clean_ip #ٱی‌پی_تمیز
<blockquote>مرگ بر جمهوری اسهالی</blockquote>"""


def send_ips_to_channel(
    sender,
    ips
):

    if not ips:

        logger.info(
            "No new IPs to send."
        )

        return 0

    logger.info(
        "Removing previous IP messages "
        "and sticker."
    )

    sender.delete_previous_messages()

    total_sent = 0
    posts = 0
    sent_in_run = []

    for i in range(
        0,
        len(ips),
        MAX_IPS_PER_POST
    ):

        if posts >= MAX_POSTS_PER_RUN:

            logger.info(
                f"Reached maximum "
                f"{MAX_POSTS_PER_RUN} "
                f"posts per run."
            )

            break

        chunk = ips[
            i:i + MAX_IPS_PER_POST
        ]

        caption = generate_caption(
            chunk
        )

        message_id = sender.send_message(
            caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        if message_id:

            logger.info(
                f"Post {posts + 1}: "
                f"sent {len(chunk)} IPs."
            )

            total_sent += len(chunk)

            sent_in_run.extend(
                chunk
            )

            posts += 1

        else:

            logger.error(
                f"Post {posts + 1} failed."
            )

    if sent_in_run:

        mark_as_sent_batch(
            sent_in_run
        )

        sticker_id = sender.send_sticker()

        if sticker_id:

            logger.info(
                f"Logo sticker sent successfully: "
                f"{sticker_id}"
            )

        else:

            logger.warning(
                "Failed to send logo sticker."
            )

    logger.info(
        f"Total {total_sent} IPs sent "
        f"in {posts} posts."
    )

    return total_sent


def main():

    logger.info(
        "Starting bot..."
    )

    init_db()
    clean_old_ips()

    all_ips = fetch_ips_from_url()

    if not all_ips:

        logger.warning(
            "No IPs retrieved from file. "
            "Skipping..."
        )

        return

    sent_set = get_sent_ips()

    new_ips = [
        ip
        for ip in all_ips
        if ip not in sent_set
    ]

    logger.info(
        f"{len(new_ips)} new IPs "
        f"(from {len(all_ips)} total)"
    )

    if not new_ips:

        logger.info(
            "All IPs already sent."
        )

        return

    sender = TelegramSender(
        BOT_TOKEN,
        CHANNEL_ID
    )

    sent_count = send_ips_to_channel(
        sender,
        new_ips
    )

    logger.info(
        f"Execution finished. "
        f"Sent: {sent_count}"
    )


if __name__ == "__main__":
    main()
