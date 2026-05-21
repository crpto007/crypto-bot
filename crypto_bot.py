from flask import Flask
import os
import logging
import random
import json
import requests
import matplotlib
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, time
from threading import Thread
import threading
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    InlineQueryHandler,
    MessageHandler,
    Filters
)
from telegram.error import Conflict

from bs4 import BeautifulSoup
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import utc

try:
    import snscrape.modules.twitter as sntwitter
except ImportError:
    print("Warning: snscrape not available. Tweet functionality will be disabled.")
    sntwitter = None

from dotenv import load_dotenv
import openai

# Matplotlib backend
matplotlib.use('Agg')  # Non-interactive backend

# ----------------- Load Environment Variables -----------------
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ----------------- Logging -----------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------- Telegram Bot Setup -----------------
 

# ----------------- Flask App -----------------
app = Flask(__name__)
@app.route("/")
def home():
    return "Crypto Bot Running 🚀"
# ----------------- Global Data Stores -----------------
user_watchlist = {}
auto_reply_users = set()
user_alerts = {}
real_time_graphs = {}
price_history = {}
alerts_db = {}
share_link = {}
user_portfolios = {}
user_data = {}  # Moved before ensure_user_data
def run_bot():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
# ----------------- Utility Functions -----------------
def ensure_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "cmd_count": 0,
            "watch_count": 0,
            "coins": 0
        }

# ----------------- Scheduler -----------------
scheduler = BackgroundScheduler(timezone=utc)
#scheduler.start()
btc_job = None

# ----------------- Quiz Questions -----------------
quiz_questions = [
    {
        "question": "🧠 Q1: What is the second most valuable crypto after BTC?",
        "options": ["Litecoin", "Ethereum", "Dogecoin", "XRP"],
        "answer": "Ethereum"
    },
    {
        "question": "🧠 Q2: What does BTC stand for?",
        "options": ["Bitcash", "BlockTradeCoin", "Bitcoin", "BaseTokenCoin"],
        "answer": "Bitcoin"
    },
    {
        "question": "🧠 Q3: Which platform is used for smart contracts?",
        "options": ["Dogecoin", "Ethereum", "Litecoin", "Ripple"],
        "answer": "Ethereum"
    },
    {
        "question": "🧠 Q4: Which coin has a Shiba Inu as mascot?",
        "options": ["Dogecoin", "Cardano", "Solana", "Polygon"],
        "answer": "Dogecoin"
    },
    {
        "question": "🧠 Q5: What is the full form of NFT?",
        "options": ["Non-Fungible Token", "New Financial Tech", "Next Future Trade", "None"],
        "answer": "Non-Fungible Token"
    }
]


# ----------------- Utility: Price Getter (Placeholder) -----------------
def get_price(coin):
    # Replace with your actual price fetch logic
    dummy_prices = {
        "bitcoin": "₹28,00,000 (+2.1%)",
        "ethereum": "₹1,80,000 (-1.2%)",
        "dogecoin": "₹7.2 (+0.4%)"
    }
    return dummy_prices.get(coin.lower(), "Price not available")

# ----------------- Watch & Earn -----------------
def watch_command(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)  # Make sure data exists

    user_data[user_id]["watch_count"] += 1

    chat_id = update.effective_chat.id
    context.bot.send_message(chat_id=chat_id, text="👀 Watching...")

    context.job_queue.run_once(finish_watch, 60, context=user_id)  # Pass user_id

def finish_watch(context: CallbackContext):
    user_id = str(context.job.context)
    ensure_user_data(user_id)

    user_data[user_id]["coins"] += 10  # Give coins
    context.bot.send_message(chat_id=user_id, text="🎉 You've completed watching! You earned 10 coins 💰")

# ----------------- Wallet Command -----------------
def mywallet_command(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    coins = user_data[user_id].get("coins", 0)

    update.message.reply_text(f"💼 *Your Wallet*\n\n💰 Coins: {coins}", parse_mode='Markdown')

# ----------------- Button Handler -----------------
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.edit_message_text(text=f"📍 You selected: {query.data}")

# ----------------- Coin Price Button -----------------
def coin_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    coin = query.data.strip().lower()
    price = get_price(coin)

    query.edit_message_text(f"💰 {price}", parse_mode='Markdown')

# ----------------- Daily Digest -----------------
def send_daily_digest(context):
    message = (
        "📰 *Daily Crypto Market Digest*\n\n"
        "BTC: ₹28,00,000 (+2.1%)\nETH: ₹1,80,000 (-1.2%)\nDOGE: ₹7.2 (+0.4%)\n\n"
        "🤖 AI Insight: \"Bitcoin may remain bullish short-term.\""
    )
    for user_id in user_data:
        context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')

def schedule_digest(updater):
    ist = pytz.timezone("Asia/Kolkata")
    updater.job_queue.run_daily(
        send_daily_digest,
        time=time(hour=9, minute=0, tzinfo=ist)
    )

# ----------------- Quiz Game -----------------
def quiz_command(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    user_data[user_id]["score"] = 0
    user_data[user_id]["current_q"] = 0

    update.message.reply_text("🎯 Starting Crypto Quiz!")
    send_quiz_question(context.bot, user_id)

def send_quiz_question(bot, user_id):
    ensure_user_data(user_id)
    index = user_data[user_id]["current_q"]

    if index >= len(quiz_questions):
        score = user_data[user_id]["score"]
        bot.send_message(
            chat_id=user_id,
            text=f"🏁 *Quiz Completed!*\n\nYour Final Score: *{score}/{len(quiz_questions)}*",
            parse_mode='Markdown'
        )
        return

    q = quiz_questions[index]
    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"quiz|{opt}|{q['answer']}|{index}")]
        for opt in q["options"]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    bot.send_message(
        chat_id=user_id,
        text=q["question"],
        reply_markup=reply_markup
    )

