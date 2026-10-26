# FastAPI–Langflow: AI-калькулятор

Учебный MVP интеграции AI-агента, созданного в **Langflow Desktop**, с внешним HTTP API на **FastAPI** и веб-интерфейсом, созданным в **Lovable**.

Пользователь вводит два числа в веб-форме. FastAPI формирует выражение умножения и передаёт его AI-агенту Langflow. Агент использует инструмент **Calculator**, а API возвращает текст ответа и время обработки. Умножение выполняется на стороне агента, а не в браузере.

> **Статус:** работающий учебный прототип. Это не автономный production-сервис: Langflow Desktop и туннель ngrok должны быть запущены отдельно.

## Архитектура

```text
Пользователь
    |
    v
Lovable (веб-интерфейс)
    | POST /multiply (JSON)
    v
FastAPI на Render
    | HTTPS
    v
ngrok (туннель к локальному компьютеру)
    |
    v
Langflow Desktop (локально, порт 7860)
    |
    v
AI-агент (OpenAI gpt-4o-mini + инструмент Calculator)
    |
    v
Ответ Langflow -> FastAPI -> Lovable
```

**Роли компонентов:**

- **Lovable** — интерфейс с двумя числовыми полями, кнопкой вычисления, результатом и временем обработки.
- **FastAPI** — публичная точка входа, валидация JSON, вызов Langflow, преобразование ответа, CORS, ограничение частоты запросов и обработка ошибок.
- **Render** — размещение FastAPI и автоматическое развёртывание из GitHub.
- **ngrok** — HTTPS-доступ к локально работающему Langflow Desktop.
- **Langflow** — выполнение flow с AI-агентом и инструментом Calculator.
- **OpenAI gpt-4o-mini** — модель, используемая агентом в проверенной конфигурации.

Веб-интерфейс Lovable и конфигурация flow Langflow не входят в подтверждённый состав файлов этого репозитория; здесь размещён код FastAPI-сервиса.

## Технологии

Python, FastAPI, Uvicorn, HTTPX, Pydantic, python-dotenv, SlowAPI; Langflow Desktop, ngrok, Render, Lovable и OpenAI.

Зависимости Python перечислены в [requirements.txt](requirements.txt). Их версии в файле не зафиксированы.

## API

Публичный Swagger UI: **https://fastapi-langflow.onrender.com/docs**

| Метод | Маршрут | Назначение |
| --- | --- | --- |
| `GET` | `/` | `{"status":"up"}` |
| `GET` | `/health` | `{"status":"ok"}` |
| `POST` | `/multiply` | Передать числа агенту и получить результат |

`GET /health` подтверждает, что FastAPI отвечает, **но не проверяет** доступность ngrok, Langflow или OpenAI.

### POST /multiply

Тело запроса:

```json
{
  "numbers": [32, 14],
  "session_id": "demo-session-1"
}
```

| Поле | Тип | Обязательное | Описание |
| --- | --- | --- | --- |
| `numbers` | массив чисел | Да | Минимум два элемента; текущая схема **не ограничивает** максимальную длину массива |
| `session_id` | строка или `null` | Нет | Идентификатор сессии Langflow; если не задан, FastAPI создаёт UUID |

Пример вызова:

```bash
curl -X POST "https://fastapi-langflow.onrender.com/multiply" \
  -H "Content-Type: application/json" \
  -d '{"numbers":[32,14]}'
```

Пример **успешного ответа из тестирования** (время меняется от запроса к запросу):

```json
{
  "input": "32.0 * 14.0",
  "result_text": "448",
  "processing_time_ms": 3131.25
}
```

- `input` — строковое выражение, отправленное в Langflow.
- `result_text` — текст из ответа агента. Это **строка**, а не вычисленное FastAPI число; если ожидаемый путь к тексту отсутствует, текущий код может вернуть `null`.
- `processing_time_ms` — время обработки запроса в FastAPI, измеренное через `time.perf_counter()`; включает ожидание ответа Langflow.

FastAPI соединяет **все** переданные числа знаком `*`. Название `/multiply` не означает, что сервер принимает строго два аргумента.

