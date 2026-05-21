from flask import Flask
import os

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

@app.route("/")
def home():
    return "Crypto Bot Running 🚀"