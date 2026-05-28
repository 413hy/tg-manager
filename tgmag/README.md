# Telegram 多账号管理 Bot

这是一个面向公司自有或已授权 Telegram 测试账号的多账号管理 Bot 第一版实现。

## 功能范围

- Telegram Bot 指令面板，仅允许 `.env` 中配置的管理员使用。
- Telethon 用户账号登录、session 单个/批量导入导出、重连、资料管理、2FA 管理、SpamBot 查询、777000 服务通知监控。
- 批量发送、关注、反应、浏览量、转发测试，统一经过目标白名单和速率控制。
- PostgreSQL 持久化，敏感字段使用 Fernet 应用层加密。
- Telegram Mini App 内置管理面板，可在 Bot 内打开账号、批量任务、白名单和速率页面。
- Debian 12 `venv + systemd` 部署。

## 快速部署

```bash
cp .env.example .env
python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

把生成的密钥写入 `.env` 的 `FERNET_KEY`，并填写 `BOT_TOKEN`、`TG_API_ID`、`TG_API_HASH`、`ADMIN_IDS`、`DATABASE_URL`。

```bash
chmod +x ops/install_debian12.sh
sudo ./ops/install_debian12.sh
source .venv/bin/activate
alembic upgrade head
python -m app.main
```

systemd 部署：

```bash
sudo cp ops/systemd/tg-account-bot.service /etc/systemd/system/tg-account-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now tg-account-bot
sudo journalctl -u tg-account-bot -f
```

更完整的环境变量、venv、PostgreSQL、systemd 说明见 [DEPLOY.md](DEPLOY.md)。

## 常用指令

发送 `/cmd` 查看完整指令。第一次使用建议顺序：

1. `/status`
2. `/login`
3. `/accounts`
4. `/export_session <账号ID>`
5. `/export_sessions 1,3,5-8`
6. `/import_sessions`
7. `/spam <账号ID>`
8. `/service_monitor_on`

Mini App 入口：

```text
/app
```

启用前需要在 `.env` 中配置：

```env
MINI_APP_ENABLED=true
MINI_APP_HOST=127.0.0.1
MINI_APP_PORT=8080
MINI_APP_PUBLIC_URL=https://your-domain.example/mini-app
```

`MINI_APP_PUBLIC_URL` 必须是 Telegram 客户端可访问的 HTTPS 地址，可由 Nginx/Caddy 反向代理到本地 `MINI_APP_HOST:MINI_APP_PORT`。

批量互动测试前必须先添加授权目标：

```text
/target_allowlist add channel @your_test_channel 测试频道
/rate set batch 5 60 2 6
```

## 安全边界

本项目不包含绕过 Telegram 风控、规避限制、破解访问控制、隐藏来源或针对未授权目标的能力。批量测试功能用于公司自有或已书面授权目标。
