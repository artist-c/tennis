import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests


def load_dotenv(dotenv_path: str = ".env") -> None:
    env_file = Path(__file__).resolve().parent / dotenv_path
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ[key] = value


def getenv_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_time_text(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) < 2:
        return value.strip()
    return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"


def normalize_slot(slot: str) -> str:
    parts = [part.strip() for part in slot.split("-", 1)]
    if len(parts) != 2:
        return slot.strip()
    return f"{normalize_time_text(parts[0])}-{normalize_time_text(parts[1])}"


def parse_datetime_text(value: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def build_slot(start_text: str, end_text: str) -> str:
    start_dt = parse_datetime_text(start_text)
    end_dt = parse_datetime_text(end_text)
    if not start_dt or not end_dt:
        return ""

    if end_dt.minute == 59 and end_dt.second == 0:
        end_dt += timedelta(minutes=1)

    return f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"


load_dotenv()


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
VENUE_NAME = os.getenv("LANGUAN_VENUE_NAME", "兰观")
TARGET_COURTS = [
    x.strip() for x in os.getenv("LANGUAN_TARGET_COURTS", os.getenv("TARGET_COURTS", "")).split(",") if x.strip()
]
LANGUAN_WEEKDAY_TARGET_SLOTS = [
    normalize_slot(x.strip())
    for x in os.getenv("LANGUAN_WEEKDAY_TARGET_SLOTS", "20:00-21:00,21:00-22:00").split(",")
    if x.strip()
]
WEEKEND_TARGET_SLOTS = [
    normalize_slot(x.strip())
    for x in os.getenv("WEEKEND_TARGET_SLOTS", "17:00-18:00,18:00-19:00,19:00-20:00").split(",")
    if x.strip()
]
LANGUAN_INVENTORY_URL = os.getenv(
    "LANGUAN_INVENTORY_URL",
    "https://wxservice-stg48.pospal.cn/wxapi/AppointmentVenue/LoadValidClassRoomApptSettingV2",
)
LANGUAN_PROJECT_UID = os.getenv("LANGUAN_PROJECT_UID", "1741574043214936056")
LANGUAN_STORE_ID = os.getenv("LANGUAN_STORE_ID", "5819221")
LANGUAN_VISITOR_ID = os.getenv(
    "LANGUAN_VISITOR_ID",
    "BVYGXwpnAmBXZlJuXjQOPwg7AzcJZA9hCWgLPV01BzFVNAAwD2YHYQA2UmwNPwo+BWICZFhhWjQCM1YxUjZQZAVkBjc=",
)
LANGUAN_VERSION_INFO = os.getenv("LANGUAN_VERSION_INFO", "NC|2025.09.15")
LANGUAN_REFERER = os.getenv(
    "LANGUAN_REFERER",
    "https://servicewechat.com/wxd8e3cbba9e327fc0/8/page-frame.html",
)
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
INCLUDE_TODAY = getenv_bool("INCLUDE_TODAY", True)
LANGUAN_DAYS_AHEAD = int(os.getenv("LANGUAN_DAYS_AHEAD", "7"))

LANGUAN_HEADERS = {
    "psplvisitorauto": "API",
    "versioninfo": LANGUAN_VERSION_INFO,
    "storeid": LANGUAN_STORE_ID,
    "xweb_xhr": "1",
    "apptype": "1",
    "psplvisitorid": LANGUAN_VISITOR_ID,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
        "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Mac "
        "MacWechat/WMPF MacWechat/3.8.7(0x13080712) "
        "UnifiedPCMacWechat(0xf2641702) XWEB/18788"
    ),
    "Content-Type": "application/json",
    "Accept": "*/*",
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "Referer": LANGUAN_REFERER,
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "priority": "u=1, i",
}


def log(msg: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def send_feishu(markdown_text: str) -> None:
    if not FEISHU_WEBHOOK or "REPLACE_WITH_REAL_WEBHOOK" in FEISHU_WEBHOOK:
        log("未配置 FEISHU_WEBHOOK，跳过通知")
        return

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True,
            },
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": f"🎾 {VENUE_NAME} 场地提醒",
                },
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": markdown_text,
                }
            ],
        },
    }
    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    log("飞书通知发送成功")


def normalize_court_name(name: str) -> str:
    return name.replace("场地", "").replace("网球场", "").strip()


def get_monitor_dates() -> list[str]:
    today = datetime.now().date()
    start_date = today if INCLUDE_TODAY else today + timedelta(days=1)
    end_date = today + timedelta(days=LANGUAN_DAYS_AHEAD)

    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.isoformat())
        current_date += timedelta(days=1)
    return dates


def get_target_slots_for_date(date_str: str) -> list[str]:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    if date_obj.weekday() < 5:
        return LANGUAN_WEEKDAY_TARGET_SLOTS
    return WEEKEND_TARGET_SLOTS


