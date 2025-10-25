from littleNetHelper.handlers.handler import Handler
from littleNetHelper.handlers.ensure_user_exists import EnsureUserExists
from littleNetHelper.handlers.db_handler import UpdateDB
from littleNetHelper.handlers.menu_handler import MessageMenu
from littleNetHelper.handlers.ping_handler import MessagePing


def getHandlers() -> list[Handler]:
    return [
        UpdateDB(),
        EnsureUserExists(),
        MessageMenu(),
        MessagePing(),
    ]