def quiz_response(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    try:
        prefix, selected, correct, index = query.data.split("|")
        user_id = str(query.from_user.id)
        ensure_user_data(user_id)

        if selected == correct:
            user_data[user_id]["score"] += 1
            reply = "✅ Correct!"
        else:
            reply = f"❌ Wrong! Correct answer: *{correct}*"

        user_data[user_id]["current_q"] += 1
        query.edit_message_text(reply, parse_mode='Markdown')

        # Send next question
        send_quiz_question(context.bot, user_id)

    except Exception as e:
        query.edit_message_text("⚠️ Error occurred in quiz.")
        print(f"[Quiz Error] {e}")

# --- Ensure required globals ---
auto_reply_users = set()
user_watchlist = {}

# Dummy placeholders (replace with actual functions)
def get_price(coin):
    # Example placeholder function
    return f"{coin.capitalize()} price: ₹12345"

def ai_question_handler(update, context):
    update.message.reply_text("🤖 AI answering your question...")

# --- Auto Reply Commands ---
def enable_auto_reply(update, context):
    user_id = str(update.effective_user.id)
    auto_reply_users.add(user_id)
    update.message.reply_text("🔔 Auto price reply enabled! Type any coin name.")

def disable_auto_reply(update, context):
    user_id = str(update.effective_user.id)
    if user_id in auto_reply_users:
        auto_reply_users.remove(user_id)
        update.message.reply_text("🔕 Auto price reply disabled.")
    else:
        update.message.reply_text("⚠️ Auto reply is not enabled.")

def auto_reply_handler(update, context):
    user_id = str(update.effective_user.id)
    if user_id not in auto_reply_users:
        return

    text = (update.message.text or "").lower().strip()

    # ✅ Ignore quiz or custom callback responses
    if text.startswith("quiz|"):
        return

    # 💰 Coin name auto-reply
    if text.isalpha() and len(text) > 2:
        price_info = get_price(text)
        if price_info and isinstance(price_info, str):
            if "not found" not in price_info.lower() and "error" not in price_info.lower():
                update.message.reply_text(f"💰 {price_info}", parse_mode='Markdown')
                return

    # 🤖 AI fallback
    if '?' in text or text.endswith("please"):
        ai_question_handler(update, context)

# --- Watchlist Commands ---
def add_watch(update, context):
    user_id = str(update.effective_user.id)
    if not context.args:
        update.message.reply_text("Usage: /addwatch bitcoin")
        return

    coin = context.args[0].lower()
    user_watchlist.setdefault(user_id, set()).add(coin)
    update.message.reply_text(f"✅ Added *{coin}* to your watchlist.", parse_mode='Markdown')

def view_watchlist(update, context):
    user_id = str(update.effective_user.id)
    coins = user_watchlist.get(user_id, set())

    if not coins:
        update.message.reply_text("📭 Your watchlist is empty.")
        return

    reply_lines = ["📋 *Your Watchlist:*", ""]
    for coin in coins:
        price = get_price(coin)
        reply_lines.append(str(price))

    reply = "\n".join(reply_lines)
    update.message.reply_text(reply, parse_mode='Markdown')

def clear_watchlist(update, context):
    user_id = str(update.effective_user.id)
    if user_id in user_watchlist:
        user_watchlist[user_id].clear()
        update.message.reply_text("🗑️ Your watchlist has been cleared.")
    else:
        update.message.reply_text("📭 Your watchlist is already empty.")

def remove_watch(update, context):
    user_id = str(update.effective_user.id)
    if not context.args:
        update.message.reply_text("Usage: /removewatch bitcoin")
        return

    coin = context.args[0].lower()
    if user_id in user_watchlist and coin in user_watchlist[user_id]:
        user_watchlist[user_id].remove(coin)
        update.message.reply_text(f"❌ Removed *{coin}* from your watchlist.", parse_mode='Markdown')
    else:
        update.message.reply_text(f"⚠️ {coin} is not in your watchlist.")

# --- AI News Summary ---
def ai_news_summary(update, context):
    if not context.args:
        update.message.reply_text("Usage: /ainews bitcoin")
        return

    coin = context.args[0].lower()

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            update.message.reply_text(f"❌ Could not find information for {coin}")
            return

        data = response.json()

        name = data.get('name', coin.capitalize())
        description = data.get('description', {}).get('en', '') or ''
        market_data = data.get('market_data', {})

        current_price = market_data.get('current_price', {}).get('inr', 0)
        price_change_24h = market_data.get('price_change_percentage_24h', 0)
        market_cap_rank = data.get('market_cap_rank', 'N/A')

        # Escape Markdown special characters
        def escape_md(text):
            for ch in "_*[]()~`>#+-=|{}.!":
                text = text.replace(ch, f"\\{ch}")
            return text

        news_summary = f"""
🤖 AI SUMMARY FOR {escape_md(name.upper())}

📊 Current Status:
• Price: ₹{current_price:,}
• 24h Change: {price_change_24h:.2f}%
• Market Rank: #{market_cap_rank}

📝 Project Overview:
{escape_md(description[:800])}...

💡 Key Insights:
• {'Bullish trend' if price_change_24h > 0 else 'Bearish trend'} in last 24h
• {'Strong market position' if isinstance(market_cap_rank, int) and market_cap_rank <= 50 else 'Emerging project'}
• {'High volatility' if abs(price_change_24h) > 5 else 'Stable price action'}

⚠️ This is automated analysis. Do your own research!
        """

        update.message.reply_text(news_summary.strip(), parse_mode='MarkdownV2')

    except Exception as e:
        update.message.reply_text(f"❌ Error generating AI summary.")
        logger.error(f"AI summary error: {e}")


import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import CallbackContext
import openai

# Example storage
auto_reply_users = set()
user_portfolios = {}

# Escape Markdown special characters
def escape_md(text):
    if not isinstance(text, str):
        return ""
    for ch in "_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def ensure_user_data(user_id):
    if user_id not in user_portfolios:
        user_portfolios[user_id] = {}

def market_sentiment(update, context):
    try:
        fear_greed_url = "https://api.alternative.me/fng/"
        response = requests.get(fear_greed_url, timeout=10)

        if response.status_code == 200:
            fg_data = response.json()['data'][0]
            value = int(fg_data['value'])
            classification = fg_data['value_classification']

            sentiment_emoji = {
                'Extreme Fear': '😰',
                'Fear': '😟',
                'Neutral': '😐',
                'Greed': '😊',
                'Extreme Greed': '🤑'
            }

            emoji = sentiment_emoji.get(classification, '📊')

            summary = f"""
🧠 *MARKET SENTIMENT ANALYSIS*

{emoji} Fear & Greed Index: {value}/100
📊 Classification: {classification}

💭 AI Interpretation:
"""

            if value <= 25:
                summary += "• Market in extreme fear - potential buying opportunity\n• High sell pressure observed\n• Consider dollar-cost averaging"
            elif value <= 45:
                summary += "• Cautious sentiment prevails\n• Market uncertainty present\n• Good time for research and planning"
            elif value <= 55:
                summary += "• Balanced market conditions\n• Neither fear nor greed dominant\n• Normal trading environment"
            elif value <= 75:
                summary += "• Greed starting to emerge\n• FOMO may be building\n• Exercise caution with new positions"
            else:
                summary += "• Extreme greed detected\n• Market may be overheated\n• Consider taking profits"

            update.message.reply_text(summary, parse_mode='Markdown')
        else:
            update.message.reply_text("❌ Could not fetch market sentiment data")

    except Exception as e:
        update.message.reply_text(f"❌ Error analyzing sentiment: {str(e)}")

def chatgpt_auto_reply(update, context):
    user_id = str(update.effective_user.id)
    if user_id in auto_reply_users:
        auto_reply_users.remove(user_id)
        update.message.reply_text("🤖 ChatGPT Auto-Reply disabled.")
    else:
        auto_reply_users.add(user_id)
        update.message.reply_text("🤖 ChatGPT Auto-Reply enabled! Ask me any crypto question.")

def ai_question_handler(update, context):
    user_id = str(update.effective_user.id)
    if user_id not in auto_reply_users:
        return
    prompt = (update.message.text or "").strip()
    if len(prompt.split()) <= 1:
        return
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a crypto expert bot that explains any crypto-related question in simple Hindi-English mix for beginners."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        reply = response['choices'][0]['message']['content']
        update.message.reply_text(f"🤖 AI Answer:\n\n{reply}")
    except Exception as e:
        update.message.reply_text("⚠️ Sorry, AI failed to respond. Try again.")

import requests

def airdrops_command(update, context):
    try:
        # Free public airdrops API (example source)
        url = "https://api.airdropking.io/public/api/airdrops?status=ongoing"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            update.message.reply_text("⚠️ Unable to fetch airdrops right now.")
            return
        
        data = response.json()
        if not data.get("airdrops"):
            update.message.reply_text("🚫 No live airdrops found at the moment.")
            return
        
        # Create message
        message = "💎 **Live Crypto Airdrops** 💎\n\n"
        for drop in data["airdrops"][:5]:  # Top 5 airdrops
            message += f"🔹 {drop['name']} ({drop['symbol']})\n"
            message += f"🌐 Link: {drop['url']}\n"
            message += f"🎁 Reward: {drop.get('reward', 'N/A')}\n\n"
        
        update.message.reply_text(message, parse_mode="Markdown")
    
    except Exception as e:
        update.message.reply_text(f"❌ Error: {e}")


def portfolio_command(update, context):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    portfolio = user_portfolios[user_id]
    if not portfolio:
        update.message.reply_text(
            "📊 *YOUR CRYPTO PORTFOLIO*\n\n💼 Portfolio is empty!\n\n"
            "📝 *Add coins with:*\n"
            "`/addcoin bitcoin 0.5 45000`\n"
            "`/removecoin bitcoin`\n"
            "`/clearportfolio`\n",
            parse_mode='Markdown')
        return

    total_value = 0
    total_invested = 0
    reply = "📊 *YOUR CRYPTO PORTFOLIO*\n\n"

    for coin, data in portfolio.items():
        amount = data['amount']
        buy_price = data['buy_price']
        invested = amount * buy_price
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr"
            response = requests.get(url, timeout=10)
            price_data = response.json()
            current_price = price_data[coin]['inr']
            current_value = amount * current_price
            profit_loss = current_value - invested
            profit_percent = (profit_loss / invested) * 100 if invested > 0 else 0
            emoji = "🟢" if profit_loss > 0 else "🔴" if profit_loss < 0 else "⚪"
            reply += f"{emoji} *{coin.upper()}*\n"
            reply += f"💰 Amount: {amount}\n"
            reply += f"💵 Buy Price: ₹{buy_price:,}\n"
            reply += f"📈 Current: ₹{current_price:,}\n"
            reply += f"💎 Value: ₹{current_value:,.2f}\n"
            reply += f"📊 P&L: ₹{profit_loss:,.2f} ({profit_percent:+.2f}%)\n\n"
            total_value += current_value
            total_invested += invested
        except:
            reply += f"⚠️ *{coin.upper()}* - Price fetch failed\n\n"

    total_pl = total_value - total_invested
    total_pl_percent = (total_pl / total_invested) * 100 if total_invested > 0 else 0
    pl_emoji = "🟢" if total_pl > 0 else "🔴" if total_pl < 0 else "⚪"
    reply += "📋 *PORTFOLIO SUMMARY*\n"
    reply += f"💰 Invested: ₹{total_invested:,.2f}\n"
    reply += f"💎 Current: ₹{total_value:,.2f}\n"
    reply += f"{pl_emoji} P&L: ₹{total_pl:,.2f} ({total_pl_percent:+.2f}%)"
    update.message.reply_text(reply, parse_mode='Markdown')

    
import requests
import logging

# Globals
user_portfolios = {}
logger = logging.getLogger(__name__)

def addcoin_command(update, context):
    user_id = str(update.effective_user.id)
    if len(context.args) != 3:
        update.message.reply_text("❌ Usage: /addcoin bitcoin 0.5 45000")
        return

    coin = context.args[0].lower()
    try:
        amount = float(context.args[1])
        buy_price = float(context.args[2])
    except ValueError:
        update.message.reply_text("❌ Invalid amount or price.")
        return

    user_portfolios.setdefault(user_id, {})[coin] = {
        'amount': amount,
        'buy_price': buy_price
    }

    update.message.reply_text(
        f"✅ Added {amount} {coin.upper()} at ₹{buy_price:,} to your portfolio!"
    )

def removecoin_command(update, context):
    user_id = str(update.effective_user.id)
    if len(context.args) != 1:
        update.message.reply_text("❌ Usage: /removecoin bitcoin")
        return

    coin = context.args[0].lower()
    if user_id in user_portfolios and coin in user_portfolios[user_id]:
        del user_portfolios[user_id][coin]
        update.message.reply_text(f"✅ Removed {coin.upper()} from your portfolio.")
    else:
        update.message.reply_text(f"⚠️ {coin.upper()} not found in your portfolio.")

def clearportfolio_command(update, context):
    user_id = str(update.effective_user.id)
    user_portfolios[user_id] = {}
    update.message.reply_text("🗑️ Your portfolio has been cleared.")

def dominance_command(update, context):
    """Show market dominance data"""
    try:
        url = "https://api.coingecko.com/api/v3/global"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            update.message.reply_text("❌ Could not fetch dominance data")
            return

        data = response.json()['data']

        btc_dominance = data['market_cap_percentage']['btc']
        eth_dominance = data['market_cap_percentage']['eth']
        total_market_cap = data['total_market_cap']['usd']
        total_volume = data['total_volume']['usd']
        active_cryptos = data['active_cryptocurrencies']

        # Get top 10 coins
        coins_url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            "?vs_currency=usd&order=market_cap_desc&per_page=10&page=1"
        )
        coins_response = requests.get(coins_url, timeout=10)

        if coins_response.status_code != 200:
            update.message.reply_text("❌ Could not fetch coin data")
            return

        dominance_text = f"""
👑 *CRYPTO MARKET DOMINANCE*

🌍 *Global Market Overview:*
💰 Total Market Cap: ${total_market_cap/1e12:.2f}T
📊 24h Volume: ${total_volume/1e9:.1f}B
🪙 Active Cryptos: {active_cryptos:,}

📈 *Dominance Rankings:*

🥇 Bitcoin (BTC): {btc_dominance:.1f}%
🥈 Ethereum (ETH): {eth_dominance:.1f}%
"""

        coins = coins_response.json()
        other_dominance = 0

        for i, coin in enumerate(coins[2:8], 3):  # Skip BTC and ETH
            symbol = coin['symbol'].upper()
            market_cap = coin['market_cap']
            dominance = (market_cap / total_market_cap) * 100
            other_dominance += dominance

            medal = "🥉" if i == 3 else f"{i}."
            dominance_text += f"{medal} {symbol}: {dominance:.1f}%\n"

        dominance_text += f"\n🔸 Others: {100 - btc_dominance - eth_dominance - other_dominance:.1f}%"
        dominance_text += "\n\n💡 High BTC dominance = Alt season might be coming"
        dominance_text += "\n💡 Low BTC dominance = Alt coins are pumping"

        update.message.reply_text(dominance_text, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"❌ Error fetching dominance: {str(e)}")
        logger.error(f"Dominance error: {e}")

