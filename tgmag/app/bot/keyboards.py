from __future__ import annotations

from app.db.models import TgAccount

from aiogram.types import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="系统状态"), KeyboardButton(text="账号管理")],
            [KeyboardButton(text="登录账号"), KeyboardButton(text="导入Session"), KeyboardButton(text="导出Session")],
            [KeyboardButton(text="批量任务"), KeyboardButton(text="目标与速率")],
            [KeyboardButton(text="监控中心"), KeyboardButton(text="隐藏键盘")],
        ],
        resize_keyboard=True,
        input_field_placeholder="选择一个管理入口",
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="取消当前操作")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="输入内容或取消",
    )


def cancel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="取消当前操作", callback_data="flow:cancel")]]
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove(remove_keyboard=True)


def force_reply(placeholder: str) -> ForceReply:
    return ForceReply(
        force_reply=True,
        input_field_placeholder=placeholder,
        selective=True,
    )


def home_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="系统状态", callback_data="nav:status"),
                InlineKeyboardButton(text="账号列表", callback_data="nav:accounts"),
            ],
            [
                InlineKeyboardButton(text="登录账号", callback_data="flow:login"),
                InlineKeyboardButton(text="导入 Session", callback_data="flow:import_session"),
            ],
            [
                InlineKeyboardButton(text="导出 Session", callback_data="flow:export_session"),
                InlineKeyboardButton(text="批量任务", callback_data="nav:batch"),
            ],
            [
                InlineKeyboardButton(text="目标与速率", callback_data="nav:settings"),
                InlineKeyboardButton(text="监控中心", callback_data="nav:monitor"),
            ],
            [
                InlineKeyboardButton(text="完整指令", callback_data="nav:help"),
            ],
        ]
    )


def account_button_label(account: TgAccount) -> str:
    if account.user_id:
        identity = str(account.user_id)
    elif account.username:
        identity = f"@{account.username}"
    else:
        identity = account.phone_masked
    return f"#{account.id} · {identity}"


def accounts_panel(accounts: list[TgAccount]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for account in accounts[:20]:
        rows.append([InlineKeyboardButton(text=account_button_label(account), callback_data=f"acct:{account.id}")])
    rows.append(
        [
            InlineKeyboardButton(text="刷新", callback_data="nav:accounts"),
            InlineKeyboardButton(text="返回", callback_data="nav:home"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_actions_panel(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="重连", callback_data=f"acct_action:reconnect:{account_id}"),
                InlineKeyboardButton(text="SpamBot", callback_data=f"acct_action:spam:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="详细信息", callback_data=f"acct_action:detail:{account_id}"),
                InlineKeyboardButton(text="刷新检测", callback_data=f"acct_action:check_detail:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="777000", callback_data=f"acct_action:service:{account_id}"),
                InlineKeyboardButton(text="2FA", callback_data=f"acct_action:twofa:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="隐私快照", callback_data=f"acct_action:privacy:{account_id}"),
                InlineKeyboardButton(text="资料设置", callback_data=f"acct_panel:profile:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="隐私设置", callback_data=f"acct_panel:privacy:{account_id}"),
                InlineKeyboardButton(text="2FA 设置", callback_data=f"acct_panel:twofa:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="导出 Session", callback_data=f"acct_action:export_session:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="返回列表", callback_data="nav:accounts"),
            ],
        ]
    )


def profile_edit_panel(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="改姓名", callback_data=f"acct_edit:name:{account_id}"),
                InlineKeyboardButton(text="改简介", callback_data=f"acct_edit:bio:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="改用户名", callback_data=f"acct_edit:username:{account_id}"),
                InlineKeyboardButton(text="头像设置", callback_data=f"acct_panel:avatar:{account_id}"),
            ],
            [InlineKeyboardButton(text="返回账号", callback_data=f"acct:{account_id}")],
        ]
    )


def avatar_panel(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="上传图片", callback_data=f"acct_edit:avatar_upload:{account_id}"),
                InlineKeyboardButton(text="服务器路径", callback_data=f"acct_edit:avatar_path:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="随机头像", callback_data=f"acct_action:avatar_random:{account_id}"),
                InlineKeyboardButton(text="返回资料", callback_data=f"acct_panel:profile:{account_id}"),
            ],
        ]
    )


def privacy_keys_panel(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="手机号", callback_data=f"privacy_key:phone:{account_id}"),
                InlineKeyboardButton(text="在线时间", callback_data=f"privacy_key:last_seen:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="头像", callback_data=f"privacy_key:profile_photo:{account_id}"),
                InlineKeyboardButton(text="转发来源", callback_data=f"privacy_key:forwards:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="通话", callback_data=f"privacy_key:calls:{account_id}"),
                InlineKeyboardButton(text="拉群", callback_data=f"privacy_key:groups:{account_id}"),
            ],
            [InlineKeyboardButton(text="返回账号", callback_data=f"acct:{account_id}")],
        ]
    )


def privacy_rules_panel(account_id: int, key_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="所有人", callback_data=f"privacy_set:{key_name}:everybody:{account_id}"),
                InlineKeyboardButton(text="联系人", callback_data=f"privacy_set:{key_name}:contacts:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="没有人", callback_data=f"privacy_set:{key_name}:nobody:{account_id}"),
                InlineKeyboardButton(text="返回", callback_data=f"acct_panel:privacy:{account_id}"),
            ],
        ]
    )


def twofa_panel(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="查询状态", callback_data=f"acct_action:twofa:{account_id}"),
                InlineKeyboardButton(text="设置 2FA", callback_data=f"twofa_edit:set:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="修改 2FA", callback_data=f"twofa_edit:change:{account_id}"),
                InlineKeyboardButton(text="配置邮箱", callback_data=f"twofa_edit:email:{account_id}"),
            ],
            [
                InlineKeyboardButton(text="关闭 2FA", callback_data=f"twofa_edit:disable:{account_id}"),
                InlineKeyboardButton(text="返回账号", callback_data=f"acct:{account_id}"),
            ],
        ]
    )


def batch_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="发送模板", callback_data="template:send"),
                InlineKeyboardButton(text="关注模板", callback_data="template:subscribe"),
            ],
            [
                InlineKeyboardButton(text="反应模板", callback_data="template:react"),
                InlineKeyboardButton(text="浏览模板", callback_data="template:view_post"),
            ],
            [
                InlineKeyboardButton(text="转发模板", callback_data="template:forward"),
                InlineKeyboardButton(text="导出 Session", callback_data="flow:export_session"),
            ],
            [InlineKeyboardButton(text="返回", callback_data="nav:home")],
        ]
    )


def settings_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="查看白名单", callback_data="settings:targets"),
                InlineKeyboardButton(text="查看速率", callback_data="settings:rate"),
            ],
            [
                InlineKeyboardButton(text="添加白名单模板", callback_data="template:target_add"),
                InlineKeyboardButton(text="设置速率模板", callback_data="template:rate_set"),
            ],
            [InlineKeyboardButton(text="返回", callback_data="nav:home")],
        ]
    )


def monitor_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="开启监听", callback_data="monitor:on"),
                InlineKeyboardButton(text="关闭监听", callback_data="monitor:off"),
            ],
            [
                InlineKeyboardButton(text="通知测试", callback_data="monitor:notify"),
                InlineKeyboardButton(text="系统状态", callback_data="nav:status"),
            ],
            [InlineKeyboardButton(text="返回", callback_data="nav:home")],
        ]
    )
