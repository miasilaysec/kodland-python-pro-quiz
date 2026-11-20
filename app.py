import os
import uuid
import numpy as np
from PIL import Image
from flask import Flask, render_template, request, session
from werkzeug.utils import secure_filename
from models import db, User, QuizAttempt, ImagePrediction

app = Flask(__name__)
app.config["SECRET_KEY"] = "kodland-python-pro-secret-key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(INSTANCE_DIR, "quiz.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

db.init_app(app)

with app.app_context():
    db.create_all()

QUESTIONS = [
    {
        "id": 1,
        "topic": "Sohbet Botu Otomasyonu (Discord.py)",
        "question": "Discord.py kütüphanesinde botun Discord sunucusuna başarıyla bağlandığını yakalamak için hangi olay (event) kullanılır?",
        "options": ["on_message", "on_ready", "on_connect_bot", "on_guild_join"],
        "answer": "on_ready",
    },
    {
        "id": 2,
        "topic": "Web Geliştirme (Flask)",
        "question": "Flask uygulamasında belirli bir URL yolunu (örneğin '/hakkinda') bir Python fonksiyonuna bağlamak için hangi dekoratör kullanılır?",
        "options": ["@app.path", "@app.url", "@app.route", "@app.view"],
        "answer": "@app.route",
    },
    {
        "id": 3,
        "topic": "Yapay Zeka Geliştirme",
        "question": "Denetimli öğrenmede (supervised learning) modelin eğitim verisindeki kalıpları aşırı ezberleyip yeni verilerde başarısız olmasına ne ad verilir?",
        "options": ["Underfitting", "Overfitting", "Tokenization", "Normalization"],
        "answer": "Overfitting",
    },
    {
        "id": 4,
        "topic": "Bilgisayar Görüşü (Computer Vision)",
        "question": "Görüntü işleme ve bilgisayar görüşünde pikselleri uzamsal yapısını koruyarak tarayan temel katman hangisidir?",
        "options": ["Convolutional Layer", "Embedding Layer", "Dropout Layer", "Attention Layer"],
        "answer": "Convolutional Layer",
    },
    {
        "id": 5,
        "topic": "Doğal Dil İşleme (NLP)",
        "question": "NLP projelerinde metni kelimelere veya anlamlı parçalara ayırma işlemine ne denir?",
        "options": ["Stemming", "Tokenization", "Pooling", "Rendering"],
        "answer": "Tokenization",
    },
]


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def classify_image(filepath):
    """Görselin kanal yoğunlukları ve kontrastından sınıf adı + güven skoru üretir."""
    with Image.open(filepath) as img:
        rgb_img = img.convert("RGB").resize((128, 128))
        arr = np.asarray(rgb_img, dtype=np.float32)

    mean_r, mean_g, mean_b = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
    brightness = arr.mean()
    contrast = float(arr.std())

    if brightness < 65:
        label = "Karanlik / Dusuk Isikli Sahne"
    elif mean_g > mean_r * 1.15 and mean_g > mean_b * 1.10:
        label = "Doga / Yesil Tonlu Goruntu"
    elif mean_b > mean_r * 1.15 and mean_b > mean_g * 1.05:
        label = "Gokyuzu / Su / Mavi Tonlu Goruntu"
    elif contrast > 60:
        label = "Yuksek Kontrastli / Detayli Goruntu"
    else:
        label = "Genel / Dengeli Goruntu"

    confidence = round(min(98.5, max(55.0, 60.0 + (contrast / 2.2))), 1)
    return label, confidence


def get_scores(username=None):
    best_user = User.query.order_by(User.best_score.desc()).first()
    general_best = round(best_user.best_score, 1) if best_user else 0.0

    personal_best = 0.0
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            personal_best = round(user.best_score, 1)

    return personal_best, general_best


@app.route("/", methods=["GET", "POST"])
def quiz():
    current_username = session.get("username", "")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if not username:
            username = "Anonim"

        session["username"] = username

        correct_count = 0
        total = len(QUESTIONS)

        for q in QUESTIONS:
            qid = q["id"]
            selected = request.form.get(f"question_{qid}")
            if selected == q["answer"]:
                correct_count += 1

        score = round((correct_count / total) * 100, 1)

        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, best_score=score)
            db.session.add(user)
            db.session.flush()
        else:
            if score > user.best_score:
                user.best_score = score

        attempt = QuizAttempt(
            user_id=user.id,
            score=score,
            correct_count=correct_count,
            total_questions=total,
        )
        db.session.add(attempt)
        db.session.commit()

        personal_best, general_best = get_scores(username)

        return render_template(
            "result.html",
            username=username,
            score=score,
            correct_count=correct_count,
            total_questions=total,
            personal_best=personal_best,
            general_best=general_best,
        )

    personal_best, general_best = get_scores(current_username)
    return render_template(
        "quiz.html",
        questions=QUESTIONS,
        username=current_username,
        personal_best=personal_best,
        general_best=general_best,
    )


@app.route("/vision", methods=["GET", "POST"])
def vision():
    current_username = session.get("username", "")
    prediction_record = None

    if request.method == "POST":
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            safe_name = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            file.save(save_path)

            label, confidence = classify_image(save_path)

            user_id = None
            if current_username:
                user = User.query.filter_by(username=current_username).first()
                if user:
                    user_id = user.id

            prediction_record = ImagePrediction(
                user_id=user_id,
                image_filename=unique_name,
                predicted_label=label,
                confidence=confidence,
            )
            db.session.add(prediction_record)
            db.session.commit()

    recent_predictions = ImagePrediction.query.order_by(ImagePrediction.created_at.desc()).limit(10).all()
    personal_best, general_best = get_scores(current_username)

    return render_template(
        "vision.html",
        prediction=prediction_record,
        recent_predictions=recent_predictions,
        personal_best=personal_best,
        general_best=general_best,
    )


if __name__ == "__main__":
    app.run(debug=True)