def predict_command(update, context):
    """AI-powered price prediction"""
    if not context.args:
        update.message.reply_text("Usage: /predict bitcoin")
        return

    coin = context.args[0].lower()

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=inr&days=30"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            update.message.reply_text(f"❌ Could not find {coin}")
            return

        data = response.json()
        prices = [p[1] for p in data['prices']]
        volumes = [v[1] for v in data['total_volumes']]

        if len(prices) < 7:
            update.message.reply_text("❌ Not enough data for prediction")
            return

        current_price = prices[-1]
        week_ago = prices[-7]
        month_ago = prices[0]

        ma7 = sum(prices[-7:]) / 7
        ma14 = sum(prices[-14:]) / 14 if len(prices) >= 14 else ma7
        ma30 = sum(prices) / len(prices)

        avg_volume = sum(volumes[-7:]) / 7
        current_volume = volumes[-1]

        week_change = ((current_price - week_ago) / week_ago) * 100
        month_change = ((current_price - month_ago) / month_ago) * 100

        bullish_signals = 0
        bearish_signals = 0

        if current_price > ma7:
            bullish_signals += 1
        else:
            bearish_signals += 1

        if ma7 > ma14:
            bullish_signals += 1
        else:
            bearish_signals += 1

        if current_volume > avg_volume:
            if week_change > 0:
                bullish_signals += 1
            else:
                bearish_signals += 1

        if week_change > 5:
            bullish_signals += 1
        elif week_change < -5:
            bearish_signals += 1

        if bullish_signals > bearish_signals:
            sentiment = "🟢 BULLISH"
            prediction = "Price likely to go UP"
            target_change = 5 + (bullish_signals * 2)
        elif bearish_signals > bullish_signals:
            sentiment = "🔴 BEARISH"
            prediction = "Price likely to go DOWN"
            target_change = -(5 + (bearish_signals * 2))
        else:
            sentiment = "⚪ NEUTRAL"
            prediction = "Price likely to CONSOLIDATE"
            target_change = 0

        predicted_price = current_price * (1 + target_change / 100)

        prediction_text = f"""
🔮 *AI PRICE PREDICTION FOR {coin.upper()}*

📊 *Current Analysis:*
💰 Current Price: ₹{current_price:,.2f}
📈 7-day MA: ₹{ma7:,.2f}
📈 14-day MA: ₹{ma14:,.2f}
📈 30-day MA: ₹{ma30:,.2f}

📉 *Performance:*
• 7 days: {week_change:+.2f}%
• 30 days: {month_change:+.2f}%

🎯 *AI Prediction (Next 7 days):*
{sentiment}
{prediction}

🔮 Target Price: ₹{predicted_price:,.2f}
📊 Expected Change: {target_change:+.1f}%

🤖 *AI Confidence Signals:*
• Bullish: {bullish_signals}/4
• Bearish: {bearish_signals}/4

⚠️ *Disclaimer:* This is AI analysis, not financial advice.
        """

        update.message.reply_text(prediction_text, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"❌ Error generating prediction: {str(e)}")
        logger.error(f"Prediction error: {e}")



