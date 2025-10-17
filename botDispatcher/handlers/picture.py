import botDispatcher.telegram_client
from botDispatcher.handler import Handler


class MessagePhoto(Handler):
    def canHandle(self, update: dict) -> bool:
        return 'message' in update and 'photo' in update['message']

    def handle(self, update: dict) -> bool:
        chat_id = update["message"]["chat"]["id"]
        photos = update["message"]["photo"]
        largest = max(photos, key=lambda p: p.get("file_size", 0))
        file_id = largest["file_id"]
        caption = update["message"].get("caption")
        botDispatcher.telegram_client.sendPicture(chat_id=chat_id, photo=file_id, **({"caption": caption} if caption and caption.strip() else {}))

        return False