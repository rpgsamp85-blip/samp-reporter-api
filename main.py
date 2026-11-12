
import os
import json
import re
import logging

from flask import Flask, jsonify, request
from g4f.client import Client

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

logging.basicConfig(level=logging.INFO)
client = Client()


def ask_ai(prompt):
    response = client.chat.completions.create(
        model="auto",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты профессиональный редактор. "
                    "Отвечай только на русском языке. "
                    "Не добавляй лишних объяснений."
                )
            },
            {"role": "user", "content": prompt}
        ],
        web_search=False
    )

    result = response.choices[0].message.content

    if not isinstance(result, str) or not result.strip():
        raise ValueError("AI returned an empty response")

    result = result.strip()

    unwanted = [
        "copilot moved to a new app",
        "install the new copilot app",
        "your copilot history and content",
        "sign in with the same account",
        "install now"
    ]

    if any(word in result.lower() for word in unwanted):
        raise ValueError("AI provider returned unrelated content")

    return result


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
        text = data.get("text", "")

        if not isinstance(text, str) or not text.strip():
            return jsonify({
                "status": "error",
                "message": "Введите текст"
            }), 400

        if len(text) > 5000:
            return jsonify({
                "status": "error",
                "message": "Текст слишком длинный"
            }), 400

        prompt = f"""
Исправь орфографию, грамматику и пунктуацию
в следующем русском тексте.

Правила:
- Сохрани первоначальный смысл.
- Не переписывай текст без необходимости.
- Исправь все ошибки.
- Верни только исправленный текст.
- Не добавляй комментарии.

Текст:
{text}
"""

        corrected = ask_ai(prompt)

        return jsonify({
            "status": "success",
            "corrected": corrected
        })

    except Exception:
        app.logger.exception("Grammar error")
        return jsonify({
            "status": "error",
            "message": "Не удалось получить ответ ИИ. Проверь Railway Deploy Logs."
        }), 502


@app.route("/generate_pr", methods=["POST"])
def generate_pr():
    try:
        data = request.get_json(silent=True) or {}

        name = str(data.get("name") or "Спонсор")[:200]
        sum_val = str(data.get("sum") or "Призы")[:200]
        event = str(data.get("event") or "Мероприятие")[:200]
        fraction = str(data.get("fraction") or "Новости")[:200]

        prompt = f"""
Ты профессиональный автор рекламных объявлений
для игрового проекта SAMP.

Создай ровно 3 разных рекламных объявления.

Информация:
Спонсор: {name}
Сумма или приз: {sum_val}
Мероприятие: {event}
Фракция: {fraction}

Требования:
- Свободный рекламный стиль.
- Красивые и привлекательные формулировки.
- Все три варианта должны отличаться.
- Используй предоставленную информацию.
- Можно использовать эмодзи и восклицательные знаки.
- Не придумывай дополнительные призы.
- Объявления должны быть готовы к публикации в чате SAMP.

Верни исключительно JSON:
{{"templates": ["Вариант 1", "Вариант 2", "Вариант 3"]}}
"""

        raw = ask_ai(prompt)
        raw = re.sub(r"```(?:json)?", "", raw).strip()

        start = raw.find("{")
        end = raw.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("AI returned invalid JSON")

        result = json.loads(raw[start:end + 1])
        templates = result.get("templates")

        if not isinstance(templates, list) or len(templates) != 3:
            raise ValueError("AI did not return exactly 3 templates")

        templates = [str(item).strip() for item in templates]

        if not all(templates):
            raise ValueError("AI returned an empty template")

        return jsonify({
            "status": "success",
            "templates": templates
        })

    except Exception:
        app.logger.exception("PR generation error")
        return jsonify({
            "status": "error",
            "message": "Не удалось создать объявления. Проверь Railway Deploy Logs."
        }), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