# ===== Imports =====
import requests
import matplotlib.pyplot as plt
from datetime import datetime
from io import BytesIO
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from telegram import InlineQueryResultArticle, InputTextMessageContent

# ===== Logger setup =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Global Variables =====
real_time_graphs = {}
scheduler = BackgroundScheduler()
#scheduler.start()

# ===== Example placeholder for get_price function =====
def get_price(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if coin in data:
                price = data[coin]['inr']
                return f"{coin.capitalize()} Price: ₹{price:,}"
        return f"❌ Coin '{coin}' not found."
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ===== Commands =====
def share(update, context):
    bot_username = "mycryptotracker007_bot"  # @ hata diya
    share_link = f"https://t.me/{bot_username}?start"
    update.message.reply_text(f"🔗 Share this bot:\n{share_link}")


def get_price_with_logo(coin):
    try:
        # Try direct coin ID search
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            info = response.json()
            image = info['image']['large']
            price = info['market_data']['current_price']['inr']
            name = info['name']
            symbol = info['symbol'].upper()
            market_cap_rank = info.get('market_cap_rank', 'N/A')
            change_24h = info['market_data'].get('price_change_percentage_24h', 0)

            trend_emoji = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"

            caption = (
                f"💰 *{name}* ({symbol}) {trend_emoji}\n"
                f"💵 Price: ₹{price:,}\n"
                f"📊 24h Change: {change_24h:+.2f}%\n"
                f"🏆 Rank: #{market_cap_rank}"
            )

            return image, caption

        # If direct search fails, try search API
        search_url = f"https://api.coingecko.com/api/v3/search?query={coin}"
        search_response = requests.get(search_url, timeout=10)

        if search_response.status_code == 200:
            search_data = search_response.json()
            if search_data.get('coins'):
                coin_id = search_data['coins'][0]['id']
                return get_price_with_logo(coin_id)
            elif search_data.get('categories'):
                return None, f"🔍 Found category '{coin}' but no specific coin."
            else:
                return None, f"❌ No results found for '{coin}'."

        return None, f"❌ Coin '{coin}' not found."

    except requests.exceptions.Timeout:
        return None, "⏱️ Request timeout - Try again later"
    except Exception as e:
        return None, f"❌ Error fetching data: {str(e)}"


def logo_price_command(update, context):
    if len(context.args) == 0:
        update.message.reply_text(
            "Usage: /logoprice bitcoin\n"
            "💡 You can search by:\n"
            "• Coin name (bitcoin, ethereum)\n"
            "• Symbol (btc, eth, doge)\n"
            "• Token name (shiba-inu, chainlink)"
        )
        return

    coin = context.args[0].lower().strip()
    loading_msg = update.message.reply_text("🔍 Searching for coin data...")

    image, msg = get_price_with_logo(coin)
    context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_msg.message_id)

    if image:
        update.message.reply_photo(photo=image, caption=msg, parse_mode='Markdown')
    else:
        update.message.reply_text(msg)


