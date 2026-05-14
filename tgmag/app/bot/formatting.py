from __future__ import annotations

from app.db.models import TgAccount


def account_line(account: TgAccount) -> str:
    username = f"@{account.username}" if account.username else "-"
    name = " ".join(part for part in [account.first_name, account.last_name] if part) or "-"
    status_labels = {
        "normal": "正常",
        "limited": "限制",
        "banned": "封禁",
        "unknown": "未知",
        "active": "未检测",
        "new": "未检测",
    }
    return f"#{account.id} {account.phone_masked} {username} {name} [{status_labels.get(account.status, account.status)}]"


COMMANDS = """可用指令
/start - 打开菜单
/cmd - 查看指令
/status - 系统状态
/accounts - 账号列表
/account <id> - 账号详情
/account_info <id> - 账号详细信息与 SpamBot 状态
/login - 手动登录/注册账号
/import_session - 导入 Telethon StringSession
/reconnect <id> - 重连账号
/reconnect_all - 重连所有 active 账号
/profile <id> - 查看账号资料
/set_name <id> <first> [last] - 设置姓名
/set_bio <id> <bio> - 设置简介
/set_username <id> <username> - 设置用户名
/set_avatar <id> <服务器文件路径> - 设置头像
/privacy <id> - 查看本地隐私快照
/set_privacy <id> <phone|last_seen|profile_photo|forwards|calls|groups> <everybody|contacts|nobody>
/check_2fa <id> - 查询 2FA 状态
/set_2fa <id> <new_password> [hint] - 设置 2FA
/change_2fa <id> <old_password> <new_password> [hint] - 修改 2FA
/disable_2fa <id> <old_password> - 关闭 2FA
/spam <id> - 查询 SpamBot
/spam_all - 批量查询 SpamBot
/service_check <id> - 拉取 777000 最近消息
/service_monitor_on - 重连账号并启用 777000 实时监听
/service_monitor_off - 断开实时监听
/notify_test - 测试管理员通知
/backup - 生成数据库备份命令提示
/target_allowlist add <type> <target> [title] - 添加授权目标
/target_allowlist remove <target> - 删除授权目标
/target_allowlist list - 查看授权目标
/rate show - 查看速率
/rate set <scope> <max_actions> <per_seconds> <jitter_min> <jitter_max>
/send <id> <target> <text> - 单账号发送
/send_all <start_id> <count> <target> <text> - 批量发送
/subscribe <id> <target> - 单账号关注
/subscribe_all <start_id> <count> <target> - 批量关注
/react <id> <target> <msg_id> <emoji> - 单账号反应
/react_all <start_id> <count> <target> <msg_id> <emoji> - 批量反应
/unreact <id> <target> <msg_id> - 取消反应
/view_post <id> <target> <msg_id> - 读取并增加浏览
/view_post_all <start_id> <count> <target> <msg_id> - 批量浏览
/forward <id> <source> <msg_id> <target> - 转发
/forward_all <start_id> <count> <source> <msg_id> <target> - 批量转发
"""