def fetch_inventory(target_date: str) -> dict:
    resp = requests.post(
        LANGUAN_INVENTORY_URL,
        headers=LANGUAN_HEADERS,
        json={
            "dateTime": target_date,
            "projectUid": LANGUAN_PROJECT_UID,
            "userId": None,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def parse_inventory(data: dict) -> list[dict]:
    results = []
    payload = data.get("result") or {}
    for item in payload.get("slots", []):
        start_text = item.get("beginDatetime", "")
        start_dt = parse_datetime_text(start_text)
        results.append(
            {
                "venue_name": VENUE_NAME,
                "date": start_dt.strftime("%Y-%m-%d") if start_dt else "",
                "court_name": item.get("classRoomName", ""),
                "slot": build_slot(start_text, item.get("endDatetime", "")),
                "available": int(item.get("status", -1)) == 0,
                "raw": item,
            }
        )
    return results


def fetch_all_inventory() -> list[dict]:
    all_items = []
    for target_date in get_monitor_dates():
        data = fetch_inventory(target_date)
        all_items.extend(parse_inventory(data))
    return all_items


def filter_targets(items: list[dict]) -> list[dict]:
    matched = []
    normalized_targets = {normalize_court_name(name) for name in TARGET_COURTS}
    for item in items:
        if TARGET_COURTS and normalize_court_name(item["court_name"]) not in normalized_targets:
            continue
        target_slots = get_target_slots_for_date(item["date"])
        if target_slots and normalize_slot(item["slot"]) not in target_slots:
            continue
        if not item["available"]:
            continue
        matched.append(item)
    return matched


def fingerprint(items: list[dict]) -> str:
    key = json.dumps(
        sorted(
            [
                {
                    "date": x["date"],
                    "court_name": x["court_name"],
                    "slot": x["slot"],
                    "available": x["available"],
                }
                for x in items
            ],
            key=lambda x: (x["date"], x["court_name"], x["slot"]),
        ),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def format_weekday(date_str: str) -> str:
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return weekday_names[date_obj.weekday()]


def group_items_by_date_and_slot(items: list[dict]) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for item in sorted(items, key=lambda x: (x["date"], x["slot"], x["court_name"])):
        slot_group = grouped.setdefault(item["date"], {})
        courts = slot_group.setdefault(item["slot"], [])
        courts.append(item["court_name"])

    result = []
    for date in sorted(grouped):
        slot_items = []
        for slot in sorted(grouped[date]):
            slot_items.append((slot, grouped[date][slot]))
        result.append((date, slot_items))
    return result


def format_message(items: list[dict]) -> str:
    lines = []
    for date, slot_items in group_items_by_date_and_slot(items):
        lines.append(f"• [{VENUE_NAME}] {date} {format_weekday(date)}")
        for slot, courts in slot_items:
            lines.append(f"  🗓️ {slot}")
            lines.append(f"  🍃 {'、'.join(courts)}")
        lines.append("")
    lines.extend(
        [
            f"监控时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "快去看看能不能抢到呀 ٩(ˊᗜˋ*)و",
        ]
    )
    return "\n".join(lines)


def format_feishu_message(items: list[dict]) -> str:
    lines = []
    for date, slot_items in group_items_by_date_and_slot(items):
        lines.append(f"**【{VENUE_NAME}】** {date} **{format_weekday(date)}**")
        for slot, courts in slot_items:
            lines.append(f"  🗓️ {slot}")
            lines.append(f"  🍃 {'、'.join(courts)}")
        lines.append("")
    lines.extend(
        [
            f"监控时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "快去看看能不能抢到呀 ٩(ˊᗜˋ*)و",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    last_sent_fp = ""

    monitor_dates = get_monitor_dates()
    log(f"开始监控 {VENUE_NAME} 场地库存")
    log(f"监控日期范围: {monitor_dates[0]} -> {monitor_dates[-1]}")
    log(f"目标场地: {TARGET_COURTS}")
    log(f"工作日时段: {LANGUAN_WEEKDAY_TARGET_SLOTS}")
    log(f"周末时段: {WEEKEND_TARGET_SLOTS}")
    log(f"轮询间隔: {POLL_INTERVAL}s")

    while True:
        try:
            all_items = fetch_all_inventory()
            matched = filter_targets(all_items)

            if matched:
                current_fp = fingerprint(matched)
                if current_fp != last_sent_fp:
                    msg = format_message(matched)
                    feishu_msg = format_feishu_message(matched)
                    log("发现可用库存，发送通知")
                    log(msg.replace("\n", " | "))
                    send_feishu(feishu_msg)
                    last_sent_fp = current_fp
                else:
                    log("库存仍可用，但和上次通知相同，跳过重复通知")
            else:
                log("未发现目标库存")
                last_sent_fp = ""

        except requests.HTTPError as e:
            log(f"HTTP 错误: {e}")
        except requests.RequestException as e:
            log(f"网络错误: {e}")
        except Exception as e:
            log(f"运行错误: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