def inline_query(update, context):
    query = update.inline_query.query.strip().lower()
    if not query:
        return

    result_text = get_price(query)
    results = [
        InlineQueryResultArticle(
            id=query,
            title=f"💸 Price of {query.capitalize()}",
            input_message_content=InputTextMessageContent(result_text)
        )
    ]
    update.inline_query.answer(results)


def real_time_graph(update, context):
    if not context.args:
        update.message.reply_text("Usage: /realtimegraph bitcoin")
        return

    coin = context.args[0].lower()
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    def update_graph():
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=inr&days=1"
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                return

            data = response.json()['prices']
            dates = [datetime.fromtimestamp(p[0] / 1000) for p in data[-24:]]
            prices = [p[1] for p in data[-24:]]

            plt.figure(figsize=(12, 6))
            plt.plot(dates, prices, label=f"{coin.upper()} Live Price", color='green', linewidth=2)
            plt.title(f"🔴 LIVE: {coin.upper()} - Last 24 Hours (INR)")
            plt.xlabel("Time")
            plt.ylabel("Price ₹")
            plt.grid(True, alpha=0.3)
            plt.legend()
            plt.xticks(rotation=45)
            plt.tight_layout()

            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            buffer.seek(0)

            current_price = prices[-1] if prices else 0
            caption = f"📊 Real-time {coin.upper()}: ₹{current_price:,.2f}"

            context.bot.send_photo(chat_id=chat_id, photo=buffer, caption=caption)
            buffer.close()
            plt.close()

        except Exception as e:
            logger.error(f"Real-time graph error: {e}")

    if user_id not in real_time_graphs:
        real_time_graphs[user_id] = {}

    if coin in real_time_graphs[user_id]:
        update.message.reply_text(f"⚠️ Real-time graph for {coin} already running!")
        return

    update_graph()

    job = scheduler.add_job(update_graph, 'interval', minutes=5, id=f"graph_{user_id}_{coin}")
    real_time_graphs[user_id][coin] = job

    update.message.reply_text(
        f"✅ Real-time graph started for {coin}! Updates every 5 minutes.\nUse /stopgraph {coin} to stop."
    )


def stop_real_time_graph(update, context):
    if not context.args:
        update.message.reply_text("Usage: /stopgraph bitcoin")
        return

    coin = context.args[0].lower()
    user_id = str(update.effective_user.id)

    if user_id in real_time_graphs and coin in real_time_graphs[user_id]:
        real_time_graphs[user_id][coin].remove()
        del real_time_graphs[user_id][coin]
        update.message.reply_text(f"⛔ Real-time graph stopped for {coin}")
    else:
        update.message.reply_text(f"⚠️ No active real-time graph for {coin}")

from io import BytesIO
from datetime import datetime
import requests
import matplotlib.pyplot as plt
import logging

from telegram import Update
from telegram.ext import CallbackContext

# Optional: For inline queries (if you use them elsewhere)
from telegram import InlineQueryResultArticle, InputTextMessageContent

# Logger setup
logger = logging.getLogger(__name__)

