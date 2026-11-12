
import os
import re
import time
import logging

from flask import Flask, request, jsonify
from google import genai
from google.genai import types

# =====================================
# REPORTER HELPER AI
# =====================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
BACKUP_MODEL = "gemini-3.5-flash-lite"

SYSTEM_INSTRUCTION = (
    "Ты помощник редактора SAMP. "
    "Отвечай только на русском языке. "
    "Точно выполняй задачу пользователя. "
    "Не добавляй рекламу, ссылки и постороннюю информацию. "
    "Не придумывай факты, имена и числа."
)


# =====================================
# JSON RESPONSE
# =====================================

def json_response(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


# =====================================
# GEMINI REQUEST WITH FALLBACK
# =====================================

def ask_ai(prompt):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY не настроен в Railway")

    client = genai.Client(api_key=api_key)

    models = [MAIN_MODEL]

    if BACKUP_MODEL != MAIN_MODEL:
        models.append(BACKUP_MODEL)

    last_error = None

    try:
        for model in models:
            for attempt in range(2):
                try:
                    logger.info(
                        "Gemini request: model=%s attempt=%s",
                        model,
                        attempt + 1
                    )

                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            max_output_tokens=1800,
                            temperature=0.3
                        )
                    )

                    result = response.text

                    if not result or not result.strip():
                        raise RuntimeError("Gemini вернул пустой ответ")

                    logger.info("Gemini response successful: %s", model)

                    return result.strip()

                except Exception as error:
                    last_error = error

                    logger.exception(
                        "Gemini failed: model=%s attempt=%s",
                        model,
                        attempt + 1
                    )

                    if attempt == 0:
                        time.sleep(2)

            logger.warning("Switching to backup model: %s", model)

        raise RuntimeError(
            f"Все модели Gemini недоступны: {last_error}"
        )

    finally:
        client.close()


# =====================================
# HOME
# =====================================

@app.route("/", methods=["GET", "POST"])
def home():
    return json_response({
        "status": "online",
        "message": "SAMP Reporter AI is running!"
    })


# =====================================
# GRAMMAR CHECK
# =====================================

@app.route("/check_grammar", methods=["POST"])
def check_grammar():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return json_response({
                "status": "error",
                "message": "Неверный формат запроса"
            }, 400)

        text = data.get("text", "")

        if not isinstance(text, str) or not text.strip():
            return json_response({
                "status": "error",
                "message": "Введите текст"
            }, 400)

        if len(text) > 5000:
            return json_response({
                "status": "error",
                "message": "Текст слишком длинный"
            }, 400)

        prompt = (
            "Исправь орфографию, грамматику и пунктуацию "
            "следующего текста. Сохрани исходный смысл и стиль. "
            "Верни только исправленный текст, без объяснений:\n\n"
            + text
        )

        corrected = ask_ai(prompt)

        return json_response({
            "status": "success",
            "corrected": corrected
        })

    except Exception:
        logger.exception("Grammar error")

        return json_response({
            "status": "error",
            "message": "ИИ временно недоступен. Попробуй позже."
        }, 502)


# =====================================
# PR GENERATOR
# =====================================

@app.route("/generate_pr", methods=["POST"])
def generate_pr():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return json_response({
                "status": "error",
                "message": "Неверный формат запроса"
            }, 400)

        name = str(data.get("name", "")).strip()
        amount = str(data.get("sum", "")).strip()
        event = str(data.get("event", "")).strip()
        fraction = str(data.get("fraction", "")).strip()

        if not all([name, amount, event, fraction]):
            return json_response({
                "status": "error",
                "message": "Заполните все поля"
            }, 400)

        prompt = f"""
Создай ровно 3 разных RP-пиара для сервера SAMP.

ДАННЫЕ:
Отправитель: {name}
Сумма перевода: {amount}
Мероприятие: {event}
Фракция отправителя: {fraction}

ТРЕБОВАНИЯ:
1. Начинай каждый вариант по-разному.
2. Укажи отправителя и его фракцию.
3. Укажи точную сумму.
4. Укажи название мероприятия.
5. Пиши естественным русским языком.
6. Используй немного эмоций.
7. Не придумывай дополнительные факты.
8. Не добавляй объяснения.
9. Создай ровно три отдельных сообщения.

Разделяй варианты отдельной строкой:
---

Верни ровно 3 варианта.
"""

        result = ask_ai(prompt)

        templates = [
            item.strip()
            for item in re.split(r"(?m)^\s*---+\s*$", result)
            if item.strip()
        ]

        if len(templates) != 3:
            raise ValueError(
                f"Ожидалось 3 варианта, получено: {len(templates)}"
            )

        return json_response({
            "status": "success",
            "templates": templates
        })

    except Exception:
        logger.exception("PR generation error")

        return json_response({
            "status": "error",
            "message": "ИИ временно недоступен. Попробуй позже."
        }, 502)


# =====================================
# ERROR HANDLERS
# =====================================

@app.errorhandler(404)
def not_found(error):
    return json_response({
        "status": "error",
        "message": "Маршрут не найден"
    }, 404)


@app.errorhandler(413)
def too_large(error):
    return json_response({
        "status": "error",
        "message": "Запрос слишком большой"
    }, 413)


@app.errorhandler(Exception)
def internal_error(error):
    logger.exception("Unexpected server error")

    return json_response({
        "status": "error",
        "message": "Внутренняя ошибка сервера"
    }, 500)


# =====================================
# START
# =====================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
