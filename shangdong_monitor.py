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


load_dotenv()


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
VENUE_NAME = os.getenv("SHANGDONG_VENUE_NAME", "上东体育中心")
TARGET_COURTS = [
    x.strip()
    for x in os.getenv("SHANGDONG_TARGET_COURTS", "").split(",")
    if x.strip()
]
# 工作日：晚 20:00-21:00
SHANGDONG_WEEKDAY_TARGET_SLOTS = [
    normalize_slot(x.strip())
    for x in os.getenv("SHANGDONG_WEEKDAY_TARGET_SLOTS", "20:00-21:00").split(",")
    if x.strip()
]
# 周末：18:00-21:00
SHANGDONG_WEEKEND_TARGET_SLOTS = [
    normalize_slot(x.strip())
    for x in os.getenv(
        "SHANGDONG_WEEKEND_TARGET_SLOTS",
        "18:00-19:00,19:00-20:00,20:00-21:00",
    ).split(",")
    if x.strip()
]
SHANGDONG_INVENTORY_URL = os.getenv(
    "SHANGDONG_INVENTORY_URL",
    "https://stmember.styd.cn/v1/venues/venues_site_list",
)
SHANGDONG_VENUE_ID = os.getenv("SHANGDONG_VENUE_ID", "2446145037664310")
SHANGDONG_SHOP_ID = os.getenv("SHANGDONG_SHOP_ID", "2445179626300102")
SHANGDONG_BRAND_CODE = os.getenv("SHANGDONG_BRAND_CODE", "4p6knKByJqm")
SHANGDONG_WX_TOKEN = os.getenv("SHANGDONG_WX_TOKEN", "FUo1SU3F_UllPhCIh_bZQirDFiXxUuD9")
SHANGDONG_REFERER = os.getenv(
    "SHANGDONG_REFERER",
    "https://servicewechat.com/wxac417392155a720c/14/page-frame.html",
)
SHANGDONG_PAGE_SIZE = int(os.getenv("SHANGDONG_PAGE_SIZE", "20"))
SHANGDONG_DAYS_AHEAD = int(os.getenv("SHANGDONG_DAYS_AHEAD", "7"))
INCLUDE_TODAY = getenv_bool("INCLUDE_TODAY", True)
FEISHU_WEBHOOK = os.getenv("SHANGDONG_WEBHOOK", "")

SHANGDONG_HEADERS = {
    "client-timezone": "+0800",
    "brand-code": SHANGDONG_BRAND_CODE,
    "xweb_xhr": "1",
    "shop-id": SHANGDONG_SHOP_ID,
    "theme-compatible": "1",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
        "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Mac "
        "MacWechat/WMPF MacWechat/3.8.7(0x13080712) "
        "UnifiedPCMacWechat(0xf2641702) XWEB/18788"
    ),
    "mina-version": "independent",
    "app-id": "mina",
    "wx-token": SHANGDONG_WX_TOKEN,
    "Accept": "*/*",
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "Referer": SHANGDONG_REFERER,
    "Accept-Language": "zh-CN,zh;q=0.9",
    "priority": "u=1, i",
    "Content-Type": "application/json",
}


def log(msg: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def send_feishu(markdown_text: str) -> None:
    if not FEISHU_WEBHOOK or "REPLACE_WITH_REAL_WEBHOOK" in FEISHU_WEBHOOK:
        log("未配置 SHANGDONG_WEBHOOK，跳过通知")
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
    end_date = today + timedelta(days=SHANGDONG_DAYS_AHEAD)

    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.isoformat())
        current_date += timedelta(days=1)
    return dates


def get_target_slots_for_date(date_str: str) -> list[str]:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    if date_obj.weekday() < 5:
        return SHANGDONG_WEEKDAY_TARGET_SLOTS
    return SHANGDONG_WEEKEND_TARGET_SLOTS


def fetch_inventory_page(target_date: str, page: int) -> dict:
    # 接口要求 date 形如 2026/06/06
    date_param = quote(target_date.replace("-", "/"), safe="")
    url = (
        f"{SHANGDONG_INVENTORY_URL}?id={SHANGDONG_VENUE_ID}"
        f"&date={date_param}&page={page}&size={SHANGDONG_PAGE_SIZE}"
    )
    resp = requests.get(url, headers=SHANGDONG_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_inventory(target_date: str) -> list[dict]:
    data = fetch_inventory_page(target_date, 1)
    if int(data.get("code", -1)) != 0:
        log(f"接口异常: date={target_date} resp={data}")
        return []
    payload = data.get("data") or {}
    return payload.get("list") or []


def parse_inventory(target_date: str, sites: list[dict]) -> list[dict]:
    results = []
    for site in sites:
        court_name = site.get("site_name", "")
        for slot_item in site.get("site_data") or []:
            start_time = slot_item.get("start_time", "")
            end_time = slot_item.get("end_time", "")
            slot = (
                f"{normalize_time_text(start_time)}-{normalize_time_text(end_time)}"
                if start_time and end_time
                else ""
            )
            results.append(
                {
                    "venue_name": VENUE_NAME,
                    "date": target_date,
                    "court_name": court_name,
                    "slot": slot,
                    "available": int(slot_item.get("status", -1)) == 2,
                    "raw": slot_item,
                }
            )
    return results


def fetch_all_inventory() -> list[dict]:
    all_items: list[dict] = []
    for target_date in get_monitor_dates():
        sites = fetch_inventory(target_date)
        all_items.extend(parse_inventory(target_date, sites))
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
    log(f"监控日期范围: {monitor_dates[0]} -> {monitor_dates[-1]}（共 {len(monitor_dates)} 天）")
    log(f"监控日期明细: {monitor_dates}")
    log(f"目标场地: {TARGET_COURTS}")
    log(f"工作日时段: {SHANGDONG_WEEKDAY_TARGET_SLOTS}")
    log(f"周末时段: {SHANGDONG_WEEKEND_TARGET_SLOTS}")
    log(f"轮询间隔: {POLL_INTERVAL}s")

    while True:
        try:
            current_dates = get_monitor_dates()
            log(
                f"本轮监控日期: {current_dates[0]} -> {current_dates[-1]}"
                f"（共 {len(current_dates)} 天）"
            )
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