# ---------------- Graph Command ----------------
def graph_command(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        update.message.reply_text("Usage: /graph bitcoin")
        return

    coin = context.args[0].lower()

    # Optional alias mapping
    coin_alias = {
        'btc': 'bitcoin',
        'eth': 'ethereum',
        'doge': 'dogecoin',
        'bnb': 'binancecoin',
        'sol': 'solana',
        'matic': 'matic-network',
    }
    coin = coin_alias.get(coin, coin)

    url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=inr&days=7"

    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            update.message.reply_text("❌ Coin not found or API error.")
            return

        data = response.json().get('prices', [])
        if not data:
            update.message.reply_text("⚠️ No price data available.")
            return

        dates = [datetime.fromtimestamp(p[0] / 1000) for p in data]
        prices = [p[1] for p in data]

        plt.figure(figsize=(10, 4))
        plt.plot(dates, prices, label=f"{coin.upper()} Price", color='blue')
        plt.title(f"{coin.upper()} - Last 7 Days (INR)")
        plt.xlabel("Date")
        plt.ylabel("Price ₹")
        plt.grid(True)
        plt.legend()

        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        update.message.reply_photo(photo=buffer)
        buffer.close()
        plt.close()

    except Exception as e:
        update.message.reply_text(f"⚠️ Failed to fetch or plot data. Error: {str(e)}")
        logger.error(f"[graph_command error] {e}")

# ---------------- Start Command ----------------
def start(update: Update, context: CallbackContext):
    welcome_text = (
        "🚀 *Welcome to CryptoTracker Pro* 🚀\n\n"
        "📊 *Your Professional Crypto Analytics Hub*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💼 *Real-Time Market Data*\n"
        "• Live INR prices for 1000+ cryptocurrencies\n"
        "• Advanced charting & technical analysis\n"
        "• Smart price alerts & portfolio tracking\n\n"
        "🔥 *Quick Start:*\n"
        "📈 `/price bitcoin` - Live BTC price\n"
        "📊 `/trending` - Market movers\n"
        "💰 `/portfolio` - Track investments\n"
        "🤖 `/predict bitcoin` - AI predictions\n\n"
        "⚡ Type `/help` for complete feature list\n\n"
        "💡 *Powered by CoinGecko API & Advanced AI*"
    )

    update.message.reply_text(welcome_text, parse_mode='Markdown')

# ---------------- Plot Command ----------------
def plot_command(update: Update, context: CallbackContext):
    update.message.reply_text("Generating price plot...")
    send_price_plot(update, context)

def send_price_plot(update: Update, context: CallbackContext):
    try:
        coins = ['Bitcoin', 'Ethereum', 'Dogecoin']
        coin_ids = ['bitcoin', 'ethereum', 'dogecoin']

        coin_ids_str = ','.join(coin_ids)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids_str}&vs_currencies=inr"
        response = requests.get(url, timeout=10)
        data = response.json()

        prices = [data.get(coin_id, {}).get('inr', 0) for coin_id in coin_ids]

        plt.figure(figsize=(10, 6))
        plt.bar(coins, prices, color=['gold', 'silver', 'green'])
        plt.title('Cryptocurrency Prices (INR)')
        plt.ylabel('Price in ₹')
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=buf)
        buf.close()
        plt.close()

    except Exception as e:
        update.message.reply_text(f"❌ Error generating plot: {str(e)}")
        logger.error(f"Plot error: {e}")

# ---------------- Help Command ----------------
def help_command(update: Update, context: CallbackContext):
    help_text = (
        "📋 *CryptoTracker Pro - Command Center*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 *AI-POWERED ANALYTICS*\n"
        "• `/predict <coin>` - AI price predictions\n"
        "• `/sentiment` - Market sentiment\n"
        "• `/ainews <coin>` - AI news summaries\n"
        "• `/chatgpt` - Q&A mode\n"
        "• `/dominance` - Market cap dominance\n\n"
        "💼 *PORTFOLIO MANAGEMENT*\n"
        "• `/portfolio` - P&L tracking\n"
        "• `/addwatch <coin>` - Add to watchlist\n"
        "• `/watchlist` - View watchlist\n"
        "• `/setalert <coin> <above/below> <price>` - Alerts\n"
        "• `/viewalerts` - View alerts\n\n"
        "📊 *REAL-TIME DATA & CHARTS*\n"
        "• `/price <coin>` - Live prices\n"
        "• `/trending` - Market movers\n"
        "• `/coinlist` - Top 20 coins\n"
        "• `/graph <coin>` - 7-day charts\n"
        "• `/realtimegraph <coin>` - Live charts\n"
        "• `/logoprice <coin>` - Price with logo\n"
    )
    update.message.reply_text(help_text, parse_mode='Markdown')

# ---------------- Get Coin ID ----------------
def get_coin_id(coin_name):
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 250,
            'page': 1,
            'sparkline': 'false'
        }

        for page in range(1, 5):
            params['page'] = page
            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"[CoinGecko] Error: {response.status_code}")
                return None

            coins = response.json()
            for coin in coins:
                if (
                    coin_name.lower() == coin['symbol'].lower()
                    or coin_name.lower() == coin['id'].lower()
                    or coin_name.lower() in coin['name'].lower()
                ):
                    return coin['id']

        return None

    except Exception as e:
        logger.error(f"[get_coin_id error] {e}")
        return None
def get_coin_id(coin_name):
    """Convert coin name or symbol to CoinGecko coin id."""
    aliases = {
        'btc': 'bitcoin',
        'eth': 'ethereum',
        'doge': 'dogecoin',
        'bnb': 'binancecoin',
        'sol': 'solana',
        'matic': 'matic-network',
    }
    return aliases.get(coin_name, coin_name)

# ================== PRICE FUNCTION ==================
def get_price(coin):
    try:
        coin = coin.strip().lower()
        coin_id = get_coin_id(coin)

        if not coin_id:
            return f"❌ Coin '{coin}' not found. Try `/coinlist` to see available coins."

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            name = data.get('name', coin_id.capitalize())
            symbol = data.get('symbol', '').upper()
            market_data = data.get('market_data', {})

            price = market_data.get('current_price', {}).get('inr', 0)
            change_24h = market_data.get('price_change_percentage_24h', 0)
            market_cap_rank = data.get('market_cap_rank', 'N/A')

            trend_icon = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
            change_color = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"

            message = (
                f"💎 <b>{name}</b> ({symbol}) {change_color}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>₹{price:,.2f}</b> INR\n"
                f"{trend_icon} 24h: <b>{change_24h:+.2f}%</b>\n"
                f"🏆 Rank: <b>#{market_cap_rank}</b>\n"
                f"⏰ <i>Live Data</i>"
            )
            return message

        return f"❌ Coin '{coin}' not found. Try `/coinlist` to see available coins."

    except requests.exceptions.Timeout:
        return "⏱️ Market data temporarily unavailable. Please try again."

    except Exception as e:
        logger.error(f"[get_price error] {e}")
        return "⚠️ Unable to fetch price data. Try again in a moment."

