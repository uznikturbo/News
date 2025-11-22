import os

import requests
from dotenv import load_dotenv
from flask import Flask, render_template

app = Flask(__name__)
load_dotenv()


NEWSAPI_URL = "https://newsapi.org/v2/everything"
API_KEY = os.getenv("API_KEY")


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


@app.route("/")
def home():
    articles = fetch_news()
    return render_template("index.html", articles=articles)


if __name__ == "__main__":
    app.run(debug=True)