### Ошибки и ограничения

| HTTP | Когда возникает |
| --- | --- |
| `422` | Некорректное тело запроса по схеме Pydantic |
| `429` | Превышен лимит `5/minute` для ключа, определяемого по `request.client.host` |
| `502` | Недоступен Langflow, ошибка upstream, ошибка его авторизации либо невалидный JSON |
| `504` | Тайм-аут HTTP-запроса к Langflow |

Примеры тел ошибок:

```json
{"detail":"Too many requests. Try again later."}
```

```json
{"detail":"Langflow service unavailable"}
```

```json
{"detail":"Langflow response timeout"}
```

Коды `429`, `502` и `504` могут отображаться в Swagger как **Undocumented**: обработка ошибок реализована, но эти ответы не описаны отдельно в OpenAPI-схеме.

## Запуск локально

Требования: Python с поддержкой используемых библиотек, запущенный Langflow Desktop с подготовленным flow и действующий ключ доступа к Langflow API.

1. Клонировать репозиторий и перейти в каталог проекта:

   ```powershell
   git clone https://github.com/Glazounov-AI/FastAPI-LangFlow.git
   cd FastAPI-LangFlow
   ```

2. Создать виртуальное окружение и установить зависимости:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

3. Создать локальный файл `.env` (он исключён из Git через `.gitignore`):

   ```dotenv
   LANGFLOW_URL=http://127.0.0.1:7860
   LANGFLOW_FLOW_ID=<ID_вашего_flow>
   LANGFLOW_API_KEY=<ключ_Langflow>
   LANGFLOW_INPUT_TYPE=chat
   LANGFLOW_OUTPUT_TYPE=chat
   LOVEABLE_ORIGINS=http://localhost:5173
   CORS_ALLOW_ALL=false
   ```

   Значения в угловых скобках — **заполнители**, а не рабочие ключи. Для доступа к Langflow на другом хосте или через ngrok задайте соответствующий URL. В коде обязательны `LANGFLOW_FLOW_ID` и `LANGFLOW_API_KEY`; для `LANGFLOW_URL` предусмотрено значение по умолчанию `http://127.0.0.1:7860`.

4. Запустить сервер:

   ```powershell
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

5. Открыть `http://127.0.0.1:8000/docs` и проверить `POST /multiply`.

При локальном запуске с прямым доступом к Langflow ngrok не нужен. При размещении FastAPI на Render, когда Langflow остаётся на локальном компьютере, необходим доступный извне HTTPS-туннель.

## Переменные окружения

