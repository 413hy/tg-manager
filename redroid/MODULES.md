# /root/redroid 功能模块清单

当前目录是 redroid + Telegram X + Appium 的 VPS 运行环境，核心目标是提供一个可远程控制的 Android 容器，用于后续 Telegram X 自动化。

## 1. 配置模块

文件：

- `redroid.env`
- `.env.example`

功能：

- 配置 redroid 镜像、容器名、数据目录。
- 配置 ADB 监听地址和端口，默认 `127.0.0.1:5555`。
- 配置 Appium 监听地址和端口，默认 `127.0.0.1:4723`。
- 配置 Telegram X APK 下载目录。

## 2. 初始化部署模块

文件：

- `scripts/init_redroid_env.sh`

功能：

- 安装基础系统依赖。
- 安装 Docker。
- 安装 Java。
- 安装 Node.js / npm。
- 安装 ADB。
- 安装 Appium。
- 安装 Appium UiAutomator2 driver。
- 准备 Android SDK 环境变量。
- 安装 systemd 服务文件。
- 安装 `/usr/local/bin` 下的快捷命令。

## 3. redroid 容器模块

文件：

- `scripts/start_redroid.sh`
- `scripts/stop_redroid.sh`
- `systemd/redroid-vps.service`

功能：

- 拉取并启动 `redroid/redroid:12.0.0_64only-latest`。
- 使用 Docker 容器运行 Android 12。
- 持久化数据到 `REDROID_DATA_DIR`，默认 `/var/lib/redroid/data`。
- ADB 端口只绑定本机，默认 `127.0.0.1:5555`。
- Docker restart policy 为 `unless-stopped`。
- systemd 服务 `redroid-vps.service` 已安装并启用。

## 4. 内核设备准备模块

文件：

- `scripts/setup_kernel.sh`

功能：

- 尝试加载 `binder_linux`。
- 尝试加载 `ashmem_linux`。
- 尝试挂载 binderfs。
- 准备 `/dev/binder`、`/dev/hwbinder`、`/dev/vndbinder`。
- 写入 `/etc/modules-load.d/redroid.conf` 和 `/etc/modprobe.d/redroid.conf`。

## 5. ADB 连接模块

文件：

- `scripts/connect_adb.sh`

快捷命令：

- `redroid-manager adb`
- `connect-redroid-adb`

功能：

- 启动 ADB server。
- 连接 `127.0.0.1:5555`。
- 等待设备状态变为 `device`。
- 输出当前设备列表。

## 6. Telegram X 安装模块

文件：

- `scripts/install_telegram_x.sh`

快捷命令：

- `redroid-manager tgx`
- `install-telegram-x`

功能：

- 通过 GitHub Releases API 获取最新 Telegram X APK。
- 下载 APK 到 `/opt/redroid/apk/telegram-x-latest.apk`。
- 通过 ADB 安装到 redroid。
- 当前已安装包名：`org.thunderdog.challegram`。

## 7. Appium 自动化服务模块

文件：

- `scripts/start_appium.sh`
- `systemd/appium-redroid.service`

快捷命令：

- `redroid-manager appium`
- `start-appium-redroid`

功能：

- 启动 Appium Server。
- 加载 UiAutomator2 driver。
- 提供 `http://127.0.0.1:4723/status` 状态接口。
- 当前服务 `appium-redroid.service` 已安装并正在运行。

## 8. 健康检查模块

文件：

- `scripts/healthcheck.sh`

快捷命令：

- `redroid-manager status`

功能：

- 检查 Docker 命令。
- 检查 Docker daemon。
- 检查 redroid 容器运行状态。
- 检查 ADB TCP 端口。
- 检查 ADB 设备状态。
- 检查 Appium 状态接口。

## 9. 统一管理入口

文件：

- `scripts/manage.sh`

快捷命令：

- `redroid-manager`

命令：

```bash
redroid-manager init
redroid-manager kernel
redroid-manager start
redroid-manager stop
redroid-manager restart
redroid-manager adb
redroid-manager tgx
redroid-manager appium
redroid-manager status
redroid-manager logs
redroid-manager ps
redroid-manager enable
redroid-manager disable
```

## 10. 文档模块

文件：

- `README.md`
- `README_upstream_vps_redroid_init.md`
- `MODULES.md`

功能：

- `README.md`：当前优化后项目说明。
- `README_upstream_vps_redroid_init.md`：原始 GitHub 文档备份。
- `MODULES.md`：当前功能模块清单。

## 当前部署状态

```text
Docker: installed and running
Java: OpenJDK 17.0.19
Node.js: v22.22.2
npm: 10.9.7
Appium: 3.4.2
UiAutomator2 driver: installed
ADB: 1.0.41
redroid container: redroid12 running
redroid image: redroid/redroid:12.0.0_64only-latest
ADB endpoint: 127.0.0.1:5555
Appium endpoint: 127.0.0.1:4723
Telegram X package: org.thunderdog.challegram
redroid-vps.service: enabled, active
appium-redroid.service: enabled, active
tg-redroid-bot.service: enabled, active
```

## 11. Telegram Bot 控制模块

文件：

- `bot/bot.py`
- `bot/telegram_api.py`
- `bot/login_flow.py`
- `bot/appium_client.py`
- `bot/db.py`
- `systemd/tg-redroid-bot.service`

快捷命令：

- `redroid-manager bot-status`
- `redroid-manager bot-logs`
- `redroid-manager bot-restart`
- `scripts/test_bot_interfaces.py`

功能：

- 只允许 `redroid.env` 中配置的 `TG_BOT_ALLOWED_USER_ID` 操作。
- 使用 Telegram Bot API 的 Reply Keyboard 和 Inline Keyboard 提供主菜单。
- 支持“初始化应用”：打开 Telegram X 并点击首次进入时的开始按钮。
- 支持“登录账号/更换手机号”：先准备新的手机号输入页，不再固定沿用上一次验证码页。
- 支持按当前 Appium 页面数据动态提示：页面文字、输入框、可点击项会回传给操作者。
- 如果当前 Telegram X 已登录账号，会尝试进入“Add Account/添加账号”流程。
- 登录成功后写入 SQLite 数据库 `/root/redroid/data/accounts.sqlite3`。
- 支持“账号列表”：查询已记录的登录账号、手机号、用户名、状态和最近更新时间。
- 支持“状态检查”：检查 Docker、redroid、ADB、Appium 和账号统计。
- 支持离线接口测试：覆盖菜单、回调、登录状态机、两步验证分支、数据库写入和权限拦截。

## 远程访问方式

ADB 和 Appium 都只绑定本机。远程机器需要通过 SSH 隧道访问：

```bash
ssh -L 5555:127.0.0.1:5555 -L 4723:127.0.0.1:4723 root@YOUR_VPS_IP
```

然后本地访问：

```bash
adb connect 127.0.0.1:5555
curl http://127.0.0.1:4723/status
```
