import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from telegram.error import Conflict
import requests
import json
import matplotlib.pyplot as plt
import io
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler, MessageHandler, Filters
from pytz import utc
import matplotlib
try:
    import snscrape.modules.twitter as sntwitter
except ImportError:
    print(
        "Warning: snscrape not available. Tweet functionality will be disabled."
    )
    sntwitter = None

matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime

# Logging for errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Token
my_secret = os.environ['BOT_TOKEN']

# Scheduler
scheduler = BackgroundScheduler(timezone=utc)
scheduler.start()
btc_job = None

# Start Command

user_watchlist = {}
auto_reply_users = set()
user_alerts = {}
real_time_graphs = {}
price_history = {}
alerts_db = {}
share_link = {}
user_portfolios = {}


def toggle_auto_reply(update, context):
    user_id = str(update.effective_user.id)
    if user_id in auto_reply_users:
        auto_reply_users.remove(user_id)
        update.message.reply_text("🔕 Auto price reply disabled.")
    else:
        auto_reply_users.add(user_id)
        update.message.reply_text(
            "🔔 Auto price reply enabled! Just type any coin name.")


def auto_reply_handler(update, context):
    user_id = str(update.effective_user.id)
    if user_id not in auto_reply_users:
        return

    text = update.message.text.lower().strip()

    # First check if it's a question for AI response
    ai_question_handler(update, context)

    # Then check if it's a potential coin name (no spaces, alphabetic)
    if text.isalpha() and len(text) > 2:
        price_info = get_price(text)
        if "not found" not in price_info and "Error" not in price_info:
            update.message.reply_text(f"💰 {price_info}")


def add_watch(update, context):
    user_id = str(update.effective_user.id)
    if not context.args:
        update.message.reply_text("Usage: /addwatch bitcoin")
        return

    coin = context.args[0].lower()
    user_watchlist.setdefault(user_id, set()).add(coin)
    update.message.reply_text(f"✅ Added *{coin}* to your watchlist.",
                              parse_mode='Markdown')


def view_watchlist(update, context):
    user_id = str(update.effective_user.id)
    coins = user_watchlist.get(user_id, set())

    if not coins:
        update.message.reply_text("📭 Your watchlist is empty.")
        return

    reply = "📋 *Your Watchlist:*\n\n"
    for coin in coins:
        reply += f"{get_price(coin)}\n\n"

    update.message.reply_text(reply, parse_mode='Markdown')


def ai_news_summary(update, context):
    if not context.args:
        update.message.reply_text("Usage: /ainews bitcoin")
        return

    coin = context.args[0].lower()

    try:
        # Get coin info from CoinGecko
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            update.message.reply_text(
                f"❌ Could not find information for {coin}")
            return

        data = response.json()

        # Extract relevant information
        name = data.get('name', coin.capitalize())
        description = data.get('description', {}).get('en', '')
        market_data = data.get('market_data', {})

        current_price = market_data.get('current_price', {}).get('inr', 0)
        price_change_24h = market_data.get('price_change_percentage_24h', 0)
        market_cap_rank = data.get('market_cap_rank', 'N/A')

        # Get latest news from description and market data
        news_summary = f"""
🤖 AI SUMMARY FOR {name.upper()}

📊 Current Status:
• Price: ₹{current_price:,}
• 24h Change: {price_change_24h:.2f}%
• Market Rank: #{market_cap_rank}

📝 Project Overview:
{description[:800]}...

💡 Key Insights:
• {'Bullish trend' if price_change_24h > 0 else 'Bearish trend'} in last 24h
• {'Strong market position' if isinstance(market_cap_rank, int) and market_cap_rank <= 50 else 'Emerging project'}
• {'High volatility' if abs(price_change_24h) > 5 else 'Stable price action'}

⚠️ This is automated analysis. Do your own research!
        """

        update.message.reply_text(news_summary.strip(), parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"❌ Error generating AI summary: {str(e)}")
        logger.error(f"AI summary error: {e}")


def market_sentiment(update, context):
    try:
        # Get Fear & Greed Index
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
            update.message.reply_text(
                "❌ Could not fetch market sentiment data")

    except Exception as e:
        update.message.reply_text(f"❌ Error analyzing sentiment: {str(e)}")


