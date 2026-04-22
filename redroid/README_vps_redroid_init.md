# VPS 初始化脚本使用文档

这个文档对应的脚本是：`init_redroid_env.sh`

目标：在一台**刚重装的 Linux VPS** 上，尽量用一套脚本完成这些准备工作：

- 安装 Docker
- 准备 redroid 运行所需的内核模块 / 设备节点
- 安装 ADB
- 安装 Java
- 安装 Node.js / npm
- 安装 Appium + UiAutomator2 驱动
- 拉起 redroid 容器
- 连接 ADB
- 下载并安装 Telegram X 到 redroid
- 配置 Appium 自动化常用设置
- 生成 redroid / Appium 的 systemd unit
- 生成几个常用辅助命令

脚本面向这些主流系统家族：

- Debian / Ubuntu
- RHEL / Rocky / AlmaLinux / CentOS Stream
- Alpine

> 说明：
> - 脚本默认使用 **Android 12 64-bit only** 的 redroid 镜像，原因是这个版本在 Telegram X + Appium 的自动化链路里通常更稳，也更省资源。
> - 如果宿主机内核**没有 binder / hwbinder / vndbinder** 能力，redroid 依然可能无法正常运行；脚本会尽量自动处理，但内核能力本身无法凭空补出来。

---

## 一、脚本文件

初始化脚本：

```bash
init_redroid_env.sh
```

建议先把它上传到 VPS，例如：

```bash
scp init_redroid_env.sh root@YOUR_VPS_IP:/root/
```

远程获取脚本

```bash
wget https://raw.githubusercontent.com/413hy/tg-manager/telegram-x-over/redroid/init_redroid_env.sh
```

然后在 VPS 上执行：

```bash
cd /root
chmod +x /root/init_redroid_env.sh
bash /root/init_redroid_env.sh
```

---

## 二、默认行为

如果你**不传任何环境变量**，脚本默认会：

- 安装 Docker
- 安装 ADB / Java / Node.js / npm
- 安装 Appium + UiAutomator2
- 配置 `ANDROID_HOME` / `ANDROID_SDK_ROOT`
- 尝试加载 `binder_linux` / `ashmem_linux`
- 启动一个名为 `redroid12` 的容器
- 把 redroid 的 ADB 端口映射到宿主机 `5555`
- 自动通过 GitHub Releases API 下载**最新 Telegram X APK**并安装到 redroid
- 自动关闭动画、开启保持唤醒、尽量启用 Appium UnicodeIME
- 默认写入 `redroid.service` 和 `appium-redroid.service`
- 生成几个辅助命令到 `/usr/local/bin/`

---

## 三、最小使用方法

### 1）直接一把跑完

```bash
bash /root/init_redroid_env.sh
```

### 2）常见自定义参数

#### 自定义 redroid ADB 端口

```bash
REDROID_HOST_ADB_PORT=49301 bash /root/init_redroid_env.sh
```

#### 自定义容器名

```bash
REDROID_NAME=my-redroid bash /root/init_redroid_env.sh
```

#### 自定义 redroid 数据目录

```bash
REDROID_DATA_DIR=/opt/redroid/data bash /root/init_redroid_env.sh
```

#### 自定义 redroid 镜像

```bash
REDROID_IMAGE=redroid/redroid:13.0.0_64only-latest bash /root/init_redroid_env.sh
```

#### 不立即安装 Telegram X

```bash
INSTALL_TELEGRAM_X_NOW=0 bash /root/init_redroid_env.sh
```

#### 不立即启动 redroid（只装环境）

```bash
START_REDROID_NOW=0 bash /root/init_redroid_env.sh
```

#### 安装完后顺手启动 Appium

```bash
START_APPIUM_NOW=1 bash /root/init_redroid_env.sh
```

#### 不写入 systemd unit

默认会写入并启用 `redroid.service`。如果你只想生成脚本、不改 systemd：

```bash
INSTALL_SYSTEMD_UNITS=0 bash /root/init_redroid_env.sh
```

#### 不立即配置自动化设置

默认会在 redroid 启动后执行一次自动化配置，包括关闭动画、保持唤醒、配置 Appium Settings 权限和 UnicodeIME。

```bash
CONFIGURE_AUTOMATION_NOW=0 bash /root/init_redroid_env.sh
```

---

## 四、脚本完成后会生成的命令

### 0）准备 redroid 内核设备

```bash
/usr/local/sbin/prepare-redroid-kernel
```

它会尽量完成：

- 挂载 `/dev/binderfs`
- 加载 `binder_linux` / `ashmem_linux`
- 从 `/proc/misc` 动态创建 `/dev/binder`、`/dev/hwbinder`、`/dev/vndbinder`、`/dev/ashmem`
- 修正这些设备节点的权限

