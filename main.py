
import os
import re
import json
import logging
import requests

from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

API_KEY = os.getenv("GEMINI_API_KEY")

MAIN_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
BACKUP_MODEL = os.getenv("GEMINI_BACKUP_MODEL", "gemini-3.5-flash-lite")

TIMEOUT = 15

SYSTEM_INSTRUCTION = """
Ты помощник для игроков SAMP.
Отвечай строго по заданию.
Не добавляй пояснения от себя.
Всегда возвращай корректный JSON.
Используй русский язык.
"""


def ask_ai(prompt):
    if not API_KEY:
        raise ValueError("На сервере не задан GEMINI_API_KEY")

    models = [MAIN_MODEL, BACKUP_MODEL]

    last_error = "Не удалось получить ответ от AI"

    for model in models:
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )

        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1200,
                "responseMimeType": "application/json"
            }
        }

        try:
            logger.info("AI request: %s", model)

            response = requests.post(
                url,
                params={"key": API_KEY},
                json=payload,
                timeout=(5, TIMEOUT)
            )

            if response.status_code != 200:
                last_error = (
                    f"Gemini HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
                logger.error("%s: %s", model, last_error)

                if response.status_code in (503, 429, 404):
                    continue

                raise RuntimeError(last_error)

            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                last_error = "Gemini вернул пустой ответ"
                logger.error(last_error)
                continue

            parts = candidates[0].get("content", {}).get("parts", [])
            result = "".join(
                part.get("text", "") for part in parts
            ).strip()

            if not result:
                last_error = "Gemini вернул пустой текст"
                continue

            parsed = json.loads(result)

            logger.info("AI response successful: %s", model)
            return parsed

        except requests.Timeout:
            last_error = f"Тайм-аут модели {model}"
            logger.error(last_error)
            continue

        except requests.RequestException as e:
            last_error = str(e)
            logger.exception("Connection error: %s", model)
            continue

        except (ValueError, KeyError, TypeError) as e:
            last_error = str(e)
            logger.exception("Invalid AI response: %s", model)
            continue

    raise RuntimeError(last_error)


@app.route("/", methods=["GET", "POST"])
def home():
    return jsonify({
        "status": "online",
        "message": "SAMP Reporter AI is running!"
    })


@app.route("/check_grammar", methods=["POST"])
def check_grammar():
    try:
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()

        if not text:
            return jsonify({
                "status": "error",
                "message": "Введите текст"
            }), 400

        if len(text) > 3000:
            return jsonify({
                "status": "error",
                "message": "Текст слишком длинный"
            }), 400

        prompt = f"""
Исправь грамматику и пунктуацию текста.
Сохрани первоначальный смысл и стиль.
Не добавляй новых предложений.

Текст:
{text}

Верни JSON строго такого вида:
{{"corrected":"исправленный текст"}}
"""

        result = ask_ai(prompt)
        corrected = result.get("corrected")

        if not isinstance(corrected, str) or not corrected.strip():
            raise ValueError("Некорректный ответ AI")

        return jsonify({
            "status": "success",
            "corrected": corrected.strip()
        })

    except Exception as e:
        logger.exception("Grammar error")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 502


@app.route("/generate_pr", methods=["POST"])
def generate_pr():
    try:
        data = request.get_json(silent=True) or {}

        name = str(data.get("name", "")).strip()
        amount = str(data.get("sum", "")).strip()
        event = str(data.get("event", "")).strip()
        fraction = str(data.get("fraction", "")).strip()

        if not all([name, amount, event, fraction]):
            return jsonify({
                "status": "error",
                "message": "Заполните все поля"
            }), 400

        prompt = f"""
Создай 5 вариантов PR-сообщения для SAMP.

Ник: {name}
Сумма: {amount}
Мероприятие: {event}
Фракция: {fraction}

Требования:
- Пиши на русском языке.
- Каждый вариант должен отличаться.
- Не придумывай дополнительные факты.
- Формулировки должны подходить для игрового RP-сервера.

Верни JSON строго такого вида:
{{"templates":["вариант 1","вариант 2","вариант 3","вариант 4","вариант 5"]}}
"""

        result = ask_ai(prompt)
        templates = result.get("templates")

        if not isinstance(templates, list) or not templates:
            raise ValueError("AI не вернул список шаблонов")

        templates = [
            str(item).strip()
            for item in templates
            if str(item).strip()
        ]

        if not templates:
            raise ValueError("Шаблоны пустые")

        return jsonify({
            "status": "success",
            "templates": templates
        })

    except Exception as e:
        logger.exception("PR generation error")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