def chatgpt_auto_reply(update, context):
    """AI-powered auto-reply for crypto questions"""
    user_id = str(update.effective_user.id)

    if user_id in auto_reply_users:
        auto_reply_users.remove(user_id)
        update.message.reply_text("🤖 ChatGPT Auto-Reply disabled.")
    else:
        auto_reply_users.add(user_id)
        update.message.reply_text(
            "🤖 ChatGPT Auto-Reply enabled! Ask me any crypto question.")


def ai_question_handler(update, context):
    """Handle crypto questions with AI responses"""
    user_id = str(update.effective_user.id)
    if user_id not in auto_reply_users:
        return

    text = update.message.text.lower()

    # Common crypto questions
    if any(keyword in text for keyword in
           ['what is', 'how to', 'why', 'when', 'where', 'explain', '?']):
        responses = {
            'bitcoin':
            "🟠 Bitcoin is the first cryptocurrency, created by Satoshi Nakamoto in 2009. It's digital money that works without banks!",
            'ethereum':
            "⚡ Ethereum is a blockchain platform that runs smart contracts. It's like a computer that runs apps decentralized!",
            'blockchain':
            "⛓️ Blockchain is a digital ledger that records transactions across many computers. Think of it as an unbreakable record book!",
            'mining':
            "⛏️ Mining is the process of validating transactions and creating new coins. Miners use powerful computers to solve complex puzzles!",
            'wallet':
            "👛 A crypto wallet stores your digital coins. It's like a bank account but you control it completely!",
            'defi':
            "🏦 DeFi (Decentralized Finance) lets you do banking without banks - lending, borrowing, trading, all on blockchain!",
            'nft':
            "🎨 NFTs are unique digital items on blockchain. Think digital art, collectibles, or game items that you truly own!",
            'staking':
            "🥩 Staking is like earning interest on your crypto. You lock up coins to help secure the network and get rewards!"
        }

        for keyword, response in responses.items():
            if keyword in text:
                update.message.reply_text(f"🤖 AI Answer:\n\n{response}")
                return

        # Generic helpful response
        update.message.reply_text(
            "🤖 Great question! For detailed crypto info, use /ainews <coin> or /price <coin>. I'm here to help! 💪"
        )


def airdrops_command(update, context):
    """Show active airdrops and opportunities"""
    try:
        airdrops_info = """
🪂 *ACTIVE AIRDROPS & OPPORTUNITIES*

🔥 *Current Hot Airdrops:*

🌟 **LayerZero (ZRO)**
• Status: Live on exchanges
• How: Bridge between chains on LayerZero protocols
• Reward: Up to $1000+ per wallet

💎 **Blast Network**
• Status: Points system active
• How: Deposit ETH/USDB on Blast.io
• Reward: Blast tokens + yield

🚀 **zkSync Era**
• Status: Rumored airdrop
• How: Use zkSync Era DEXs and bridges
• Reward: ZK tokens (speculative)

⭐ **Arbitrum Odyssey**
• Status: Ongoing
• How: Complete tasks on Arbitrum
• Reward: NFTs + potential tokens

🎯 **Polygon zkEVM**
• Status: Testnet rewards
• How: Use Polygon zkEVM testnet
• Reward: Early adopter rewards

⚠️ *SAFETY TIPS:*
• Never share private keys
• Always verify official channels
• Start with small amounts
• Do your own research (DYOR)

💡 Use /portfolio to track your airdrop earnings!
        """

        update.message.reply_text(airdrops_info, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"❌ Error fetching airdrops: {str(e)}")


# Portfolio tracking
user_portfolios = {}
user_portfolios = {}


