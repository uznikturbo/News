import os

import requests
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
load_dotenv()


NEWSAPI_URL = "https://newsapi.org/v2/everything"
API_KEY = os.getenv("API_KEY")
DATABASE_URI = os.getenv("DATABASE_URI")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


db = SQLAlchemy(app)


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(300), nullable=False)


def fetch_news():
    params = {
        "q": "Україна",
        "language": "uk",
        "sortBy": "publishedAt",
        "apiKey": API_KEY,
        "pageSize": 20,
    }
    response = requests.get(NEWSAPI_URL, params=params)
    data = response.json()
    return data.get("articles", [])


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route("/")
def home():
    articles = fetch_news()
    return render_template("index.html", articles=articles)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        password = request.form.get("password")

        if not all([first_name, last_name, email, password]):
            flash("Будь ласка, заповніть всі поля", "error")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email вже зареєстрований", "error")
            return redirect(url_for("register"))

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=generate_password_hash(password),
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Реєстрація успішна! Тепер увійдіть", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Будь ласка, введіть email та пароль", "error")
            return redirect(url_for("login"))

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f"Ласкаво просимо, {user.first_name}!", "success")
            return redirect(url_for("profile"))

        flash("Неправильний email або пароль", "error")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Ви вийшли з акаунту", "info")
    return redirect(url_for("home"))


@app.route("/profile")
@login_required
def profile():
    user = User.query.get(current_user.id)
    return render_template("profile.html", user=user)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
