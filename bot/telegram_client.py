import urllib.request
import os
import json
from dotenv import load_dotenv

load_dotenv()

def makeRequest(method: str, **param) -> dict:
    json_data = json.dumps(param).encode("utf-8")
    request = urllib.request.Request(
        method="POST",
        url=f"{os.getenv('TELEGRAM_BASE_URI')}/{method}",
        data=json_data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
    except Exception as e:
        raise RuntimeError(f"HTTP error calling {method}: {e}") from e

    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError(f"Telegram API error {method}: {body}")

    return data["result"]

def getUpdates(**params) -> list[dict]:
    return makeRequest('getUpdates', **params)

def sendMessage(chat_id: int, text: str, reply_markup: dict | None = None, parse_mode: str | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return makeRequest("sendMessage", **payload)

def editMessageText(chat_id: int, message_id: int, text: str, reply_markup: dict | None = None, parse_mode: str | None = None) -> dict:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return makeRequest("editMessageText", **payload)

def answerCallbackQuery(callback_query_id: str, text: str | None = None, show_alert: bool = False) -> dict:
    payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
    if text:
        payload["text"] = text
    return makeRequest("answerCallbackQuery", **payload)

def sendPicture(chat_id: int, photo: str, **params) -> dict:
    return makeRequest("sendPhoto", chat_id=chat_id, photo=photo, **params)

def getMe() -> dict:
    return makeRequest("getMe")

def answerCallbackQuery(callback_query_id: str, **kwargs) -> dict:
    """
    https://core.telegram.org/bots/api#answercallbackquery
    """
    return makeRequest("answerCallbackQuery", callback_query_id=callback_query_id, **kwargs)


def deleteMessage(chat_id: int, message_id: int) -> dict:
    """
    https://core.telegram.org/bots/api#deletemessage
    """
    return makeRequest("deleteMessage", chat_id=chat_id, message_id=message_id)

# "пишет..." / имитация активности
def sendChatAction(chat_id: int, action: str = "typing") -> dict:
    return makeRequest("sendChatAction", chat_id=chat_id, action=action)

# безопасное редактирование — игнорирует "message is not modified" и похожие 400
def safe_edit_message_text(chat_id: int, message_id: int, *, text: str, reply_markup: dict | None = None, parse_mode: str | None = None) -> bool:
    try:
        editMessageText(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except RuntimeError as e:
        s = str(e).lower()
        benign = (
            "message is not modified" in s or
            "message to edit not found" in s or
            "bad request: not found" in s or
            "message can't be edited" in s
        )
        if benign:
            return False
        raise

def getFile(file_id: str) -> dict:
    return makeRequest("getFile", file_id=file_id)