def portfolio_command(update, context):
    user_id = str(update.effective_user.id)

    if len(context.args) == 0:
        # Show Portfolio
        if user_id not in user_portfolios or not user_portfolios[user_id]:
            update.message.reply_text(
                """📊 *YOUR CRYPTO PORTFOLIO*\n\n💼 Portfolio is empty!\n\n📝 *Add coins with:*\n/portfolio add bitcoin 0.5 45000\n/portfolio add ethereum 2.0 30000\n\n📈 *Commands:*\n• /portfolio - View portfolio\n• /portfolio add <coin> <amount> <buy_price>\n• /portfolio remove <coin>\n• /portfolio clear - Clear all\n\n💡 Track your investments and see profits/losses!""",
                parse_mode='Markdown')
            return

        portfolio = user_portfolios[user_id]
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
                profit_percent = (profit_loss / invested) * 100

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
                reply += f"⚠️ *{coin.upper()}* - Failed to fetch price\n\n"

        total_pl = total_value - total_invested
        total_pl_percent = (total_pl /
                            total_invested) * 100 if total_invested > 0 else 0
        pl_emoji = "🟢" if total_pl > 0 else "🔴" if total_pl < 0 else "⚪"

        reply += "📋 *PORTFOLIO SUMMARY*\n"
        reply += f"💰 Total Invested: ₹{total_invested:,.2f}\n"
        reply += f"💎 Current Value: ₹{total_value:,.2f}\n"
        reply += f"{pl_emoji} Total P&L: ₹{total_pl:,.2f} ({total_pl_percent:+.2f}%)"

        update.message.reply_text(reply, parse_mode='Markdown')
        return  # Prevent going to below code accidentally

    # ADD COIN
    if context.args[0].lower() == 'add':
        if len(context.args) < 4:
            update.message.reply_text(
                "❌ Usage: /portfolio add bitcoin 0.5 45000")
            return

        coin = context.args[1].lower()
        try:
            amount = float(context.args[2])
            buy_price = float(context.args[3])
            if user_id not in user_portfolios:
                user_portfolios[user_id] = {}

            user_portfolios[user_id][coin] = {
                'amount': amount,
                'buy_price': buy_price
            }

            update.message.reply_text(
                f"✅ Added {amount} {coin.upper()} at ₹{buy_price:,} to your portfolio!"
            )
        except:
            update.message.reply_text("❌ Invalid amount or price.")

    # REMOVE COIN
    elif context.args[0].lower() == 'remove':
        if len(context.args) < 2:
            update.message.reply_text("❌ Usage: /portfolio remove bitcoin")
            return

        coin = context.args[1].lower()
        if user_id in user_portfolios and coin in user_portfolios[user_id]:
            del user_portfolios[user_id][coin]
            update.message.reply_text(
                f"✅ Removed {coin.upper()} from portfolio.")
        else:
            update.message.reply_text(f"❌ {coin.upper()} not found.")

    # CLEAR
    elif context.args[0].lower() == 'clear':
        user_portfolios[user_id] = {}
        update.message.reply_text("✅ Portfolio cleared!")

    # INVALID
    else:
        update.message.reply_text(
            "❌ Unknown subcommand. Use /portfolio for help.")


def dominance_command(update, context):
    """Show market dominance data"""
    try:
        # Get global market data
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

        # Get top 10 coins for detailed dominance
        coins_url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=10&page=1"
        coins_response = requests.get(coins_url, timeout=10)

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

        if coins_response.status_code == 200:
            coins = coins_response.json()
            other_dominance = 0

            for i, coin in enumerate(coins[2:8], 3):  # Skip BTC and ETH
                symbol = coin['symbol'].upper()
                market_cap = coin['market_cap']
                dominance = (market_cap / (total_market_cap * 1e12)) * 100
                other_dominance += dominance

                medal = "🥉" if i == 3 else f"{i}."
                dominance_text += f"{medal} {symbol}: {dominance:.1f}%\n"

            dominance_text += f"\n🔸 Others: {100 - btc_dominance - eth_dominance - other_dominance:.1f}%"

        dominance_text += "\n\n💡 High BTC dominance = Alt season might be coming"
        dominance_text += "\n💡 Low BTC dominance = Alt coins are pumping"

        update.message.reply_text(dominance_text, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"❌ Error fetching dominance: {str(e)}")


