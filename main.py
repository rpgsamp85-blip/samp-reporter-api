import os
from flask import Flask, request, jsonify
import g4f

app = Flask(__name__)

# Промпт для проверки грамматики ИИ
GRAMMAR_PROMPT = (
    "Ты — строго профессиональный корректор текста. "
    "Исправь орфографические, пунктуационные и грамматические ошибки в следующем тексте. "
    "Расставь все запятые и точки по правилам русского языка. "
    "Убери сленг (например: лямов -> миллионов, кс -> CS, мни -> мне). "
    "В ответ выведи ТОЛЬКО исправленное предложение, без каких-либо комментариев и лишнего текста.\n\n"
    "Текст: "
)

# Промпт для создания вариантов пиара ИИ
PR_PROMPT = (
    "Ты — креативный репортер в GTA SA:MP. "
    "Напиши 3 разных, красивых, захватывающих и уникальных текста для эфира радио новостей. "
    "В тексте расскажи о спонсоре/взносе на мероприятие со следующими данными:\n"
    "- Ник игрока: {name}\n"
    "- Сумма: {sum}\n"
    "- Название МП: {event}\n"
    "- Фракция/Банда: {fraction}\n\n"
    "Раздели варианты символом '|||'. Не пиши ничего лишнего, только 3 варианта через '|||'."
)

@app.route('/check_grammar', methods=['POST'])
def check_grammar():
    try:
        data = request.get_json(force=True)
        user_text = data.get('text', '')
        
        if not user_text:
            return jsonify({"status": "error", "message": "Пустой текст"}), 400

        # Вызов ИИ для исправления
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4o,
            messages=[{"role": "user", "content": GRAMMAR_PROMPT + user_text}]
        )
        
        corrected = str(response).strip()
        return jsonify({"status": "success", "corrected": corrected})

    except Exception as e:
        # Резервный фолбэк, если ИИ временно недоступен
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/generate_pr', methods=['POST'])
def generate_pr():
    try:
        data = request.get_json(force=True)
        name = data.get('name', 'Игрок')
        sum_val = data.get('sum', 'Сумма')
        event = data.get('event', 'МП')
        fraction = data.get('fraction', 'Фракция')

        prompt = PR_PROMPT.format(name=name, sum=sum_val, event=event, fraction=fraction)
        
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4o,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw_text = str(response).strip()
        templates = [t.strip() for t in raw_text.split('|||') if t.strip()]
        
        # Если ИИ вывел меньше 3 вариантов, дополним базовыми
        if len(templates) < 3:
            templates = [
                f"Воу, воу, воу! Ко мне на банк поступил огромный перевод в размере {sum_val} от игрока {name} из {fraction} на проведение МП \"{event}\"!",
                f"Невероятная щедрость! Уважаемый игрок {name} ({fraction}) пополнил призовой фонд мероприятия \"{event}\" на сумму {sum_val}!",
                f"Спонсоры не перестают удивлять! {name} из {fraction} выделяет {sum_val} на организацию мероприятия \"{event}\"!"
            ]

        return jsonify({"status": "success", "templates": templates})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)