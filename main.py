
import os
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

TIMEOUT = 30

SYSTEM_INSTRUCTION = """
Ты универсальный ИИ-помощник.
Отвечай на русском языке, если пользователь не попросил другой язык.
Выполняй поставленную задачу точно.
"""


def ask_ai(prompt, temperature=0.7, max_tokens=1500):
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
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
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

                if response.status_code in (429, 503, 404):
                    continue

                raise RuntimeError(last_error)

            data = response.json()

            candidates = data.get("candidates", [])

            if not candidates:
                last_error = "Gemini вернул пустой ответ"
                logger.error(last_error)
                continue

            parts = candidates[0].get(
                "content", {}
            ).get("parts", [])

            result = "".join(
                part.get("text", "")
                for part in parts
            ).strip()

            if not result:
                last_error = "Gemini вернул пустой текст"
                continue

            parsed = json.loads(result)

            if not isinstance(parsed, dict):
                raise ValueError("AI вернул некорректный JSON")

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


def error_response(message, status=502):
    return jsonify({
        "status": "error",
        "message": str(message)
    }), status


def get_data():
    return request.get_json(silent=True) or {}


# ==========================================
# 1. CONNECTION CHECK
# ==========================================

@app.route("/", methods=["GET", "POST"])
def home():
    return jsonify({
        "status": "online",
        "message": "SAMP Reporter AI is running!"
    })


# ==========================================
# 2. GRAMMAR CHECK
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
Исправь орфографию, грамматику и пунктуацию текста.

Правила:
- Сохрани первоначальный смысл.
- Сохрани стиль автора.
- Не добавляй новых фактов.
- Не сокращай текст без необходимости.
- Не добавляй пояснения от себя.

Текст:
{text}

Верни JSON строго такого вида:
{{"corrected":"исправленный текст"}}
"""

        result = ask_ai(
            prompt,
            temperature=0.2,
            max_tokens=3000
        )

        corrected = result.get("corrected")

        if not isinstance(corrected, str) or not corrected.strip():
            raise ValueError("AI вернул некорректный исправленный текст")

        return jsonify({
            "status": "success",
            "corrected": corrected.strip()
        })

    except Exception:
        logger.exception("Grammar error")
        return error_response("Ошибка ИИ при проверке текста")


# ==========================================
# 3. GENERATE ONE PR
# ==========================================

@app.route("/generate_pr", methods=["POST"])
def generate_pr():
    try:
        data = get_data()

        name = str(data.get("name", "")).strip()
        amount = str(data.get("sum", "")).strip()
        event = str(data.get("event", "")).strip()
        fraction = str(data.get("fraction", "")).strip()

        if not all([name, amount, event, fraction]):
            return error_response("Заполните все поля", 400)

        prompt = f"""
Создай ОДИН оригинальный PR-текст на русском языке.

Данные:
Ник отправителя: {name}
Сумма перевода: {amount}
Мероприятие: {event}
Фракция отправителя: {fraction}

Требования:
- Самостоятельно придумай интересную подачу.
- Сделай текст выразительным, живым и подробным.
- Используй креативное начало и запоминающееся завершение.
- Органично упомяни предоставленные данные.
- Благодари отправителя, если это уместно.
- Не придумывай дополнительные факты, которых нет во входных данных.
- Не используй готовые шаблоны.
- Не копируй чужие тексты.
- Не добавляй пояснений от себя.
- Не навязывай строгий стиль репортёров.
- Не учитывай RP-ограничения при творческой подаче.

Каждый новый запрос должен создавать новый, отличающийся текст.

Верни JSON строго такого вида:
{{"pr":"полный текст PR"}}
"""

        result = ask_ai(
            prompt,
            temperature=0.9,
            max_tokens=1500
        )

        pr = result.get("pr")

        if not isinstance(pr, str) or not pr.strip():
            raise ValueError("AI не вернул PR")

        return jsonify({
            "status": "success",
            "pr": pr.strip()
        })

    except Exception:
        logger.exception("PR generation error")
        return error_response("Не удалось сгенерировать PR")


# ==========================================
# 4. AI CHAT
# ==========================================

@app.route("/chat", methods=["POST"])
def chat():
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

        conversation = []

        for item in history[-12:]:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in ("user", "assistant"):
                continue

            if not isinstance(content, str) or not content.strip():
                continue

            conversation.append(
                f"{'Пользователь' if role == 'user' else 'ИИ'}: "
                f"{content[:3000]}"
            )

        history_text = "\n".join(conversation)

        prompt = f"""
Ты общаешься с пользователем через чат внутри SA-MP.

Твои задачи:
- Отвечай на вопросы пользователя.
- Помогай с Lua, Python, MoonLoader, SA-MP и другими темами.
- Объясняй ошибки и помогай разбираться с кодом.
- Учитывай предыдущую переписку.
- Не выдумывай информацию.
- Отвечай понятно и по существу.
- Общайся естественно, без лишней официальности.
- Если вопрос непонятен, попроси уточнение.

Предыдущая переписка:
{history_text if history_text else "Переписки пока нет."}

Новое сообщение пользователя:
{message}

Ответь на последнее сообщение с учётом контекста.

Верни JSON строго такого вида:
{{"reply":"твой ответ пользователю"}}
"""

        result = ask_ai(
            prompt,
            temperature=0.7,
            max_tokens=2000
        )

        reply = result.get("reply")

        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("AI вернул пустой ответ")

        return jsonify({
            "status": "success",
            "reply": reply.strip()
        })

    except Exception:
        logger.exception("Chat error")
        return error_response("Не удалось получить ответ от ИИ")


# ==========================================
# START
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
    )