def predict_command(update, context):
    """AI-powered price prediction based on technical indicators"""
    if not context.args:
        update.message.reply_text("Usage: /predict bitcoin")
        return

    coin = context.args[0].lower()

    try:
        # Get historical data for analysis
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

        # Simple technical analysis
        current_price = prices[-1]
        week_ago = prices[-7] if len(prices) >= 7 else prices[0]
        month_ago = prices[0]

        # Calculate moving averages
        ma7 = sum(prices[-7:]) / 7
        ma14 = sum(prices[-14:]) / 14 if len(prices) >= 14 else ma7
        ma30 = sum(prices) / len(prices)

        # Volume analysis
        avg_volume = sum(volumes[-7:]) / 7
        current_volume = volumes[-1]

        # Price changes
        week_change = ((current_price - week_ago) / week_ago) * 100
        month_change = ((current_price - month_ago) / month_ago) * 100

        # Simple prediction logic
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

        # Generate prediction
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
Always do your own research (DYOR)!
        """

        update.message.reply_text(prediction_text, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"❌ Error generating prediction: {str(e)}")
        logger.error(f"Prediction error: {e}")


def share(update, context):
    bot_username = "@mycryptotracker007_bot"
    share_link = f"https://t.me/{bot_username}?start"
    update.message.reply_text(f"🔗 Share this bot:\n{share_link}")


def get_price_with_logo(coin):
    try:
        # First try direct coin ID search
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            info = response.json()
            image = info['image']['large']
            price = info['market_data']['current_price']['inr']
            name = info['name']
            symbol = info['symbol'].upper()
            market_cap_rank = info.get('market_cap_rank', 'N/A')
            change_24h = info['market_data'].get('price_change_percentage_24h',
                                                 0)

            trend_emoji = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"

            caption = (f"💰 *{name}* ({symbol}) {trend_emoji}\n"
                       f"💵 Price: ₹{price:,}\n"
                       f"📊 24h Change: {change_24h:+.2f}%\n"
                       f"🏆 Rank: #{market_cap_rank}")

            return image, caption
        else:
            # If direct search fails, try searching by name/symbol
            search_url = f"https://api.coingecko.com/api/v3/search?query={coin}"
            search_response = requests.get(search_url, timeout=10)

            if search_response.status_code == 200:
                search_data = search_response.json()

                # Check coins first
                if search_data.get('coins'):
                    coin_id = search_data['coins'][0]['id']
                    return get_price_with_logo(coin_id)

                # Then check categories/exchanges if no coins found
                elif search_data.get('categories'):
                    return None, f"🔍 Found category '{coin}' but no specific coin. Try a more specific name."

                else:
                    return None, f"❌ No results found for '{coin}'. Try another name or symbol."

            return None, f"❌ Coin '{coin}' not found."

    except requests.exceptions.Timeout:
        return None, "⏱️ Request timeout - Try again later"
    except Exception as e:
        return None, f"❌ Error fetching data: {str(e)}"


def logo_price_command(update, context):
    if len(context.args) == 0:
        update.message.reply_text("Usage: /logoprice bitcoin\n"
                                  "💡 You can search by:\n"
                                  "• Coin name (bitcoin, ethereum)\n"
                                  "• Symbol (btc, eth, doge)\n"
                                  "• Token name (shiba-inu, chainlink)")
        return

    coin = context.args[0].lower().strip()

    # Show loading message for better UX
    loading_msg = update.message.reply_text("🔍 Searching for coin data...")

    image, msg = get_price_with_logo(coin)

    # Delete loading message
    context.bot.delete_message(chat_id=update.effective_chat.id,
                               message_id=loading_msg.message_id)

    if image:
        update.message.reply_photo(photo=image,
                                   caption=msg,
                                   parse_mode='Markdown')
    else:
        update.message.reply_text(msg)


def inline_query(update, context):
    query = update.inline_query.query.strip().lower()
    if not query:
        return

    result_text = get_price(query)  # Must return a string
    results = [
        InlineQueryResultArticle(
            id=query,
            title=f"💸 Price of {query.capitalize()}",
            input_message_content=InputTextMessageContent(result_text))
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
            dates = [datetime.fromtimestamp(p[0] / 1000)
                     for p in data[-24:]]  # Last 24 hours
            prices = [p[1] for p in data[-24:]]

            plt.figure(figsize=(12, 6))
            plt.plot(dates,
                     prices,
                     label=f"{coin.upper()} Live Price",
                     color='green',
                     linewidth=2)
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

            context.bot.send_photo(chat_id=chat_id,
                                   photo=buffer,
                                   caption=caption)
            buffer.close()
            plt.close()

        except Exception as e:
            logger.error(f"Real-time graph error: {e}")

    # Start real-time updates every 5 minutes
    if user_id not in real_time_graphs:
        real_time_graphs[user_id] = {}

    if coin in real_time_graphs[user_id]:
        update.message.reply_text(
            f"⚠️ Real-time graph for {coin} already running!")
        return

    # Send initial graph
    update_graph()

    # Schedule periodic updates
    job = scheduler.add_job(update_graph,
                            'interval',
                            minutes=5,
                            id=f"graph_{user_id}_{coin}")
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


def graph_command(update, context):
    if len(context.args) == 0:
        update.message.reply_text("Usage: /graph bitcoin")
        return

    coin = context.args[0].lower()
    url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=inr&days=7"
    response = requests.get(url)

    if response.status_code != 200:
        update.message.reply_text("❌ Coin not found or API error.")
        return

    data = response.json()['prices']
    dates = [datetime.fromtimestamp(p[0] / 1000) for p in data]
    prices = [p[1] for p in data]

    plt.figure(figsize=(10, 4))
    plt.plot(prices, label=f"{coin.upper()} Price")
    plt.title(f"{coin.upper()} - Last 7 Days (INR)")
    plt.xlabel("Date")
    plt.ylabel("Price ₹")
    plt.grid(True)
    plt.legend()

    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    update.message.reply_photo(photo=buffer)
    
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

# Help Command
def plot_command(update: Update, context: CallbackContext):
    update.message.reply_text("Generating price plot...")
    send_price_plot(update, context)


def send_price_plot(update: Update, context: CallbackContext):
    try:
        # Get actual price data
        coins = ['Bitcoin', 'Ethereum', 'Dogecoin']
        coin_ids = ['bitcoin', 'ethereum', 'dogecoin']
        prices = []

        # Fetch all coin prices properly
        coin_ids_str = ','.join(coin_ids)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids_str}&vs_currencies=inr"
        response = requests.get(url, timeout=10)
        data = response.json()

        for coin_id in coin_ids:
            if coin_id in data and 'inr' in data[coin_id]:
                prices.append(data[coin_id]['inr'])
            else:
                prices.append(0)

        plt.figure(figsize=(10, 6))
        plt.bar(coins, prices, color=['gold', 'silver', 'green'])
        plt.title('Cryptocurrency Prices (INR)')
        plt.ylabel('Price in ₹')
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Save the plot to a BytesIO object
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)

        # Send the plot as a photo
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=buf)
        buf.close()
        plt.close()  # Close the plot to free memory

    except Exception as e:
        update.message.reply_text(f"❌ Error generating plot: {str(e)}")
        logger.error(f"Plot error: {e}")


def help_command(update: Update, context: CallbackContext):
    help_text = ("📋 *CryptoTracker Pro - Command Center*\n"
                 "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                 "🤖 *AI-POWERED ANALYTICS*\n"
                 "• `/predict <coin>` - Advanced AI price predictions\n"
                 "• `/sentiment` - Real-time market sentiment analysis\n"
                 "• `/ainews <coin>` - AI-curated news summaries\n"
                 "• `/chatgpt` - Toggle intelligent Q&A mode\n"
                 "• `/dominance` - Market cap dominance insights\n\n"
                 "💼 *PORTFOLIO MANAGEMENT*\n"
                 "• `/portfolio` - Professional P&L tracking\n"
                 "• `/addwatch <coin>` - Build your watchlist\n"
                 "• `/watchlist` - Monitor saved investments\n"
                 "• `/setalert <coin> <above/below> <price>` - Smart alerts\n"
                 "• `/viewalerts` - Active alert dashboard\n\n"
                 "📊 *REAL-TIME DATA & CHARTS*\n"
                 "• `/price <coin>` - Live INR prices\n"
                 "• `/trending` - Top market movers\n"
                 "• `/coinlist` - Top 20 by market cap\n"
                 "• `/graph <coin>` - 7-day technical charts\n"
                 "• `/realtimegraph <coin>` - Live updating charts\n"
                 "• `/logoprice <coin>` - Price with official logos\n\n"
                 "⚡ *QUICK ACCESS*\n"
                 "• `/btc` `/eth` `/doge` - Instant major coin prices\n"
                 "• `/coins` - Interactive coin selector\n"
                 "• `/autobtc` - Auto Bitcoin price updates\n\n"
                 "🪂 *OPPORTUNITIES*\n"
                 "• `/airdrops` - Active airdrop opportunities\n"
                 "• `/tweets <coin>` - Latest crypto news\n\n"
                 "📱 *Get Started:* `/price bitcoin` or `/trending`\n"
                 "💡 *Pro Tip:* Enable `/autoreply` for hands-free updates")
    update.message.reply_text(help_text, parse_mode='Markdown')


# Price Fetch


def get_price(coin):
    try:
        coin = coin.strip().lower()

        # Get comprehensive data for professional display
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            name = data.get('name', coin.capitalize())
            symbol = data.get('symbol', '').upper()
            market_data = data.get('market_data', {})

            price = market_data.get('current_price', {}).get('inr', 0)
            change_24h = market_data.get('price_change_percentage_24h', 0)
            market_cap_rank = data.get('market_cap_rank', 'N/A')

            # Professional formatting
            trend_icon = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
            change_color = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"

            return (f"💎 *{name}* ({symbol}) {change_color}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **₹{price:,.2f}** INR\n"
                    f"{trend_icon} 24h: **{change_24h:+.2f}%**\n"
                    f"🏆 Rank: **#{market_cap_rank}**\n"
                    f"⏰ *Live Data*")
        else:
            # Fallback to simple price API
            simple_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr"
            simple_response = requests.get(simple_url, timeout=10)

            if simple_response.status_code == 200:
                simple_data = simple_response.json()
                if coin in simple_data and 'inr' in simple_data[coin]:
                    price = simple_data[coin]["inr"]
                    return f"💰 **{coin.capitalize()}** → ₹{price:,.2f}"

            return f"❌ Coin '{coin}' not found. Try `/coinlist` to see available coins."

    except requests.exceptions.Timeout:
        return "⏱️ Market data temporarily unavailable. Please try again."
    except Exception:
        return "⚠️ Unable to fetch price data. Try again in a moment."


# Price Command


def price(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        update.message.reply_text(
            "❌ Please provide a coin name like bitcoin or ethereum.")
        return
    coin = context.args[0].lower()
    msg = get_price(coin)
    update.message.reply_text(msg, parse_mode='Markdown')


# Shortcuts


def btc_command(update: Update, context: CallbackContext):
    update.message.reply_text(get_price('bitcoin'))


def eth_command(update: Update, context: CallbackContext):
    update.message.reply_text(get_price('ethereum'))


def doge_command(update: Update, context: CallbackContext):
    update.message.reply_text(get_price('dogecoin'))


# Inline Buttons


def price_buttons(update: Update, context: CallbackContext):
    keyboard = [[
        InlineKeyboardButton("Bitcoin 💰", callback_data='bitcoin'),
        InlineKeyboardButton("Ethereum ⚡", callback_data='ethereum'),
        InlineKeyboardButton("Dogecoin 🐶", callback_data='dogecoin'),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Select a coin:', reply_markup=reply_markup)


def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    coin = query.data
    query.answer()
    query.edit_message_text(get_price(coin))


# Fancy Command


def fancy_command(update: Update, context: CallbackContext):
    if context.args:
        coin = context.args[0].strip().lower()
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr"
            response = requests.get(url)
            data = response.json()
            if coin in data:
                price = data[coin]["inr"]
                reply = f"✨ *{coin.capitalize()}* \nPrice: ₹{price}"
            else:
                reply = f"❌ Coin '{coin}' not found."
            update.message.reply_text(reply, parse_mode='Markdown')
        except Exception as e:
            update.message.reply_text(f"⚠️ Error: {e}")
    else:
        update.message.reply_text("Usage: /fancy bitcoin")


# Auto BTC Update


def get_btc_price():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=inr'
    response = requests.get(url)
    data = response.json()
    return data['bitcoin']['inr']


def auto_btc(update: Update, context: CallbackContext):
    global btc_job
    chat_id = update.effective_chat.id  # Get the chat ID of the user who sent the command

    def send_btc_price():
        try:
            price = get_btc_price()
            context.bot.send_message(chat_id=chat_id,
                                     text=f"💰 Live BTC Price: ₹{price}")
        except Exception as e:
            logger.error(f"Error: {e}")

    if btc_job:
        update.message.reply_text("🔁 Auto BTC is already running.")
    else:
        btc_job = scheduler.add_job(send_btc_price, 'interval', seconds=60)
        update.message.reply_text(
            "✅ Auto BTC updates started (every 60 seconds).")


alerts_db = {}  # GLOBAL dictionary


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
        price = float(context.args[2])
    except ValueError:
        update.message.reply_text("❌ Invalid price.")
        return

    if direction not in ["above", "below"]:
        update.message.reply_text("Use 'above' or 'below' only.")
        return

    if user_id not in alerts_db:
        alerts_db[user_id] = []

    alert = {"coin": coin, "direction": direction, "price": price}
    alerts_db[user_id].append(alert)

    update.message.reply_text(
        f"✅ Alert set! You'll be notified when {coin.upper()} goes {direction} ₹{price:,}"
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
        alerts_db[user_id] = [
            a for a in alerts_db[user_id] if a['coin'] != coin
        ]

        after = len(alerts_db[user_id])
        if before > after:
            update.message.reply_text(f"✅ Removed alert for {coin.upper()}")
        else:
            update.message.reply_text(f"⚠️ No alert found for {coin.upper()}")
    else:
        update.message.reply_text("⚠️ No alerts set.")


def stop_btc(update: Update, context: CallbackContext):
    global btc_job
    if btc_job:
        btc_job.remove()
        btc_job = None
        update.message.reply_text("⛔ Auto BTC updates stopped.")
    else:
        update.message.reply_text("⚠️ Auto BTC is not running.")


# Trending


def trending_command(update: Update, context: CallbackContext):
    try:
        # Get real trending coins from CoinGecko
        trending_url = "https://api.coingecko.com/api/v3/search/trending"
        trending_response = requests.get(trending_url, timeout=15)

        if trending_response.status_code == 200:
            trending_data = trending_response.json()
            trending_coins = [
                coin['item']['id'] for coin in trending_data['coins'][:5]
            ]
        else:
            # Fallback to top coins
            trending_coins = [
                'bitcoin', 'ethereum', 'tether', 'binancecoin', 'solana'
            ]

        # Get detailed market data
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=inr&ids={','.join(trending_coins)}&order=market_cap_desc&per_page=5&page=1"
        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            update.message.reply_text(
                "📊 Market data temporarily unavailable. Please try again.")
            return

        coins = response.json()

        reply = "🔥 *TRENDING CRYPTO MARKETS*\n"
        reply += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, coin in enumerate(coins, 1):
            name = coin['name']
            symbol = coin['symbol'].upper()
            price = coin['current_price']
            change_24h = coin['price_change_percentage_24h'] or 0
            market_cap = coin['market_cap']

            # Professional icons and formatting
            trend_icon = "🚀" if change_24h > 5 else "📈" if change_24h > 0 else "📉" if change_24h < -5 else "📊"
            change_color = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "⚪"

            reply += f"{trend_icon} **{i}. {name}** ({symbol}) {change_color}\n"
            reply += f"💰 ₹{price:,.2f} | 24h: **{change_24h:+.2f}%**\n"
            reply += f"📊 MCap: ₹{market_cap/1e7:.1f}Cr\n\n"

        reply += "💡 *Use* `/price <coin>` *for detailed analysis*\n"
        reply += "📈 *Market data updates every minute*"

        update.message.reply_text(reply, parse_mode='Markdown')

    except requests.exceptions.Timeout:
        update.message.reply_text(
            "⏱️ Market data loading... Please try again in a moment.")
    except Exception as e:
        update.message.reply_text(
            "📊 Unable to fetch trending data. Market may be experiencing high volatility."
        )
        logger.error(f"Trending command error: {e}")


# Coin List


def coinList_command(update: Update, context: CallbackContext):
    try:
        # Get top 20 coins by market cap with prices
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

            # Add emoji based on price change
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


def status_command(update, context):
    try:
        update.message.reply_text("✅ Bot is alive!")
    except Exception as e:
        print(f"/status error: {e}")


# Main


def main():
    if 'BOT_TOKEN' not in os.environ:
        print("❌ BOT_TOKEN environment variable not set!")
        return
from keep_alive import keep_alive
keep_alive()
        updater = Updater(token=my_secret, use_context=True)
        dp = updater.dispatcher

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
        dp.add_handler(CommandHandler("autoreply", toggle_auto_reply))
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
        dp.add_handler(CommandHandler("dominance", dominance_command))
        dp.add_handler(CommandHandler("predict", predict_command))
        dp.add_handler(CommandHandler("status", status_command))

        dp.add_handler(
            MessageHandler(Filters.text & ~Filters.command,
                           auto_reply_handler))

        print("🤖 Bot starting...")
        updater.start_polling(drop_pending_updates=True)
        print("✅ Bot is running!")
        updater.idle()

    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        print(f"❌ Bot failed to start: {e}")
if __name__ == '__main__':
    main()
