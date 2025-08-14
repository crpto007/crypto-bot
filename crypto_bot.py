# =========================
# IMPORTS
# =========================
import logging
import os
import threading
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackContext, CallbackQueryHandler
)
import requests
import json
import time
import datetime
import random

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# FLASK APP FOR UPTIME
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 CryptoTracker Bot is running!", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

# =========================
# BOT TOKEN
# =========================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

# =========================
# DATA STRUCTURES
# =========================
watchlists = {}     # user_id -> list of symbols
portfolio = {}      # user_id -> dict(symbol: amount)
alerts = {}         # user_id -> list of alerts
auto_replies = {}   # user_id -> dict(keyword: reply)
quiz_questions = [
    {
        "question": "What does 'HODL' stand for in crypto slang?",
        "options": ["Hold On for Dear Life", "Hold On, Don't Lose", "Hope On, Deal Later", "High Order Demand List"],
        "answer": 0
    },
    {
        "question": "Which is the first cryptocurrency?",
        "options": ["Ethereum", "Bitcoin", "Litecoin", "Dogecoin"],
        "answer": 1
    }
]
active_quiz = {}    # user_id -> current quiz index

# =========================
# HELPER FUNCTIONS
# =========================

def get_crypto_price(symbol):
    """Fetch current USD price of a crypto from CoinGecko"""
    symbol = symbol.lower()
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        if symbol in data:
            return data[symbol]['usd']
        else:
            return None
    except Exception as e:
        logger.error(f"Price fetch error for {symbol}: {e}")
        return None

def add_to_watchlist(user_id, symbol):
    symbol = symbol.lower()
    if user_id not in watchlists:
        watchlists[user_id] = []
    if symbol not in watchlists[user_id]:
        watchlists[user_id].append(symbol)
        return True
    return False

def remove_from_watchlist(user_id, symbol):
    symbol = symbol.lower()
    if user_id in watchlists and symbol in watchlists[user_id]:
        watchlists[user_id].remove(symbol)
        return True
    return False

def format_watchlist(user_id):
    if user_id not in watchlists or not watchlists[user_id]:
        return "📌 Your watchlist is empty."
    msg = "📊 **Your Watchlist:**\n"
    for symbol in watchlists[user_id]:
        price = get_crypto_price(symbol)
        if price:
            msg += f"• {symbol.capitalize()}: ${price}\n"
        else:
            msg += f"• {symbol.capitalize()}: price unavailable\n"
    return msg

def add_to_portfolio(user_id, symbol, amount):
    symbol = symbol.lower()
    if user_id not in portfolio:
        portfolio[user_id] = {}
    if symbol in portfolio[user_id]:
        portfolio[user_id][symbol] += amount
    else:
        portfolio[user_id][symbol] = amount

def format_portfolio(user_id):
    if user_id not in portfolio or not portfolio[user_id]:
        return "💼 Your portfolio is empty."
    msg = "💼 **Your Portfolio:**\n"
    total_value = 0.0
    for symbol, amount in portfolio[user_id].items():
        price = get_crypto_price(symbol)
        if price:
            value = amount * price
            total_value += value
            msg += f"• {symbol.capitalize()}: {amount} coins, worth ${value:.2f}\n"
        else:
            msg += f"• {symbol.capitalize()}: {amount} coins, price unavailable\n"
    msg += f"\n💰 Total Portfolio Value: ${total_value:.2f}"
    return msg

def add_alert(user_id, symbol, target_price):
    symbol = symbol.lower()
    if user_id not in alerts:
        alerts[user_id] = []
    alerts[user_id].append({"symbol": symbol, "target": target_price})

def check_alerts(context: CallbackContext):
    for user_id, user_alerts in list(alerts.items()):
        for alert in user_alerts[:]:
            current_price = get_crypto_price(alert["symbol"])
            if current_price is not None and current_price >= alert["target"]:
                try:
                    context.bot.send_message(chat_id=user_id,
                        text=f"🚨 Alert! {alert['symbol'].capitalize()} reached ${current_price}")
                    user_alerts.remove(alert)
                except Exception as e:
                    logger.error(f"Error sending alert to {user_id}: {e}")
        if not user_alerts:
            del alerts[user_id]

