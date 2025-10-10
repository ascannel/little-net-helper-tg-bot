import bot.telegram_client
import bot.db_client
import time

def main() -> None:
    nextUpdateOffset = 0
    try:
        while True:
            updates = bot.telegram_client.getUpdates(nextUpdateOffset)
            bot.db_client.persistUpdates(updates)
            for update in updates:
                if "message" in update and "text" in update["message"]:
                    bot.telegram_client.sendMessage(
                        chat_id=update["message"]["chat"]["id"],
                        text=update["message"]["text"],
                    )
                    print(".", end="", flush=True)
                else:
                    print("x", end="", flush=True)
                nextUpdateOffset = max(nextUpdateOffset, update["update_id"]+1)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nbb")


if __name__ == "__main__":
    main()