| Переменная | Назначение |
| --- | --- |
| `LANGFLOW_URL` | Базовый URL Langflow; по умолчанию `http://127.0.0.1:7860` |
| `LANGFLOW_FLOW_ID` | ID запускаемого flow; обязателен |
| `LANGFLOW_API_KEY` | Ключ для запросов к Langflow; обязателен |
| `LANGFLOW_INPUT_TYPE` | Тип входа Langflow; по умолчанию `chat` |
| `LANGFLOW_OUTPUT_TYPE` | Тип выхода Langflow; по умолчанию `chat` |
| `LOVEABLE_ORIGINS` | Разрешённые CORS origins через запятую, **без завершающего /** |
| `CORS_ALLOW_ALL` | Если `true`, разрешает все origins; по умолчанию `false` |

> Имя `LOVEABLE_ORIGINS` сохранено **точно как в исходном коде**, включая написание `LOVEABLE`. Прежняя переменная `LOVEABLE_ORIGIN` больше не используется.

Пример формата списка origins:

```dotenv
LOVEABLE_ORIGINS=https://example.lovable.app,https://preview.example.lovable.app
```

Секреты OpenAI и Langflow не следует добавлять в Git или код браузера. Ключ OpenAI настраивается на стороне Langflow.

## Развёртывание на Render

FastAPI развёрнут как веб-сервис Render из ветки `main` этого репозитория.

Команда запуска в проверенной конфигурации:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Для работы сервиса на Render необходимо задать переменные окружения, прежде всего `LANGFLOW_URL` (публичный адрес ngrok), `LANGFLOW_FLOW_ID`, `LANGFLOW_API_KEY` и `LOVEABLE_ORIGINS`.

Если URL туннеля ngrok изменился, необходимо обновить `LANGFLOW_URL` на Render. После обновления переменных или кода нужно дождаться завершения развёртывания и проверить запрос.

На бесплатном тарифе Render возможна задержка первого обращения после периода простоя.

## Реализованная защита

- **Валидация:** Pydantic проверяет типы полей и минимальную длину `numbers`.
- **CORS:** доступ из браузера разрешён для перечисленных в `LOVEABLE_ORIGINS` адресов; это **не аутентификация**.
- **Rate limiting:** SlowAPI ограничивает `POST /multiply` пятью запросами в минуту на `request.client.host`. Счётчики хранятся в памяти процесса.
- **Обработка ошибок:** исключения HTTPX преобразуются в контролируемые ответы FastAPI без передачи upstream-ответов целиком.
- **Тайм-ауты HTTPX:** `connect=10`, `read=60`, `write=10`, `pool=10` секунд. `read` — тайм-аут ожидания данных, **не общий лимит длительности запроса**.
- **Ключи:** передаются сервером FastAPI к Langflow, а не из Lovable. FastAPI сначала пробует заголовок `Authorization: Bearer`, при ответе `401/403` — `x-api-key`.

## Что было проверено

В ходе разработки выполнены следующие ручные проверки:

1. Успешный вызов `POST /multiply` с числами `32` и `14`: агент вернул `448`.
2. Отображение результата и времени обработки в веб-интерфейсе Lovable.
3. Исправление CORS для разных origins предварительного просмотра Lovable и успешный повторный вызов.
4. Проверка обработки недоступного Langflow: контролируемая ошибка вместо необработанного исключения.
5. Искусственно вызванный тайм-аут: HTTP `504`; после теста восстановлено `read=60`.
6. Локальная проверка SlowAPI: при временном лимите `1/minute` повторный запрос получил `429`.
7. Проверка на Render: при лимите `5/minute` шестой запрос за минуту отклонён.
8. Диагностика `request.client.host` на Render при двух разных подключениях: наблюдались разные публичные IPv4-адреса; временное логирование IP затем удалено.

Это результаты ручного тестирования, **не автоматизированный тестовый набор**.

## Известные ограничения и дальнейшее развитие

- Langflow Desktop и ngrok работают вне Render. При остановке компьютера, Langflow или туннеля вычисления недоступны.
- Публичный `POST /multiply` не требует авторизации. CORS не препятствует прямым HTTP-запросам.
- In-memory rate limiting не синхронизируется между несколькими экземплярами и сбрасывается при перезапуске. Для масштабирования потребуется общее хранилище счётчиков, например Redis.
- Корректное разделение двух клиентов по IP наблюдалось, но устойчивость к подмене прокси-заголовков отдельно не проверялась.
- `numbers` не ограничен двумя значениями или верхней границей длины; числовые диапазоны и конечность значений дополнительно не ограничены.
- Отсутствие ожидаемого поля текста в валидном JSON Langflow может приводить к `result_text: null` при HTTP 200.
- Нет полноценной аутентификации, постоянного журнала запросов, метрик, алертов, контроля стоимости LLM и автоматизированных тестов.
- `/health` не проверяет зависимости.
- Telegram-бот рассматривался как возможный интерфейс: он мог бы преобразовывать текст сообщения в тот же JSON `POST /multiply`, но **Telegram-интеграция в рамках данного проекта не реализована**.

## Ссылки

- [GitHub — исходный код FastAPI](https://github.com/Glazounov-AI/FastAPI-LangFlow)
- [FastAPI — Swagger UI на Render](https://fastapi-langflow.onrender.com/docs)
- [FastAPI — health endpoint](https://fastapi-langflow.onrender.com/health)

---

Проект разработан как учебная практическая работа по интеграции AI-агента Langflow с FastAPI и веб-интерфейсом.
