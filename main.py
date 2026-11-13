
import os
import json
import uuid
import logging
import threading
import requests

from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reporter_ai")

API_KEY = os.getenv("GEMINI_API_KEY")
MAIN_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
BACKUP_MODEL = os.getenv("GEMINI_BACKUP_MODEL", "gemini-3.5-flash-lite")

TIMEOUT = 90
executor = ThreadPoolExecutor(max_workers=4)

tasks = {}
tasks_lock = threading.Lock()

SYSTEM_INSTRUCTION = """
Ты универсальный ИИ-помощник.
Отвечай на русском языке, если пользователь не попросил другой язык.
Выполняй задачу точно.
"""


def update_task(task_id, **values):
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].update(values)


def create_task(task_type):
    task_id = str(uuid.uuid4())

    with tasks_lock:
        tasks[task_id] = {
            "id": task_id,
            "type": task_type,
            "status": "running",
            "text": "",
            "error": None
        }

    return task_id


def get_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)

        if task is None:
            return None

        return dict(task)


def stream_gemini(system_instruction, contents, temperature=0.8,
                  max_tokens=2000, on_text=None):
    if not API_KEY:
        raise RuntimeError("На сервере не задан GEMINI_API_KEY")

    models = [MAIN_MODEL, BACKUP_MODEL]
    last_error = "Не удалось получить ответ Gemini"

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }

    for model in models:
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:streamGenerateContent"
        )

        result = ""

        try:
            logger.info("Streaming Gemini request: %s", model)

            with requests.post(
                url,
                params={"key": API_KEY, "alt": "sse"},
                json=payload,
                stream=True,
                timeout=(10, TIMEOUT)
            ) as response:

                if response.status_code != 200:
                    last_error = (
                        f"Gemini HTTP {response.status_code}: "
                        f"{response.text[:400]}"
                    )
                    logger.error("%s", last_error)

                    if response.status_code in (404, 429, 500, 503):
                        continue

                    raise RuntimeError(last_error)

                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")

                    line = line.strip()

                    if not line.startswith("data:"):
                        continue

                    raw = line[5:].strip()

                    if not raw or raw == "[DONE]":
                        continue

                    try:
                        packet = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Invalid Gemini stream packet")
                        continue

                    candidates = packet.get("candidates", [])
                    if not candidates:
                        continue

                    parts = (
                        candidates[0]
                        .get("content", {})
                        .get("parts", [])
                    )

                    for part in parts:
                        chunk = part.get("text", "")

                        if chunk:
                            result += chunk

                            if on_text:
                                on_text(result)

            result = result.strip()

            if result:
                return result

            last_error = "Gemini вернул пустой ответ"

        except requests.Timeout:
            last_error = f"Тайм-аут модели {model}"
            logger.exception(last_error)

        except requests.RequestException as exc:
            last_error = str(exc)
            logger.exception("Gemini connection error")

        except Exception as exc:
            last_error = str(exc)
            logger.exception("Gemini generation error")

    raise RuntimeError(last_error)


def run_task(task_id, system_instruction, contents,
             temperature=0.8, max_tokens=2000,
             validator=None):
    try:
        def on_text(current_text):
            update_task(task_id, text=current_text)

        result = stream_gemini(
            system_instruction,
            contents,
            temperature,
            max_tokens,
            on_text
        )

        if validator:
            result = validator(result)

        if not isinstance(result, str) or not result.strip():
            raise ValueError("ИИ вернул пустой текст")

        update_task(
            task_id,
            text=result.strip(),
            status="done"
        )

    except Exception as exc:
        logger.exception("Task %s failed", task_id)

        update_task(
            task_id,
            status="error",
            error=str(exc)
        )


def start_task(task_type, system_instruction, contents,
               temperature=0.8, max_tokens=2000,
               validator=None):
    task_id = create_task(task_type)

    executor.submit(
        run_task,
        task_id,
        system_instruction,
        contents,
        temperature,
        max_tokens,
        validator
    )

    return jsonify({
        "status": "success",
        "task_id": task_id
    })


def clean_pr(text):
    text = text.strip()

    # Убираем случайные Markdown-блоки.
    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    # Не допускаем выдачу исходного программного кода.
    forbidden = [
        "from flask import",
        "import os",
        "import requests",
        "def generate_pr",
        "def ask_ai",
        "app = Flask",
        "app.run(",
        "def request_gemini",
        "GEMINI_API_KEY",
        "```python"
    ]

    lowered = text.lower()

    if any(item.lower() in lowered for item in forbidden):
        raise ValueError("Gemini вернул код вместо PR")

    return text


def error_response(message, status=502):
    return jsonify({
        "status": "error",
        "message": str(message)
    }), status


def get_data():
    return request.get_json(silent=True) or {}