# ================== COMMANDS ==================
def price(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        update.message.reply_text("❌ Please provide a coin name like bitcoin or ethereum.")
        return
    coin = context.args[0].lower()
    msg = get_price(coin)
    update.message.reply_text(msg, parse_mode='HTML')

def btc_command(update, context):
    update.message.reply_text(get_price("btc"), parse_mode='HTML')

def eth_command(update, context):
    update.message.reply_text(get_price("eth"), parse_mode='HTML')

def doge_command(update, context):
    update.message.reply_text(get_price("doge"), parse_mode='HTML')

def price_buttons(update: Update, context: CallbackContext):
    keyboard = [[
        InlineKeyboardButton("Bitcoin 💰", callback_data='bitcoin'),
        InlineKeyboardButton("Ethereum ⚡", callback_data='ethereum'),
        InlineKeyboardButton("Dogecoin 🐶", callback_data='dogecoin'),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Select a coin:', reply_markup=reply_markup)

def fancy_command(update: Update, context: CallbackContext):
    if context.args:
        coin = context.args[0].strip().lower()
        coin = get_coin_id(coin)

        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr"
            response = requests.get(url, timeout=10)
            data = response.json()

            if data and coin in data and 'inr' in data[coin]:
                price_val = data[coin]["inr"]
                reply = f"✨ *{coin.capitalize()}*\n💰 Price: ₹{price_val:,.2f}"
            else:
                reply = f"❌ Coin '{coin}' not found. Try `/coinlist` for options."
            update.message.reply_text(reply, parse_mode='Markdown')
        except Exception as e:
            update.message.reply_text(f"⚠️ Error: {e}")
    else:
        update.message.reply_text("Usage: /fancy bitcoin")

# ================== ALERTS ==================
def set_alert(update, context):
    user_id = str(update.effective_user.id)

    if len(context.args) != 3:
        update.message.reply_text(
            "Usage:\n/setalert bitcoin above 50000\nor\n/setalert ethereum below 30000"
        )
        return

    coin = context.args[0].lower()
    direction = context.args[1].lower()
    try:
        price_val = float(context.args[2])
    except ValueError:
        update.message.reply_text("❌ Invalid price.")
        return

    if direction not in ["above", "below"]:
        update.message.reply_text("Use 'above' or 'below' only.")
        return

    if user_id not in alerts_db:
        alerts_db[user_id] = []

    alert = {"coin": coin, "direction": direction, "price": price_val}
    alerts_db[user_id].append(alert)

    update.message.reply_text(
        f"✅ Alert set! You'll be notified when {coin.upper()} goes {direction} ₹{price_val:,}"
    )

def view_alerts(update, context):
    user_id = str(update.effective_user.id)
    alerts = alerts_db.get(user_id, [])

    if not alerts:
        update.message.reply_text("☺ No alerts set.")
        return

    msg = "🔔 *Your Active Alerts:*\n\n"
    for a in alerts:
        msg += f"🛎 {a['coin'].upper()} {a['direction']} ₹{a['price']:,}\n"

    update.message.reply_text(msg, parse_mode="Markdown")

def remove_alert(update, context):
    user_id = str(update.effective_user.id)

    if len(context.args) != 1:
        update.message.reply_text("Usage: /removealert bitcoin")
        return

    coin = context.args[0].lower()
    if user_id in alerts_db:
        before = len(alerts_db[user_id])
        alerts_db[user_id] = [a for a in alerts_db[user_id] if a['coin'] != coin]
        after = len(alerts_db[user_id])
        if before > after:
            update.message.reply_text(f"✅ Removed alert for {coin.upper()}")
        else:
            update.message.reply_text(f"⚠️ No alert found for {coin.upper()}")
    else:
        update.message.reply_text("⚠️ No alerts set.")

# ================== TRENDING ==================
def trending_command(update: Update, context: CallbackContext):
    try:
        trending_url = "https://api.coingecko.com/api/v3/search/trending"
        trending_response = requests.get(trending_url, timeout=15)

        if trending_response.status_code == 200:
            trending_data = trending_response.json()
            all_ids = [coin['item']['id'] for coin in trending_data['coins']]
            trending_coins = [cid for cid in all_ids if cid]
        else:
            trending_coins = ['bitcoin', 'ethereum', 'tether', 'binancecoin', 'solana']

        if not trending_coins:
            trending_coins = ['bitcoin', 'ethereum', 'tether', 'binancecoin', 'solana']

        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=inr&ids={','.join(trending_coins)}&order=market_cap_desc&per_page=5&page=1"
        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            update.message.reply_text("📊 Market data temporarily unavailable. Please try again.")
            return

        coins = response.json()
        reply = "🔥 *TRENDING CRYPTO MARKETS*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, coin in enumerate(coins, 1):
            name = coin['name']
            symbol = coin['symbol'].upper()
            price = coin['current_price']
            change_24h = coin['price_change_percentage_24h'] or 0
            market_cap = coin['market_cap']

            trend_icon = "🚀" if change_24h > 5 else "📈" if change_24h > 0 else "📉" if change_24h < -5 else "📊"
            change_color = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"

            reply += f"{trend_icon} **{i}. {name}** ({symbol}) {change_color}\n"
            reply += f"💰 ₹{price:,.2f} | 24h: **{change_24h:+.2f}%**\n"
            reply += f"📊 MCap: ₹{market_cap/1e7:.1f}Cr\n\n"

        reply += "💡 *Use* `/price <coin>` *for detailed analysis*\n📈 *Market data updates every minute*"
        update.message.reply_text(reply, parse_mode='Markdown')

    except requests.exceptions.Timeout:
        update.message.reply_text("⏱️ Market data loading... Please try again in a moment.")
    except Exception as e:
        update.message.reply_text("📊 Unable to fetch trending data.")
        logger.error(f"[trending_command error] {e}")

# ================== COIN LIST ==================
def coinList_command(update: Update, context: CallbackContext):
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=inr&order=market_cap_desc&per_page=20&page=1"
        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            update.message.reply_text("❌ API Error - Try again later")
            return

        coins = response.json()
        reply = "📋 *Top 20 Coins by Market Cap (INR)*\n\n"

        for i, coin in enumerate(coins, 1):
            name = coin['name']
            symbol = coin['symbol'].upper()
            price = coin['current_price']
            change_24h = coin['price_change_percentage_24h']
            trend_emoji = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"
            reply += f"{i}. *{name}* ({symbol}) {trend_emoji}\n"
            reply += f"   ₹{price:,.2f} ({change_24h:+.2f}%)\n\n"

        reply += "💡 Use `/price <coinname>` to get detailed price info"
        update.message.reply_text(reply, parse_mode='Markdown')

    except requests.exceptions.Timeout:
        update.message.reply_text("⏱️ Request timeout - Try again later")
    except Exception as e:
        update.message.reply_text(f"⚠️ Failed to fetch coin list: {str(e)}")
        logger.error(f"Coinlist error: {e}")

# ================== STATUS ==================
def status_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    update.message.reply_text(
        f"✅ Bot is *LIVE* and responding!\n\nYour User ID: `{user_id}`",
        parse_mode='Markdown'
    )
def auto_btc(update, context):
    chat_id = update.effective_chat.id
    if chat_id in auto_btc_users:
        update.message.reply_text("⚠️ Auto BTC पहले से चालू है!")
        return
    
    auto_btc_users[chat_id] = True
    update.message.reply_text("✅ Auto BTC चालू कर दिया गया है! हर 1 मिनट में price भेजी जाएगी।")
    
    def send_price():
        while auto_btc_users.get(chat_id, False):
            price = get_btc_price()
            context.bot.send_message(chat_id=chat_id, text=f"💰 BTC Price: ${price}")
            time.sleep(60)  # हर 1 मिनट बाद price भेजना
    
#

def stop_btc(update, context):
    chat_id = update.effective_chat.id
    if chat_id in auto_btc_users:
        auto_btc_users[chat_id] = False
        update.message.reply_text("🛑 Auto BTC बंद कर दिया गया है।")
    else:
        update.message.reply_text("⚠️ Auto BTC अभी चालू नहीं था।")
def run_bot():
     
     

    # Register handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("share", share))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("plot", plot_command))
    dp.add_handler(CommandHandler("price", price))
    dp.add_handler(CommandHandler("btc", btc_command))
    dp.add_handler(CommandHandler("eth", eth_command))
    dp.add_handler(CommandHandler("doge", doge_command))
    dp.add_handler(CommandHandler("coins", price_buttons))
    dp.add_handler(CommandHandler("fancy", fancy_command))
    dp.add_handler(CommandHandler("autobtc", auto_btc))
    dp.add_handler(CommandHandler("stopbtc", stop_btc))
    dp.add_handler(CommandHandler("trending", trending_command))
    dp.add_handler(CommandHandler("coinlist", coinList_command))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(CommandHandler("graph", graph_command))
    dp.add_handler(CommandHandler("logoprice", logo_price_command))
    dp.add_handler(InlineQueryHandler(inline_query))
    dp.add_handler(CommandHandler("addwatch", add_watch))
    dp.add_handler(CommandHandler("watchlist", view_watchlist))
    dp.add_handler(CommandHandler("autoreply", enable_auto_reply))
    dp.add_handler(CommandHandler("stopautoreply", disable_auto_reply))
    dp.add_handler(CommandHandler("realtimegraph", real_time_graph))
    dp.add_handler(CommandHandler("stopgraph", stop_real_time_graph))
    dp.add_handler(CommandHandler("setalert", set_alert))
    dp.add_handler(CommandHandler("viewalerts", view_alerts))
    dp.add_handler(CommandHandler("removealert", remove_alert))
    dp.add_handler(CommandHandler("ainews", ai_news_summary))
    dp.add_handler(CommandHandler("sentiment", market_sentiment))
    dp.add_handler(CommandHandler("chatgpt", chatgpt_auto_reply))
    dp.add_handler(CommandHandler("airdrops", airdrops_command))
    dp.add_handler(CommandHandler("portfolio", portfolio_command))
    dp.add_handler(CommandHandler("addcoin", addcoin_command))
    dp.add_handler(CommandHandler("removecoin", removecoin_command))
    dp.add_handler(CommandHandler("clearportfolio", clearportfolio_command))
    dp.add_handler(CommandHandler("dominance", dominance_command))
    dp.add_handler(CommandHandler("predict", predict_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("mywallet", mywallet_command))
    dp.add_handler(CommandHandler("watch", watch_command))
    dp.add_handler(CommandHandler("clearwatch", clear_watchlist))
    dp.add_handler(CommandHandler("removewatch", remove_watch))
    dp.add_handler(CallbackQueryHandler(quiz_response, pattern=r"^quiz\|"))

    dp.add_handler(CallbackQueryHandler(quiz_response, pattern="^quiz\|"))
    dp.add_handler(CallbackQueryHandler(coin_button_handler, pattern="^(bitcoin|ethereum|dogecoin)$"))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, auto_reply_handler))
    # Scheduler
    schedule_digest(updater)

    print("🤖 Bot starting on Vercel Webhook...")

PORT = int(os.environ.get("PORT", 8080))

updater.start_webhook(
    listen="0.0.0.0",
    port=PORT,
    url_path=BOT_TOKEN,
    webhook_url=f"https://crypto-bot-lime.vercel.app//{BOT_TOKEN}"
)

updater.bot.set_webhook(
    f"https://crypto-bot-lime.vercel.app//{BOT_TOKEN}"
)

updater.idle()


if __name__ == '__main__':
    run_bot()