通常不需要手动运行，`/usr/local/bin/start-redroid` 和 `redroid.service` 会自动调用。

### 1）启动 redroid

```bash
/usr/local/bin/start-redroid
```

如果你要临时覆盖配置：

```bash
REDROID_HOST_ADB_PORT=49301 REDROID_NAME=redroid12 /usr/local/bin/start-redroid
```

### 2）连接 ADB

```bash
/usr/local/bin/connect-redroid-adb 5555
```

例如：

```bash
/usr/local/bin/connect-redroid-adb 49301
```

### 3）修复 ADB 端口被 thost9 改掉的问题

```bash
/usr/local/bin/fix-redroid-adb 5555
```

这个命令会：

- 停止 `com.hagaseca.thost9`
- 把容器内 `service.adb.tcp.port` 设回 `5555`
- 重启 `adbd`
- 重连宿主机 ADB

如果 `adb devices` 里 redroid 消失，或者容器仍在但 5555 端口不可用，优先跑这个命令。

### 4）安装 Telegram X

```bash
/usr/local/bin/install-telegram-x
```

它会：

- 调 GitHub Releases API 取最新 Telegram X release
- 自动挑一个 APK 资产
- 下载到：`/opt/redroid/apk/telegram-x-latest.apk`
- 安装到 redroid

### 5）配置 redroid 自动化环境

```bash
/usr/local/bin/configure-redroid-automation 5555
```

它会等待 redroid 启动完成，然后做这些设置：

- 关闭窗口、转场、Animator 动画
- 设置插电保持唤醒
- 放宽 hidden API policy，减少 UiAutomator2 兼容问题
- 给 `io.appium.settings` 授权
- 尝试启用 `io.appium.settings/.UnicodeIME`
- 打印 Telegram X / Appium 包和当前输入法列表

注意：`io.appium.settings` 通常由 Appium UiAutomator2 第一次创建 session 时安装。如果首次运行这个命令时还没有该包，先启动一次 Appium session，再重跑配置命令。

### 6）启动 Appium

```bash
/usr/local/bin/start-appium-redroid
```

默认参数：

- 监听地址：`127.0.0.1`
- 端口：`4723`
- 日志：`/var/log/appium.log`

如果你要改端口：

```bash
APPIUM_PORT=4725 /usr/local/bin/start-appium-redroid
```

### 7）systemd 服务

脚本默认写入：

```bash
systemctl status redroid.service
systemctl status appium-redroid.service
```

`redroid.service` 会调用：

- `/usr/local/bin/start-redroid`
- `/usr/local/bin/connect-redroid-adb`
- `/usr/local/bin/configure-redroid-automation`

`appium-redroid.service` 默认监听：

- 地址：`127.0.0.1`
- 端口：`4723`

常用命令：

```bash
systemctl start redroid.service
systemctl restart redroid.service
systemctl start appium-redroid.service
systemctl restart appium-redroid.service
journalctl -u redroid.service -n 100 --no-pager
journalctl -u appium-redroid.service -n 100 --no-pager
```

---

## 五、安装完成后的检查命令

### 检查 Docker

```bash
docker version
docker ps
```

### 检查 redroid 容器

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### 检查 ADB

```bash
adb connect 127.0.0.1:5555
adb devices
```

如果你改过端口，例如：

```bash
adb connect 127.0.0.1:49301
adb devices
```

### 检查 Appium

```bash
curl http://127.0.0.1:4723/status
```

### 检查 Telegram X 是否安装

```bash
adb -s 127.0.0.1:5555 shell pm list packages | grep -i thunderdog
```

### 检查 Appium 自动化依赖

```bash
adb -s 127.0.0.1:5555 shell pm list packages | grep -E 'thunderdog|appium'
adb -s 127.0.0.1:5555 shell ime list -s
```

正常情况下，包列表里应能看到：

- `org.thunderdog.challegram`
- `io.appium.settings`
- `io.appium.uiautomator2.server`
- `io.appium.uiautomator2.server.test`

如果输入法列表没有 `io.appium.settings/.UnicodeIME`，先创建一次 Appium session，再执行：

```bash
/usr/local/bin/configure-redroid-automation 5555
```

---

## 六、Appium 连接 redroid 的参考 capabilities

如果你后面要自己测 Appium，可以直接用这组：

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

如果宿主机端口不是 `5555`，把 `udid` 改掉即可。

例如：

```json
"appium:udid": "127.0.0.1:49301"
```

---

## 七、低配 VPS 的建议

如果你的 VPS 配置比较小，建议这样用：

