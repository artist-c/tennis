# Tennis Monitor

一个用于监控网球场地库存并通过飞书机器人发送通知的脚本。

当前脚本会自动监控：

- 今天到下周一的场地库存
- 支持同时监控多个场馆，当前内置：
  - `回体`
  - `兰观`
- 工作日：`20:00-21:00`、`21:00-22:00`
- 周末：`17:00-18:00`、`18:00-19:00`、`19:00-20:00`

当命中条件时，会向飞书机器人发送通知。

## 环境要求

- macOS 或 Linux
- Python 3.9+
- `requests`

安装依赖：

```bash
pip3 install requests
```

## 配置 .env

脚本启动时会自动读取项目目录下的 `.env` 文件。

先复制模板文件：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```env
# 飞书机器人 webhook，替换为你的真实地址
FEISHU_WEBHOOK=https://open.larkoffice.com/open-apis/bot/v2/hook/REPLACE_WITH_REAL_WEBHOOK

# 轮询间隔，单位秒
POLL_INTERVAL=20

# HTTP 请求超时，单位秒
REQUEST_TIMEOUT=10

# 留空表示监控所有场地，例如：1号场,2号场
TARGET_COURTS=

# 主场馆名称
PRIMARY_VENUE_NAME=软杰

# 是否启用兰观场馆监控
LANGUAN_ENABLED=true

# 兰观场馆名称
LANGUAN_VENUE_NAME=兰观

# 工作日监控时段
WEEKDAY_TARGET_SLOTS=20:00-21:00,21:00-22:00

# 周末监控时段
WEEKEND_TARGET_SLOTS=17:00-18:00,18:00-19:00,19:00-20:00

# 库存接口地址模板
INVENTORY_URL=http://www.ruanjiezh.cn:8081/api/mobile/reservation/tag/{date}

# 兰观库存接口
LANGUAN_INVENTORY_URL=https://wxservice-stg48.pospal.cn/wxapi/AppointmentVenue/LoadValidClassRoomApptSettingV2
LANGUAN_PROJECT_UID=1741574043214936056
LANGUAN_STORE_ID=5819221
LANGUAN_VISITOR_ID=替换成你的真实值
LANGUAN_VERSION_INFO=NC|2025.09.15
LANGUAN_REFERER=https://servicewechat.com/wxd8e3cbba9e327fc0/8/page-frame.html
```

说明：

- `FEISHU_WEBHOOK`：飞书群自定义机器人地址
- `POLL_INTERVAL`：轮询间隔，单位秒
- `REQUEST_TIMEOUT`：接口请求超时，单位秒
- `TARGET_COURTS`：指定监控场地，多个用逗号分隔；留空表示全部场地
- `PRIMARY_VENUE_NAME`：主场馆名称，默认 `软杰`
- `LANGUAN_ENABLED`：是否启用 `兰观` 场馆监控
- `LANGUAN_VENUE_NAME`：第二场馆名称，默认 `兰观`
- `WEEKDAY_TARGET_SLOTS`：工作日监控时段
- `WEEKEND_TARGET_SLOTS`：周末监控时段
- `INVENTORY_URL`：库存接口地址模板，通常不需要修改
- `LANGUAN_*`：兰观场馆接口配置

## 多场馆说明

现在脚本会把多个场馆的结果合并后统一筛选和通知，通知中会显示场馆名。

如果你暂时不想监控 `兰观`，可以在 `.env` 中关闭：

```env
LANGUAN_ENABLED=false
```

如果你想单独监控 `兰观`，可以直接运行独立脚本：

```bash
python3 languan_monitor.py
```

独立脚本会读取同一个 `.env`，并额外支持：

- `LANGUAN_TARGET_COURTS`：只监控兰观指定场地
- `INCLUDE_TODAY`：是否把今天纳入监控范围
- `LANGUAN_DAYS_AHEAD`：兰观独立脚本向后监控的天数，默认 `7`

## 运行方式

在项目目录执行：

```bash
python3 tennis_monitor.py
```

启动后会持续轮询，并在命中条件时发送飞书通知。

如果只跑兰观：

```bash
python3 languan_monitor.py
```

## 可用判断规则

当前脚本把场地视为“可通知”的条件为：

- `软杰`：`isBooked == false` 且 `reservationStatus == 1`
- `兰观`：`status == 0`

如果你后续想调整这个规则，可以修改 `tennis_monitor.py` 中的库存解析逻辑。

## 常见用法

只监控指定场地：

```env
TARGET_COURTS=1号场,2号场
```

修改轮询频率：

```env
POLL_INTERVAL=10
```

## 停止运行

脚本启动后会持续运行，按下面的快捷键停止：

```bash
Ctrl + C
```
