
import os
import time
import logging

from flask import Flask, request, jsonify
from g4f.client import Client

# -------------------------------
# SETTINGS
# -------------------------------

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Client()

# -------------------------------
# JSON RESPONSE
# -------------------------------

def json_response(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


# -------------------------------
# AI REQUEST
# -------------------------------

def ask_ai(prompt):
    last_error = None

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="auto",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты профессиональный помощник редактора "
                            "SAMP. Отвечай только на русском языке. "
                            "Не добавляй рекламу, ссылки и постороннюю "
                            "информацию. Выполняй задачу точно."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                web_search=False
            )

            result = response.choices[0].message.content

            if not result or not result.strip():
                raise ValueError("ИИ вернул пустой ответ")

            result = result.strip()

            unwanted = [
                "copilot moved to a new app",
                "install now",
                "your copilot history",
                "sign in with the same account"
            ]

            if any(word in result.lower() for word in unwanted):
                raise ValueError("ИИ вернул посторонний текст")

            return result

        except Exception as error:
            last_error = error
            logger.exception("AI request failed (attempt %s)", attempt + 1)
            time.sleep(1)

    raise RuntimeError(
        "ИИ временно недоступен. Попробуй позже."
    ) from last_error


# -------------------------------
# HOME / CONNECTION
# -------------------------------

@app.route("/", methods=["GET", "POST"])
def home():
    return json_response({
        "status": "online",
        "message": "SAMP Reporter AI is running!"
    })


# -------------------------------
# GRAMMAR CHECK
# -------------------------------

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
            "следующего текста. Сохрани исходный смысл. "
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
            "message": "Не удалось проверить текст. Попробуй позже."
        }, 502)


# -------------------------------
# PR GENERATOR
# -------------------------------

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
Создай 3 разных варианта PR-отчёта для сервера SAMP.

Имя участника: {name}
Сумма: {amount}
Мероприятие: {event}
Фракция: {fraction}

Требования:
- Пиши грамотно на русском языке.
- Используй стиль игрового RP-отчёта.
- Каждый вариант должен отличаться.
- Не добавляй вымышленные доказательства.
- Верни только три варианта.
- Разделяй варианты строкой ---.
"""

        result = ask_ai(prompt)

        templates = [
            item.strip()
            for item in result.split("---")
            if item.strip()
        ]

        if len(templates) < 2:
            raise ValueError("ИИ вернул неправильный формат PR")

        return json_response({
            "status": "success",
            "templates": templates[:3]
        })

    except Exception:
        logger.exception("PR generation error")

        return json_response({
            "status": "error",
            "message": "Не удалось создать PR. Попробуй позже."
        }, 502)


# -------------------------------
# GLOBAL ERRORS
# -------------------------------

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


# -------------------------------
# START
# -------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