1. 默认保留 `12.0.0_64only-latest`
2. 不要把 Appium 常驻启动，按需启动
3. 不要同时开太多 redroid 实例
4. `REDROID_DATA_DIR` 放到空间更充足的盘
5. 公网不要直接暴露 ADB 端口
6. 公网不要直接暴露 Appium 端口

比较推荐的访问方式是：

- ADB / Appium 只监听本地
- 通过 SSH 隧道转发

例如：

```bash
ssh -L 4723:127.0.0.1:4723 -L 5555:127.0.0.1:5555 root@YOUR_VPS_IP
```

---

## 八、常见问题

### 1）Docker 装好了，但 redroid 一启动就退出

先看：

```bash
dmesg -T | tail -n 100
docker logs redroid12
```

重点看内核有没有：

- `binder_linux`
- `/dev/binder`
- `/dev/hwbinder`
- `/dev/vndbinder`

### 2）ADB 连接不上

检查容器和端口：

```bash
docker ps
ss -lntp | grep 5555
adb connect 127.0.0.1:5555
adb devices
```

如果容器存在但 ADB 端口异常，执行：

```bash
/usr/local/bin/fix-redroid-adb 5555
```

如果 `adb devices` 同时出现多个设备，例如 `127.0.0.1:5555` 和 `emulator-5554`，所有自动化命令都必须显式传入 serial：

```bash
adb -s 127.0.0.1:5555 shell getprop sys.boot_completed
```

### 3）Appium 创建 session 报 `ANDROID_HOME` / `ANDROID_SDK_ROOT` 未设置

重新加载环境变量：

```bash
source /etc/profile.d/redroid-android-sdk.sh
```

或者直接这样启动 Appium：

```bash
ANDROID_HOME=/opt/android-sdk ANDROID_SDK_ROOT=/opt/android-sdk /usr/local/bin/start-appium-redroid
```

### 4）Telegram X 安装失败

先手动确认 redroid 已连上：

```bash
adb connect 127.0.0.1:5555
adb devices
```

再重跑：

```bash
/usr/local/bin/install-telegram-x
```

### 5）UnicodeIME 没有生效

先确认 Appium Settings 是否已安装：

```bash
adb -s 127.0.0.1:5555 shell pm list packages | grep io.appium.settings
```

没有安装时，启动一次 Appium UiAutomator2 session。安装后再跑：

```bash
/usr/local/bin/configure-redroid-automation 5555
adb -s 127.0.0.1:5555 shell ime list -s
```

如果仍然没有 UnicodeIME，可以先继续使用粘贴板或普通输入路径；中文、特殊符号、2FA 密码这类输入再优先通过 Appium Unicode keyboard 或 ADB clipboard 模块处理。

### 6）开机后 redroid 没自动起来

检查 systemd unit：

```bash
systemctl is-enabled redroid.service
systemctl status redroid.service
journalctl -u redroid.service -n 100 --no-pager
```

如果你执行脚本时设置过 `INSTALL_SYSTEMD_UNITS=0`，则不会写入 systemd unit，需要手动运行：

```bash
/usr/local/bin/start-redroid
/usr/local/bin/connect-redroid-adb 5555
/usr/local/bin/configure-redroid-automation 5555
```

---

## 九、推荐的首次执行顺序

如果你想最稳地从零开始：

```bash
bash /root/init_redroid_env.sh
/usr/local/bin/connect-redroid-adb 5555
/usr/local/bin/configure-redroid-automation 5555
/usr/local/bin/start-appium-redroid
curl http://127.0.0.1:4723/status
adb -s 127.0.0.1:5555 shell pm list packages | grep -i thunderdog
```

如果你用自定义端口，例如 `49301`：

```bash
REDROID_HOST_ADB_PORT=49301 bash /root/init_redroid_env.sh
/usr/local/bin/connect-redroid-adb 49301
/usr/local/bin/configure-redroid-automation 49301
/usr/local/bin/start-appium-redroid
curl http://127.0.0.1:4723/status
adb -s 127.0.0.1:49301 shell pm list packages | grep -i thunderdog
```

---

## 十、你后面最可能继续做的事

这个脚本跑完后，你基本就可以继续做：

- 用 Appium Inspector 看 Telegram X 元素
- 自动化登录 Telegram X
- 固化 `go_home()` / `open_drawer()` / `open_add_account()` 这类路由函数
- 接入你自己的 HTTP API / Bot 控制层

当前仓库的 `tgbot-api/` 已经接入 Telegram X 自动化接口和网页端；redroid 初始化完成后，优先确认这三个服务链路：

```bash
systemctl status redroid.service
systemctl status tgx-api.service
systemctl status tgx-bot.service
```
