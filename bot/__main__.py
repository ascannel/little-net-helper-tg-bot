import sys
import platform

from bot.long_polling import startLongPolling
from bot.handlers.db_handler import UpdateDB
from bot.dispatcher import Dispatcher
from bot.handlers import getHandlers

def _warn_if_not_linux() -> None:
    import os
    if os.getenv("LNH_SUPPRESS_OS_WARNING") == "1":
        return
    system = platform.system().lower()
    if system != "linux":
        print(
            f"Attention required: сstable workload is quaranteed only on Linux-based systems.\n"
            f"Your current platform is: {platform.system()} {platform.release()}.\n",
            file=sys.stderr,
        )

if __name__ == "__main__":
    try:
        dispatcher = Dispatcher()
        dispatcher.addHandlers(*getHandlers())
        startLongPolling(dispatcher)
    except KeyboardInterrupt:
        print("\nbb")