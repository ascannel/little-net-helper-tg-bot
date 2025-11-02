# Little Net Helper — Telegram-бот для сетевых мини-проверок

**Зачем:** быстрые диагностики сети прямо из Telegram — без терминала и приложений. *Особенно удобно на iPhone!*
**Статус:** альфа-версия

Поддерживаемые команды (сокращённый набор):
- `🔁 Ping (ICMP)` 
- `🔎 DNS /ns` (nslookup) 
- `❓ WHOIS` 
- `🔐 TLS info` 
- `🧭 My IP`

---

## Как пользоваться (глазами пользователя)

### Главное меню
Команды: `/start` или `/menu`.

Экран: «Выберите действие» и инлайн-кнопки:
- `🔁 Ping (ICMP)`
- `🔎 DNS /ns`
- `❓ WHOIS`
- `🔐 TLS info`
- `🧭 My IP`

---

### Ping (ICMP)
1. Нажмите **`🔁 Ping (ICMP)`** — бот попросит **публичный IPv4 или домен**.  
2. Отправьте адрес (пример: `8.8.8.8` или `example.com`).  
3. Бот отправит результат по 10 ICMP-пакетам: передано/получено/потери, `rtt min/avg/max/σ`, и «хвост» вывода `ping`.  
4. Под ответом — кнопки:
   - **`🔁 Повторить`** (пинг другой цели)
   - **`🏠 Меню`** (вернуться в главное меню)

**Валидация:** понятные причины отказа (частные сети, loopback, неверный формат) + «**🔁 Ввести заново**».

---

### DNS /ns (nslookup) 
- Поток: выбрать тип записи → ввести домен → ответ со списком записей (A/AAAA/CNAME/MX/TXT/NS/PTR) и TTL.  
- Кнопки: **«Повторить»**, **«Сменить тип»**, **«Меню»**.  
- Длинные TXT — автоматически файл `.txt`.

### WHOIS
- Ввод: домен или IP/подсеть.  
- Ответ: регистратор/ORG, даты `created/expiry`, для IP — ASN/диапазон.  
- Длинный ответ — файлом `.txt`.

### TLS info
- Ввод: `host[:port]` (по умолчанию 443).  
- Ответ: `CN/SAN`, издатель, `notBefore/notAfter`, дней до истечения.

### My IP
- Без ввода.  
- Ответ: внешний IP сервера/бота.

---

## Архитектура (обзор)

### Поток обработки
Telegram (`getUpdates`)

│

▼

`long_polling.py` -> `dispatcher.py` -> `handlers/`* -> `telegram_client.py`

▲

│

`net_tools/`*

│

▼

`db_client.py` (SQLite)


### Паттерны
- **Dispatcher / Chain of Responsibility.**  
  Регистрируем упорядоченный список хэндлеров. Для каждого апдейта:
  - `canHandle(update) -> bool` — «мое ли событие?»  
  - `handle(update, state, data) -> HandlerStatus` — обработка шага.  
  `STOP` останавливает цепочку, `CONTINUE` передаёт следующему хэндлеру.

- **Finite State (пер-пользовательское состояние).**  
  `users.state` хранит текущий «режим» сценария (например, `PING_WAIT_TARGET`). Любой текст в этом режиме трактуется как ввод адреса.

- **Чистые исполнители (`net_tools/*`).**  
  Никакой завязки на Telegram; функции возвращают структурированный результат, который форматируется в хэндлере.

- **Тонкая обёртка над Telegram Bot API.**  
  `telegram_client.py`: `getUpdates`, `sendMessage`, `editMessageText`, `answerCallbackQuery` (+ при необходимости `sendDocument`).

### База данных
- **SQLite** (stdlib `sqlite3`) для MVP.
- Схема (минимум):
  ```sql
  CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    state       TEXT NOT NULL DEFAULT '',
    data        TEXT NOT NULL DEFAULT '{}'  -- JSON (напр., last_ping_target)
  );

  CREATE TABLE IF NOT EXISTS telegram_updates (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL                   -- JSON апдейта
  );

  PRAGMA journal_mode=WAL;
  CREATE INDEX IF NOT EXISTS idx_users_state ON users(state);

## Технические детали по командам
### Ping (ICMP)

- Как: системная утилита ping (-c 10 -n -W 2), парсинг сводки transmitted/received/loss и rtt min/avg/max/….
- Безопасность: запрещены частные/`loopback`/`link-local`/резервные диапазоны.
- Вывод: краткий summary + «хвост» оригинального `ping` в блоке кода; кнопки «`Повторить`/`Меню`».

### DNS /ns (nslookup)

- Как: dnspython (чистый Python), типы: `A`/`AAAA`/`CNAME`/`MX`/`TXT`/`NS`/`PTR`, настройка таймаутов/резолверов.
- Формат: компактный список значений (для `MX` — приоритет/хост; для `TXT` — тримминг или файл).

### WHOIS

- Как: `python-whois` (домены) и `ipwhois` (IP/ASN через RDAP).
- Формат: `registrar`/`ORG`, `created`/`updated`/`expiry`, `ASN`/`route`. Длинный вывод — `.txt`.

### TLS info

- Как: ssl + TCP-сокет: извлекаем серверный сертификат, парсим поля CN, SAN, issuer, сроки действия; считаем «дней до истечения».
- Формат: несколько строк, без «сырой» DER; при ошибке — читаемое описание (SNI/handshake/hostname mismatch).

### My IP

- Как : через публичный резолвер OpenDNS: запрос `myip.opendns.com` у `resolver1.opendns.com` (в `dnspython`),
- Формат: одна строка с IPv4.

## Зависимости (минимум для сокращённого набора)

- Обязательные:
  - `python-dotenv` — загрузка `.env`;
  - `dnspython` — DNS (`/ns`);
  - `python-whois` — WHOIS (домены);
  - `ipwhois` — WHOIS (IP/ASN).


Пример `requirements.txt`:
```
python-dotenv>=1.0
dnspython>=2.6
python-whois>=0.8
ipwhois>=1.2
```
## Установка и запуск

- Окружение:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- Конфигурация .env:
```
TELEGRAM_BASE_URI=https://api.telegram.org/bot<ВАШ_ТОКЕН>
SQLITE_DB_PATH=/абсолютный/путь/к/bot.db
```

- Создать/пересоздать БД:
```
python -m bot.recreate_database
```

- Запуск бота (polling):
```
python -m bot
```
## Безопасность и лимиты

- Ввод адресов/доменов валидируется; приватные/локальные диапазоны отклоняются.
- Таймауты на сетевые операции и ограничение размера вывода.
- Для стабильной работы используйте systemd/Docker-рестарт; polling-процесс должен постоянно работать.
