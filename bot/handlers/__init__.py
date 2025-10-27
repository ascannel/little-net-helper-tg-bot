from bot.handlers.handler import Handler
from bot.handlers.ensure_user_exists import EnsureUserExists
from bot.handlers.db_handler import UpdateDB
from bot.handlers.menu_handler import MessageMenu
from bot.handlers.ping_handler import MessagePing
from bot.handlers.dns_handler import MessageDNS
from bot.handlers.whois_handler import MessageWhois
from bot.handlers.tls_handler import MessageTLS
from bot.handlers.myip_handler import MessageMyIP


def getHandlers() -> list[Handler]:
    return [
        UpdateDB(),
        EnsureUserExists(),
        MessageMenu(),
        MessageDNS(),
        MessageWhois(),
        MessageMyIP(),
        MessageTLS(),
        MessagePing(),
    ]