def fetch_trending_coins():
    """Fetch top trending coins from CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/search/trending"
        response = requests.get(url)
        data = response.json()
        trending = []
        for coin in data.get("coins", []):
            item = coin.get("item", {})
            trending.append({
                "name": item.get("name"),
                "symbol": item.get("symbol"),
                "market_cap_rank": item.get("market_cap_rank"),
                "price_btc": item.get("price_btc")
            })
        return trending
    except Exception as e:
        logger.error(f"Error fetching trending coins: {e}")
        return []

def format_trending():
    trending = fetch_trending_coins()
    if not trending:
        return "🔥 Could not fetch trending coins right now."
    msg = "🔥 **Top Trending Cryptocurrencies:**\n"
    for coin in trending:
        msg += f"• {coin['name']} ({coin['symbol'].upper()}), Rank: {coin['market_cap_rank']}\n"
    return msg

def fetch_ai_news():
    """Fetch AI or crypto news (dummy example - replace with real API call as needed)"""
    # Example: Use a free news API or a crypto news API to get headlines
    # Here a placeholder returning dummy news
    news = [
        "Crypto market shows signs of recovery amid global economic shifts.",
        "New DeFi project launches with promising features.",
        "AI advances boost adoption in crypto trading algorithms."
    ]
    formatted = "📰 **Latest Crypto & AI News:**\n"
    for n in news:
        formatted += f"• {n}\n"
    return formatted

def auto_reply_on_keyword(user_id, message_text):
    """Return the auto-reply if keyword matches"""
    if user_id in auto_replies:
        for keyword, reply in auto_replies[user_id].items():
            if keyword.lower() in message_text.lower():
                return reply
    return None

def format_quiz_question(q_index):
    if q_index >= len(quiz_questions):
        return None
    q = quiz_questions[q_index]
    return q["question"], q["options"]

def start_quiz(user_id):
    active_quiz[user_id] = 0

def get_current_quiz_index(user_id):
    return active_quiz.get(user_id, None)

def increment_quiz_index(user_id):
    active_quiz[user_id] = active_quiz.get(user_id, 0) + 1

def quiz_is_active(user_id):
    return user_id in active_quiz

def reset_quiz(user_id):
    if user_id in active_quiz:
        del active_quiz[user_id]

# =========================
# COMMAND HANDLERS
# =========================

def start(update: Update, context: CallbackContext):
    welcome_message = (
        "👋 Welcome to CryptoTracker Bot!\n\n"
        "Commands:\n"
        "/add <symbol> - Add coin to your watchlist\n"
        "/remove <symbol> - Remove coin from your watchlist\n"
        "/watchlist - View your watchlist\n"
        "/price <symbol> - Get price of a coin\n"
        "/quiz - Start crypto quiz\n"
        "/portfolio - Show your portfolio\n"
        "/addportfolio <symbol> <amount> - Add coins to your portfolio\n"
        "/alert <symbol> <target_price> - Set a price alert\n"
        "/trending - Show top trending coins\n"
        "/news - Show latest crypto & AI news\n"
        "/autoreply <keyword> <reply> - Set an auto-reply for a keyword\n"
        "/removeautoreply <keyword> - Remove an auto-reply\n"
        "/help - Show this message"
    )
    update.message.reply_text(welcome_message)

def help_command(update: Update, context: CallbackContext):
    start(update, context)

def add_command(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /add <symbol>")
        return
    symbol = context.args[0]
    if add_to_watchlist(update.effective_user.id, symbol):
        update.message.reply_text(f"✅ Added {symbol.upper()} to your watchlist.")
    else:
        update.message.reply_text(f"⚠️ {symbol.upper()} is already in your watchlist.")

def remove_command(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /remove <symbol>")
        return
    symbol = context.args[0]
    if remove_from_watchlist(update.effective_user.id, symbol):
        update.message.reply_text(f"❌ Removed {symbol.upper()} from your watchlist.")
    else:
        update.message.reply_text(f"⚠️ {symbol.upper()} is not in your watchlist.")

def watchlist_command(update: Update, context: CallbackContext):
    msg = format_watchlist(update.effective_user.id)
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

def price_command(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /price <symbol>")
        return
    symbol = context.args[0].lower()
    price = get_crypto_price(symbol)
    if price:
        update.message.reply_text(f"💰 {symbol.upper()} current price: ${price}")
    else:
        update.message.reply_text(f"❌ Could not fetch price for {symbol.upper()}")

def portfolio_command(update: Update, context: CallbackContext):
    msg = format_portfolio(update.effective_user.id)
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

def addportfolio_command(update: Update, context: CallbackContext):
    if len(context.args) != 2:
        update.message.reply_text("Usage: /addportfolio <symbol> <amount>")
        return
    symbol = context.args[0]
    try:
        amount = float(context.args[1])
    except ValueError:
        update.message.reply_text("❌ Invalid amount.")
        return
    add_to_portfolio(update.effective_user.id, symbol, amount)
    update.message.reply_text(f"✅ Added {amount} {symbol.upper()} to your portfolio.")

def alert_command(update: Update, context: CallbackContext):
    if len(context.args) != 2:
        update.message.reply_text("Usage: /alert <symbol> <target_price>")
        return
    symbol = context.args[0].lower()
    try:
        target_price = float(context.args[1])
    except ValueError:
        update.message.reply_text("❌ Invalid price.")
        return
    add_alert(update.effective_user.id, symbol, target_price)
    update.message.reply_text(f"✅ Alert set for {symbol.upper()} at ${target_price}")

def trending_command(update: Update, context: CallbackContext):
    msg = format_trending()
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

def news_command(update: Update, context: CallbackContext):
    msg = fetch_ai_news()
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

def autoreply_command(update: Update, context: CallbackContext):
    if len(context.args) < 2:
        update.message.reply_text("Usage: /autoreply <keyword> <reply message>")
        return
    keyword = context.args[0].lower()
    reply = ' '.join(context.args[1:])
    user_id = update.effective_user.id
    if user_id not in auto_replies:
        auto_replies[user_id] = {}
    auto_replies[user_id][keyword] = reply
    update.message.reply_text(f"✅ Auto-reply set for keyword '{keyword}'")

def removeautoreply_command(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /removeautoreply <keyword>")
        return
    keyword = context.args[0].lower()
    user_id = update.effective_user.id
    if user_id in auto_replies and keyword in auto_replies[user_id]:
        del auto_replies[user_id][keyword]
        update.message.reply_text(f"❌ Removed auto-reply for keyword '{keyword}'")
    else:
        update.message.reply_text(f"⚠️ No auto-reply found for keyword '{keyword}'")

# =========================
# QUIZ HANDLERS
# =========================

def quiz_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    start_quiz(user_id)
    send_quiz_question(update, user_id)

def send_quiz_question(update_or_callback, user_id):
    q_index = get_current_quiz_index(user_id)
    question, options = format_quiz_question(q_index)
    if question is None:
        if hasattr(update_or_callback, 'message'):
            update_or_callback.message.reply_text("🎉 Quiz completed! Thanks for playing.")
        else:
            update_or_callback.edit_message_text("🎉 Quiz completed! Thanks for playing.")
        reset_quiz(user_id)
        return

    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"quiz|{i}")]
        for i, opt in enumerate(options)
    ]

    if hasattr(update_or_callback, 'message'):
        update_or_callback.message.reply_text(
            question,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        update_or_callback.edit_message_text(
            question,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

def quiz_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    _, ans_index_str = query.data.split('|')
    ans_index = int(ans_index_str)
    q_index = get_current_quiz_index(user_id)
    correct_answer = quiz_questions[q_index]["answer"]

    if ans_index == correct_answer:
        query.answer("✅ Correct!")
    else:
        query.answer("❌ Wrong!")

    increment_quiz_index(user_id)
    send_quiz_question(query, user_id)

# =========================
# MESSAGE HANDLER FOR AUTO-REPLY
# =========================
def message_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    reply = auto_reply_on_keyword(user_id, text)
    if reply:
        update.message.reply_text(reply)

# =========================
# MAIN RUN FUNCTION
# =========================
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("add", add_command))
    dp.add_handler(CommandHandler("remove", remove_command))
    dp.add_handler(CommandHandler("watchlist", watchlist_command))
    dp.add_handler(CommandHandler("price", price_command))
    dp.add_handler(CommandHandler("portfolio", portfolio_command))
    dp.add_handler(CommandHandler("addportfolio", addportfolio_command))
    dp.add_handler(CommandHandler("alert", alert_command))
    dp.add_handler(CommandHandler("trending", trending_command))
    dp.add_handler(CommandHandler("news", news_command))
    dp.add_handler(CommandHandler("quiz", quiz_command))
    dp.add_handler(CommandHandler("autoreply", autoreply_command))
    dp.add_handler(CommandHandler("removeautoreply", removeautoreply_command))

    # Callback for quiz answers
    dp.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz\|\d+$"))

    # Message handler for auto reply keywords
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, message_handler))

    # Job queue for alert checks every 60 seconds
    job_queue = updater.job_queue
    job_queue.run_repeating(check_alerts, interval=60, first=10)

    # Run Flask app in a separate thread
    threading.Thread(target=run_flask).start()

    # Start polling updates from Telegram
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
