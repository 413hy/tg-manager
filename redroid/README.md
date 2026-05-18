# redroid VPS Telegram X 环境

这个目录是对原 `init_redroid_env.sh` 的重整版。目标是把一次性脚本拆成可维护的 VPS 项目，方便重复启动、健康检查、systemd 托管和后续接入 Appium 自动化。

## 关键优化

- ADB 默认只绑定 `127.0.0.1:5555`，避免把调试端口暴露到公网。
- redroid 容器默认 `--restart unless-stopped`，不会每次启动都删除数据容器。
- 配置集中在 `/root/redroid/redroid.env`，端口、镜像、数据目录都从这里改。
- 提供 `redroid-manager` 统一入口，以及可安装的 `systemd` 服务。
- 增加 `healthcheck`，能同时检查 Docker、容器、ADB 和 Appium。
- Telegram X 下载和安装独立成脚本，可失败后单独重跑。

## 文件结构

```text
/root/redroid/
  redroid.env
  .env.example
  scripts/
    init_redroid_env.sh
    manage.sh
    setup_kernel.sh
    start_redroid.sh
    stop_redroid.sh
    connect_adb.sh
    install_telegram_x.sh
    start_appium.sh
    healthcheck.sh
  systemd/
    redroid-vps.service
    appium-redroid.service
```

## 首次安装

```bash
cd /root/redroid
chmod +x scripts/*.sh
bash scripts/init_redroid_env.sh
```

默认初始化只安装环境、写入命令和 systemd 单元，不会立刻启动 redroid、Appium 或安装 Telegram X。要一把跑完可以：

```bash
START_REDROID_NOW=1 INSTALL_TELEGRAM_X_NOW=1 START_APPIUM_NOW=1 bash /root/redroid/scripts/init_redroid_env.sh
```

## 常用命令

```bash
redroid-manager start
redroid-manager adb
redroid-manager tgx
redroid-manager appium
redroid-manager status
redroid-manager logs
redroid-manager bot-status
redroid-manager bot-logs
redroid-manager bot-restart
/root/redroid/scripts/test_bot_interfaces.py
```

如果还没有执行初始化，也可以直接调用目录内脚本：

```bash
/root/redroid/scripts/start_redroid.sh
/root/redroid/scripts/connect_adb.sh
/root/redroid/scripts/install_telegram_x.sh
```

## systemd

初始化后会安装并启用 `redroid-vps.service`：

```bash
systemctl status redroid-vps
systemctl start redroid-vps
systemctl enable redroid-vps
```

Appium 建议按需启动。如果确实要常驻：

```bash
systemctl enable --now appium-redroid
```

## 安全访问方式

ADB 和 Appium 默认只监听 VPS 本机。远程调试时使用 SSH 隧道：

```bash
ssh -L 5555:127.0.0.1:5555 -L 4723:127.0.0.1:4723 root@YOUR_VPS_IP
```

本地再连接：

```bash
adb connect 127.0.0.1:5555
curl http://127.0.0.1:4723/status
```

不要把 `REDROID_ADB_BIND_ADDR` 或 `APPIUM_BIND_ADDR` 改成 `0.0.0.0`，除非你已经有防火墙和访问控制。

## 配置

编辑：

```bash
nano /root/redroid/redroid.env
```

常见项：

```bash
REDROID_IMAGE=redroid/redroid:12.0.0_64only-latest
REDROID_NAME=redroid12
REDROID_DATA_DIR=/var/lib/redroid/data
REDROID_ADB_BIND_ADDR=127.0.0.1
REDROID_HOST_ADB_PORT=5555
APPIUM_BIND_ADDR=127.0.0.1
APPIUM_PORT=4723
```

修改容器关键参数后重建容器：

```bash
redroid-manager restart
```

## Appium capabilities

```json
{
  "platformName": "Android",
  "appium:automationName": "UiAutomator2",
  "appium:deviceName": "redroid",
  "appium:udid": "127.0.0.1:5555",
  "appium:appPackage": "org.thunderdog.challegram",
  "appium:appActivity": ".MainActivity",
  "appium:noReset": true,
  "appium:newCommandTimeout": 300
}
```

## 排错

```bash
redroid-manager status
docker logs redroid12
dmesg -T | tail -n 100
adb connect 127.0.0.1:5555
adb devices
redroid-manager bot-logs
```

如果 `/dev/binder`、`/dev/hwbinder`、`/dev/vndbinder` 缺失，说明宿主机内核可能不支持 redroid 需要的 binder 能力。脚本会尝试加载模块和挂载 binderfs，但不能补齐 VPS 内核本身没有的能力。

## Telegram Bot

Bot 服务文件：`/etc/systemd/system/tg-redroid-bot.service`

```bash
systemctl status tg-redroid-bot
systemctl restart tg-redroid-bot
redroid-manager bot-logs
```

Bot 菜单功能：

- 初始化应用
- 登录账号
- 账号列表
- 状态检查

登录成功账号会写入：

```bash
/root/redroid/data/accounts.sqlite3
```