# ==========================================
# HOME
# ==========================================

@app.route("/", methods=["GET", "POST"])
def home():
    return jsonify({
        "status": "online",
        "message": "SAMP Reporter AI is running"
    })


# ==========================================
# GRAMMAR
# ==========================================

@app.route("/check_grammar", methods=["POST"])
def check_grammar():
    try:
        data = get_data()
        text = str(data.get("text", "")).strip()

        if not text:
            return error_response("Введите текст", 400)

        if len(text) > 10000:
            return error_response("Текст слишком длинный", 400)

        prompt = f"""
Исправь орфографию, грамматику и пунктуацию.

Правила:
- Сохрани первоначальный смысл.
- Сохрани стиль автора.
- Не добавляй новых фактов.
- Не добавляй пояснений.
- Верни только исправленный текст.

Текст:
{text}
"""

        result = stream_gemini(
            SYSTEM_INSTRUCTION,
            [{"role": "user", "parts": [{"text": prompt}]}],
            temperature=0.2,
            max_tokens=3000
        )

        return jsonify({
            "status": "success",
            "corrected": result.strip()
        })

    except Exception:
        logger.exception("Grammar error")
        return error_response("Ошибка ИИ при проверке текста")


# ==========================================
# PR START
# ==========================================

@app.route("/generate_pr/start", methods=["POST"])
def generate_pr_start():
    try:
        data = get_data()

        name = str(data.get("name", "")).strip()
        amount = str(data.get("sum", "")).strip()
        event = str(data.get("event", "")).strip()
        fraction = str(data.get("fraction", "")).strip()

        if not name or not amount or not fraction:
            return error_response(
                "Укажите ник, сумму и фракцию",
                400
            )

        prompt = f"""
Напиши готовый рекламный PR для игрового SA-MP проекта.

Исходные данные:
Фракция: {fraction}
Ник игрока: {name}
Сумма перевода: {amount}
Мероприятие: {event if event else "Не указано"}

Требования:
- Самостоятельно придумай оригинальную подачу.
- Сделай красивое начало, основной текст и завершение.
- Обязательно укажи точные ник, фракцию и сумму.
- Добавь несколько эмоциональных, выразительных фраз.
- Используй абзацы и естественные переносы строк.
- Можно добавить уместные эмодзи.
- Не выдумывай дополнительные факты.
- Не меняй исходные данные.
- Не используй одинаковый шаблон для каждого запроса.
- Не пиши инструкций, пояснений или комментариев.
- Не возвращай JSON.
- Не возвращай программный код.
- Не используй Markdown-блоки кода.

Верни только готовый PR-текст.
"""

        return start_task(
            "pr",
            "Ты профессиональный автор рекламных текстов. " +
            "Возвращай только готовый PR, без кода и пояснений.",
            [{"role": "user", "parts": [{"text": prompt}]}],
            temperature=1.0,
            max_tokens=1200,
            validator=clean_pr
        )

    except Exception:
        logger.exception("PR start error")
        return error_response("Не удалось начать генерацию PR")


# ==========================================
# CHAT START
# ==========================================

@app.route("/chat/start", methods=["POST"])
def chat_start():
    try:
        data = get_data()

        message = str(data.get("message", "")).strip()
        history = data.get("history", [])

        if not message:
            return error_response("Введите сообщение", 400)

        if len(message) > 4000:
            return error_response("Сообщение слишком длинное", 400)

        if not isinstance(history, list):
            history = []

        contents = []

        for item in history[-16:]:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in ("user", "assistant"):
                continue

            if not isinstance(content, str) or not content.strip():
                continue

            contents.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": content[:3000]}]
            })

        contents.append({
            "role": "user",
            "parts": [{"text": message}]
        })

        system = """
Ты настоящий универсальный ИИ-собеседник.

- Общайся естественно.
- Отвечай на вопросы по существу.
- Учитывай историю разговора.
- Помогай с Python, Lua, MoonLoader и SA-MP.
- Не выдавай случайные заготовки.
- Не добавляй JSON и технические метаданные.
- Отвечай на русском языке, если не попросили другой.
"""

        return start_task(
            "chat",
            system,
            contents,
            temperature=0.8,
            max_tokens=2000
        )

    except Exception:
        logger.exception("Chat start error")
        return error_response("Не удалось начать общение с ИИ")


# ==========================================
# TASK STATUS / STREAM POLLING
# ==========================================

@app.route("/task/<task_id>", methods=["GET"])
def task_status(task_id):
    task = get_task(task_id)

    if task is None:
        return error_response("Задача не найдена", 404)

    return jsonify({
        "status": task["status"],
        "text": task["text"],
        "error": task["error"]
    })


# ==========================================
# START
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        threaded=True
    )
