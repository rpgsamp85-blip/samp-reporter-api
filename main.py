
import os
import time
import logging
import re

from flask import Flask, request, jsonify
from g4f.client import Client

# =====================================
# REPORTER HELPER AI
# =====================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Client()


# =====================================
# JSON RESPONSE
# =====================================

def json_response(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


# =====================================
# AI REQUEST
# =====================================

def ask_ai(prompt):
    last_error = None

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="auto",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты помощник редактора SAMP. "
                            "Отвечай строго на русском языке. "
                            "Выполняй задачу пользователя. "
                            "Не добавляй ссылки, рекламу и постороннюю информацию. "
                            "Не меняй факты, имена и числа."
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

            if not isinstance(result, str) or not result.strip():
                raise ValueError("ИИ вернул пустой ответ")

            result = result.strip()

            # Удаляем возможные блоки Markdown
            result = re.sub(r"^```(?:text|markdown)?\s*", "", result, flags=re.I)
            result = re.sub(r"\s*```$", "", result)

            # Проверяем явно посторонние ответы
            unwanted = [
                "copilot moved to a new app",
                "install now",
                "your copilot history",
                "sign in with the same account"
            ]

            if any(word in result.lower() for word in unwanted):
                raise ValueError("Провайдер вернул посторонний текст")

            return result.strip()

        except Exception as error:
            last_error = error
            logger.exception("AI request failed, attempt %s", attempt + 1)

            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(
        "AI provider failed after 3 attempts"
    ) from last_error


# =====================================
# HOME / SERVER STATUS
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
            "Верни только исправленный текст:\n\n"
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
        }, 503)


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

СТИЛЬ:
Пиши как игрок, который эмоционально сообщает
о поступлении денег на банковский счёт для мероприятия.

Пример стиля:
"Воу!! Ко мне на банк поступил перевод от латинца
из банды Aztecas в размере 20.000.000$!
Деньги отправлены на МП «CS»! Вот это поддержка!"

ТРЕБОВАНИЯ:
1. Начинай варианты по-разному.
2. Укажи отправителя и его фракцию.
3. Укажи точную сумму перевода.
4. Укажи название мероприятия.
5. Используй живой русский язык.
6. Можно немного эмодзи и восклицаний.
7. Не придумывай дополнительные факты.
8. Не используй сухой официальный стиль.
9. Каждый вариант должен быть отдельным сообщением.
10. Не добавляй объяснения.

Разделяй варианты строкой:
---

Верни ровно 3 варианта.
"""

        result = ask_ai(prompt)

        templates = [
            item.strip()
            for item in re.split(r"\n\s*---+\s*\n", result)
            if item.strip()
        ]

        # Запасной вариант разделения, если AI использовал
        # разделитель без переносов строк
        if len(templates) < 3:
            templates = [
                item.strip()
                for item in result.split("---")
                if item.strip()
            ]

        if len(templates) < 3:
            raise ValueError("ИИ вернул меньше трёх вариантов пиара")

        return json_response({
            "status": "success",
            "templates": templates[:3]
        })

    except Exception:
        logger.exception("PR generation error")

        return json_response({
            "status": "error",
            "message": "ИИ временно недоступен. Попробуй позже."
        }, 503)


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
