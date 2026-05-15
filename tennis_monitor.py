import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

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


load_dotenv()


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))  # 轮询间隔，秒
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

# 你要监控的目标
# 留空表示监控所有场地，例如：TARGET_COURTS=1号场,2号场
TARGET_COURTS = [x.strip() for x in os.getenv("TARGET_COURTS", "").split(",") if x.strip()]
# 工作日默认监控晚上 8-9 点和 9-10 点
WEEKDAY_TARGET_SLOTS = [
    x.strip()
    for x in os.getenv("WEEKDAY_TARGET_SLOTS", "20:00-21:00,21:00-22:00").split(",")
    if x.strip()
]
# 周末默认监控下午 5-6 点、6-7 点、7-8 点
WEEKEND_TARGET_SLOTS = [
    x.strip()
    for x in os.getenv("WEEKEND_TARGET_SLOTS", "17:00-18:00,18:00-19:00,19:00-20:00").split(",")
    if x.strip()
]

# 查询库存的接口地址模板
INVENTORY_URL = os.getenv(
    "INVENTORY_URL",
    "http://www.ruanjiezh.cn:8081/api/mobile/reservation/tag/{date}",
)

# 通知方式：这里用飞书机器人 webhook，换成企业微信/钉钉/Server酱也很容易
FEISHU_WEBHOOK = os.getenv(
    "FEISHU_WEBHOOK",
    "https://open.larkoffice.com/open-apis/bot/v2/hook/e674aa78-0bc6-4653-97cc-c8c5b1a8e888",
)

# 请求头按抓包结果填写
HEADERS = {
    "Proxy-Connection": "keep-alive",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
        "NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) "
        "MacWechat/3.8.7(0x13080712) UnifiedPCMacWechat(0xf2641702) "
        "XWEB/18788 Flue"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "http://www.ruanjiezh.cn",
    "Referer": "http://www.ruanjiezh.cn/",
    "Accept-Language": "zh-CN,zh;q=0.9",
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
                    "content": "🎾 发现可预订网球场地啦",
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
    try:
        resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        log("飞书通知发送成功")
    except Exception as e:
        log(f"飞书通知发送失败: {e}")


def build_inventory_url(target_date: str) -> str:
    if "{date}" in INVENTORY_URL:
        return INVENTORY_URL.format(date=quote(target_date, safe=""))
    return INVENTORY_URL


def fetch_inventory(target_date: str) -> dict:
    url = build_inventory_url(target_date)
    resp = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def parse_inventory(data: dict) -> list[dict]:
    results = []
    payload = data.get("data") or {}
    payload_date = payload.get("date", "")

    for item in payload.get("items", []):
        start_dt = item.get("startTime", "")
        end_dt = item.get("endTime", "")
        start_time = start_dt[11:16] if len(start_dt) >= 16 else ""
        end_time = end_dt[11:16] if len(end_dt) >= 16 else ""
        slot = f"{start_time}-{end_time}" if start_time and end_time else ""

        results.append({
            "date": item.get("reservationDate") or payload_date,
            "court_name": item.get("spaceName", ""),
            "slot": slot,
            "available": (
                not bool(item.get("isBooked", True))
                and int(item.get("reservationStatus", 0)) == 1
            ),
            "raw": item,
        })

    return results


def normalize_court_name(name: str) -> str:
    return name.replace("场地", "").strip()


def get_monitor_dates() -> list[str]:
    today = datetime.now().date()
    start_date = today
    days_until_next_monday = 7 - today.weekday() if today.weekday() != 0 else 7
    end_date = today + timedelta(days=days_until_next_monday)

    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.isoformat())
        current_date += timedelta(days=1)
    return dates


def get_target_slots_for_date(date_str: str) -> list[str]:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    if date_obj.weekday() < 5:
        return WEEKDAY_TARGET_SLOTS
    return WEEKEND_TARGET_SLOTS


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
        if target_slots and item["slot"] not in target_slots:
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


def format_message(items: list[dict]) -> str:
    lines = []
    for item in sorted(items, key=lambda x: (x["date"], x["slot"], x["court_name"])):
        weekday = format_weekday(item["date"])
        lines.append(f"• {item['date']} {weekday}")
        lines.append(f"  {item['court_name']} | {item['slot']}")
        lines.append("")
    lines.extend([
        f"监控时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "快去看看能不能抢到呀 ٩(ˊᗜˋ*)و",
    ])
    return "\n".join(lines)


def format_feishu_message(items: list[dict]) -> str:
    lines = []
    for item in sorted(items, key=lambda x: (x["date"], x["slot"], x["court_name"])):
        weekday = format_weekday(item["date"])
        lines.append(f"• {item['date']} **{weekday}**")
        lines.append(f"  {item['court_name']} | {item['slot']}")
        lines.append("")
    lines.extend([
        f"监控时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "快去看看能不能抢到呀 ٩(ˊᗜˋ*)و",
    ])
    return "\n".join(lines)


def main() -> None:
    last_sent_fp = ""

    monitor_dates = get_monitor_dates()
    log("开始监控库存")
    log(f"监控日期范围: {monitor_dates[0]} -> {monitor_dates[-1]}")
    log(f"目标场地: {TARGET_COURTS}")
    log(f"工作日时段: {WEEKDAY_TARGET_SLOTS}")
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
