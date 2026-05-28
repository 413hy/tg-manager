# 部署说明

本文档以 Debian 12、Python venv、PostgreSQL、systemd 为目标环境。

## 1. 系统依赖

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip build-essential libpq-dev postgresql-client
```

项目声明 Python 版本为 `>=3.11`。生产环境建议使用 Python 3.11 或更新版本。

## 2. 数据库

示例 PostgreSQL 初始化：

```bash
sudo -u postgres psql
```

```sql
CREATE USER tg_bot WITH PASSWORD 'change_me';
CREATE DATABASE tg_account_bot OWNER tg_bot;
GRANT ALL PRIVILEGES ON DATABASE tg_account_bot TO tg_bot;
```

## 3. venv

```bash
cd /opt/tg-account-bot
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip wheel
pip install -r requirements.txt
```

venv 相关约定：

- systemd 使用 `.venv/bin/python -m app.main` 启动。
- 手动执行管理命令前先运行 `. .venv/bin/activate`。
- 不要提交 `.venv/` 到仓库。

## 4. 环境变量

```bash
cp .env.example .env
```

生成 Fernet 密钥：

```bash
. .venv/bin/activate
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

`.env` 字段说明：

- `BOT_TOKEN`: Telegram BotFather 提供的 Bot Token。
- `TG_API_ID`: Telegram API ID。
- `TG_API_HASH`: Telegram API Hash。
- `ADMIN_IDS`: 允许使用 Bot 的 Telegram 用户 ID，多个用英文逗号分隔。
- `DATABASE_URL`: SQLAlchemy asyncpg 连接串。
- `FERNET_KEY`: Fernet 密钥，用于加密 session、手机号、2FA 等敏感信息。
- `SESSION_DIR`: 本地 session 文件目录，默认 `./data/sessions`。
- `BACKUP_DIR`: 备份目录，默认 `./data/backups`。
- `DEFAULT_RATE_MAX_ACTIONS`: 默认批量速率窗口内最大动作数。
- `DEFAULT_RATE_PER_SECONDS`: 默认速率窗口秒数。
- `DEFAULT_JITTER_MIN`: 批量动作最小随机等待秒数。
- `DEFAULT_JITTER_MAX`: 批量动作最大随机等待秒数。
- `SERVICE_MONITOR_INTERVAL_SECONDS`: 服务通知监控间隔。
- `LOG_LEVEL`: 日志级别。
- `MINI_APP_ENABLED`: 是否启动内置 Mini App HTTP 服务。
- `MINI_APP_HOST`: Mini App HTTP 服务监听地址，生产环境建议监听 `127.0.0.1` 后由反向代理公开。
- `MINI_APP_PORT`: Mini App HTTP 服务监听端口。
- `MINI_APP_PUBLIC_URL`: Telegram Bot 按钮打开的公开 HTTPS 地址，路径应指向 `/mini-app`。
- `MINI_APP_AUTH_MAX_AGE_SECONDS`: Telegram initData 最大有效时间。

不要把真实 `.env`、session、数据库备份上传到仓库。

## 4.1 Telegram Mini App

Mini App 与 Bot 同进程启动，默认路径为 `/mini-app`，API 路径为 `/mini-app/api/*`。启用示例：

```env
MINI_APP_ENABLED=true
MINI_APP_HOST=127.0.0.1
MINI_APP_PORT=8080
MINI_APP_PUBLIC_URL=https://your-domain.example/mini-app
```

Telegram 客户端要求 Web App 使用可访问的 HTTPS 地址。生产环境可用 Nginx 或 Caddy 将公网 HTTPS 反向代理到：

```text
http://127.0.0.1:8080/mini-app
```

Mini App 后端会校验 `Telegram.WebApp.initData` 签名，并复用 `.env`/数据库中的管理员白名单。

## 5. 数据库迁移

```bash
. .venv/bin/activate
alembic upgrade head
```

应用启动时也会执行 `Base.metadata.create_all`，但生产环境仍建议显式跑 Alembic。

## 6. 前台启动

```bash
. .venv/bin/activate
python -m app.main
```

## 7. systemd

复制服务文件：

```bash
sudo cp ops/systemd/tg-account-bot.service /etc/systemd/system/tg-account-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now tg-account-bot
```

查看状态和日志：

```bash
sudo systemctl status tg-account-bot --no-pager
sudo journalctl -u tg-account-bot -f
```

如果部署目录不是 `/opt/tg-account-bot`，请同步修改 `ops/systemd/tg-account-bot.service` 中的：

- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

## 8. 备份

```bash
mkdir -p data/backups
pg_dump 'postgresql://tg_bot:change_me@127.0.0.1:5432/tg_account_bot' \
  | gzip > data/backups/tg_account_bot_$(date +%F_%H%M%S).sql.gz
```

数据库内 session、2FA、手机号等字段为加密值，`FERNET_KEY` 必须单独安全保存。
