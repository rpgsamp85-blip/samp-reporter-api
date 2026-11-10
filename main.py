from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route("/")
def home():
  return jsonify({"status": "online", "message": "API is working!"})


@app.route("/check_grammar", methods=["POST"])
def check_grammar():
  try:
    data = request.get_json() or {}
    text = data.get("text", "")
    # Логика исправления текста
    corrected = text.strip()
    return jsonify({"status": "success", "corrected": corrected})
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/generate_pr", methods=["POST"])
def generate_pr():
  try:
    data = request.get_json() or {}
    name = data.get("name", "Спонсор")
    sum_val = data.get("sum", "Приз")
    event = data.get("event", "МП")
    fraction = data.get("fraction", "Новости")

    # Важно: ключ называется templates, чтобы скрипт его увидел
    templates = [
        f"• [{fraction}] • Уважаемые жители штата! Спонсор {name} проводит мероприятие '{event}'.",
        (
            f"• [{fraction}] • Призовой фонд составляет {sum_val}! Ждем всех на"
            f" '{event}'!"
        ),
        (
            f"• [{fraction}] • Не упустите шанс проявить себя и выиграть в"
            f" '{event}'!"
        ),
    ]

    return jsonify({"status": "success", "templates": templates})
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=10000)