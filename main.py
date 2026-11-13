
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

TIMEOUT = 60

SYSTEM_INSTRUCTION = """
Ты универсальный ИИ-помощник.
Отвечай на русском языке, если пользователь не попросил другой язык.
Выполняй поставленную задачу точно.
"""


def request_gemini(payload, json_mode=True):
    if not API_KEY:
        raise ValueError("На сервере не задан GEMINI_API_KEY")

    models = [MAIN_MODEL, BACKUP_MODEL]
    last_error = "Не удалось получить ответ от AI"

    for model in models:
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )

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

                if response.status_code in (404, 429, 503):
                    continue

                raise RuntimeError(last_error)

            data = response.json()
            candidates = data.get("candidates", [])

            if not candidates:
                last_error = "Gemini вернул пустой ответ"
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

            if json_mode:
                if result.startswith("```"):
                    result = result.replace("```json", "", 1)
                    result = result.replace("```", "").strip()

                parsed = json.loads(result)

                if not isinstance(parsed, dict):
                    raise ValueError("AI вернул некорректный JSON")

                return parsed

            return result

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


def ask_ai(prompt, temperature=0.7, max_tokens=1500):
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

    return request_gemini(payload, json_mode=True)


def ask_chat_ai(message, history):
    system_instruction = """
Ты настоящий универсальный ИИ-собеседник.

Правила:
- Общайся естественно, как обычный человек.
- Если тебе пишут «Привет», просто поздоровайся.
- Поддерживай нормальный разговор.
- Отвечай на вопросы, а не выдавай случайные заготовки.
- Помогай с Python, Lua, MoonLoader, SA-MP и другими темами.
- Учитывай предыдущие сообщения.
- Не выдумывай факты.
- Не повторяй постоянно одни и те же приветствия.
- Не добавляй JSON и технические метаданные.
- Отвечай на русском языке.
"""

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

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 2000
        }
    }

    return request_gemini(payload, json_mode=False)


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
# 2. GRAMMAR
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
- Не добавляй пояснения.
- Не сокращай текст без необходимости.

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
            raise ValueError("AI вернул некорректный текст")

        return jsonify({
            "status": "success",
            "corrected": corrected.strip()
        })

    except Exception:
        logger.exception("Grammar error")
        return error_response("Ошибка ИИ при проверке текста")


# ==========================================
# 3. PR GENERATOR
# ==========================================

@app.route("/generate_pr", methods=["POST"])
def generate_pr():
    try:
        data = get_data()

        name = str(data.get("name", "")).strip()
        amount = str(data.get("sum", "")).strip()
        event = str(data.get("event", "")).strip()
        fraction = str(data.get("fraction", "")).strip()

        if not all([name, amount, fraction]):
            return error_response(
                "Укажите ник, сумму и фракцию",
                400
            )

        prompt = f"""
Создай один красивый, эффектный PR-текст
для игрового SA-MP проекта.

Данные:
Фракция: {fraction}
Ник игрока: {name}
Сумма перевода: {amount}
Повод или мероприятие: {event if event else "Не указан"}

СТИЛЬ:
- Начни с яркой и цепляющей фразы.
- Красиво представь фракцию и игрока.
- Обязательно укажи точную сумму перевода.
- Добавь 2-3 горячие, эмоциональные фразы.
- Используй выразительные слова, например:
  «Вот это размах!», «Настоящая щедрость!»,
  «Такой поступок заслуживает внимания!»
- Не копируй эти примеры дословно каждый раз.
- Заверши красивой благодарностью.
- Можно использовать несколько уместных эмодзи.
- Текст должен выглядеть как готовое объявление,
  а не как сухой отчёт.
- Не придумывай дополнительные факты.
- Не меняй ник, сумму и название фракции.
- Не добавляй пояснений от себя.

Каждый запрос должен создавать новую оригинальную подачу.

Верни JSON:
{{"pr":"готовый PR-текст"}}
"""

        result = ask_ai(
            prompt,
            temperature=1.0,
            max_tokens=1500
        )

        pr = result.get("pr")

        if not isinstance(pr, str) or not pr.strip():
            raise ValueError("AI не вернул PR")

        pr = pr.strip()

        forbidden = [
            "from flask import",
            "import os",
            "def generate_pr",
            "app = Flask",
            "def ask_ai"
        ]

        if any(word in pr for word in forbidden):
            raise ValueError("AI вернул код вместо PR")

        return jsonify({
            "status": "success",
            "pr": pr
        })

    except Exception:
        logger.exception("PR generation error")
        return error_response("Не удалось сгенерировать PR")


# ==========================================
# 4. REAL AI CHAT
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

        reply = ask_chat_ai(message, history)

        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("ИИ вернул пустой ответ")

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
