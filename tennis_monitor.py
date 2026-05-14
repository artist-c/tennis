import hashlib
import json
import os
import time
from datetime import datetime
from urllib.parse import quote

import requests


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))  # 轮询间隔，秒
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

# 你要监控的目标
TARGET_DATE = os.getenv("TARGET_DATE", "2026-05-15")
# 留空表示监控所有场地，例如：TARGET_COURTS=1号场,2号场
TARGET_COURTS = [x.strip() for x in os.getenv("TARGET_COURTS", "").split(",") if x.strip()]
# 默认只监控晚上 8-9 点和 9-10 点
TARGET_SLOTS = [x.strip() for x in os.getenv("TARGET_SLOTS", "20:00-21:00,21:00-22:00").split(",") if x.strip()]

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


def send_feishu(text: str) -> None:
    if not FEISHU_WEBHOOK or "REPLACE_WITH_REAL_WEBHOOK" in FEISHU_WEBHOOK:
        log("未配置 FEISHU_WEBHOOK，跳过通知")
        return

    payload = {
        "msg_type": "text",
        "content": {
            "text": text
        }
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


def fetch_inventory() -> dict:
    url = build_inventory_url(TARGET_DATE)
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
            "available": not bool(item.get("isBooked", True)),
            "raw": item,
        })

    return results


def normalize_court_name(name: str) -> str:
    return name.replace("场地", "").strip()


def filter_targets(items: list[dict]) -> list[dict]:
    matched = []
    normalized_targets = {normalize_court_name(name) for name in TARGET_COURTS}
    for item in items:
        if item["date"] != TARGET_DATE:
            continue
        if TARGET_COURTS and normalize_court_name(item["court_name"]) not in normalized_targets:
            continue
        if TARGET_SLOTS and item["slot"] not in TARGET_SLOTS:
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


def format_message(items: list[dict]) -> str:
    lines = [f"发现可预订网球场地，日期：{TARGET_DATE}"]
    for item in items:
        lines.append(f'- {item["court_name"]} {item["slot"]}')
    lines.append(f"监控时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def main() -> None:
    last_sent_fp = ""

    log("开始监控库存")
    log(f"目标日期: {TARGET_DATE}")
    log(f"目标场地: {TARGET_COURTS}")
    log(f"目标时段: {TARGET_SLOTS}")
    log(f"轮询间隔: {POLL_INTERVAL}s")

    while True:
        try:
            data = fetch_inventory()
            all_items = parse_inventory(data)
            matched = filter_targets(all_items)

            if matched:
                current_fp = fingerprint(matched)
                if current_fp != last_sent_fp:
                    msg = format_message(matched)
                    log("发现可用库存，发送通知")
                    log(msg.replace("\n", " | "))
                    send_feishu(msg)
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
