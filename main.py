import os
from flask import Flask, jsonify, request

app = Flask(__name__)


# Главная страница (проверка статуса)
@app.route("/", methods=["GET", "POST"])
def home():
  return jsonify(
      {"status": "online", "message": "SAMP Reporter API is running successfully!"}
  )


# Эндпоинт для проверки и исправления грамматики
@app.route("/check_grammar", methods=["POST"])
def check_grammar():
  try:
    data = request.get_json() or {}
    text = data.get("text", "")

    if not text:
      return jsonify(
          {"status": "error", "message": "Empty text provided"}
      ), 400

    # Здесь в будущем можно подключить ИИ-модель (OpenAI, GigaChat и т.д.)
    # Сейчас текст обрабатывается и возвращается обратно
    corrected_text = text.strip()

    return jsonify({"status": "success", "corrected": corrected_text})
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


# Эндпоинт для генерации вариантов рекламных эфиров (пиара)
@app.route("/generate_pr", methods=["POST"])
def generate_pr():
  try:
    data = request.get_json() or {}
    name = data.get("name", "Спонсор")
    sum_val = data.get("sum", "Приз")
    event = data.get("event", "МП")
    fraction = data.get("fraction", "Новости")

    # Шаблоны рекламных эфиров для радиоцентра
    templates = [
        f"• [{fraction}] • Уважаемые жители штата! Спонсор {name} проводит грандиозное мероприятие '{event}'.",
        (
            f"• [{fraction}] • Призовой фонд составляет целых {sum_val}! Ждем"
            f" каждого из вас на '{event}'!"
        ),
        (
            f"• [{fraction}] • Не упустите шанс проявить себя и выиграть ценные"
            f" призы в '{event}' от спонсора {name}!"
        ),
    ]

    return jsonify({"status": "success", "templates": templates})
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
  # Railway автоматически передает порт через переменные окружения
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)