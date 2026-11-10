from flask import Flask, request, jsonify

app = Flask(__name__)


# Главная страница (чтобы при открытии в браузере не было 404)
@app.route('/')
def home():
  return jsonify(
      {
          'status': 'online',
          'message': 'SAMP Reporter API is running successfully!',
      }
  )


@app.route('/check_grammar', methods=['POST'])
def check_grammar():
  data = request.get_json() or {}
  text = data.get('text', '')
  # Здесь твоя логика обработки ИИ для грамматики
  corrected_text = text  # Пример ответа
  return jsonify({'status': 'success', 'corrected': corrected_text})


@app.route('/generate_pr', methods=['POST'])
def generate_pr():
  data = request.get_json() or {}
  # Здесь твоя логика генерации пиара
  templates = [
      'Вариант рекламы 1: Проводим мероприятие...',
      'Вариант рекламы 2: Ждем всех на МП...',
  ]
  return jsonify({'status': 'success', 'templates': templates})


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=10000)