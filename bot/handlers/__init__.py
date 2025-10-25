from bot.handlers.handler import Handler
from bot.handlers.ensure_user_exists import EnsureUserExists
from bot.handlers.db_handler import UpdateDB
from bot.handlers.menu_handler import MessageMenu
from bot.handlers.ping_handler import MessagePing


def getHandlers() -> list[Handler]:
    return [
        UpdateDB(),
        EnsureUserExists(),
        MessageMenu(),
        MessagePing(),
    ]