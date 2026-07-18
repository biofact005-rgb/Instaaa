import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import random
import string
from pymongo import MongoClient

# ================= KHAZANA (ENVIRONMENT VARIABLES) =================
# Ye saari keys Render ke 'Environment' tab me set karni hain
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
SMM_API_KEY = os.environ.get("SMM_API_KEY")
SHORTLINK_KEY = os.environ.get("SHORTLINK_KEY")

# Ye public details hain, isko yahi rahne do (Chaho toh change kar lena)
SMM_API_URL = "https://tntsmm.com/api/v2"
SHORTLINK_API = "https://gplinks.in/api"
SERVICE_ID = "123"      # TntSMM me Telegram Reaction ya Insta Like ki actual ID daalna
ORDER_QUANTITY = 20     # Ek baar me kitne reactions dene hain
ORDER_PRICE = 20        # Ek order lagane ke kitne coins katenge

# ================= BOT & DB SETUP =================
bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB Connection
client = MongoClient(MONGO_URI)
db = client['tufani_bot_db']
users_col = db['users']
tokens_col = db['tokens']

# Secret Token Generator
def generate_token(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# ================= BOT LOGIC =================

@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.chat.id
    text = message.text.split()
    
    # Naye user ko DB mein add karo (0 coins ke sath), agar pehle se hai toh ignore karo
    users_col.update_one(
        {'user_id': user_id}, 
        {'$setOnInsert': {'coins': 0}}, 
        upsert=True
    )

    # Agar user Ad dekh kar aaya hai (Token verification)
    if len(text) > 1:
        token = text[1]
        
        # Token ko database me dhoondho
        result = tokens_col.find_one({'token': token})
        
        if result and result['user_id'] == user_id:
            # Token match! User ko 50 coins de do
            users_col.update_one({'user_id': user_id}, {'$inc': {'coins': 50}})
            tokens_col.delete_one({'token': token}) # Token use ho gaya, delete kardo
            
            bot.send_message(user_id, "🎉 *Mubarak ho!* Aapko Ad dekhne ke liye **50 Coins** mil gaye hain!", parse_mode="Markdown")
        else:
            bot.send_message(user_id, "❌ Invalid ya Expired Token! Kripya dubara ad dekhein.")

    # Main Menu bhejo
    user_data = users_col.find_one({'user_id': user_id})
    coins = user_data['coins'] if user_data else 0
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("💰 Earn Coins (Watch Ad)", callback_data="earn_coins"))
    markup.row(InlineKeyboardButton("🚀 Get Free Reactions/Likes", callback_data="buy_order"))
    markup.row(InlineKeyboardButton(f"💳 Balance: {coins} Coins", callback_data="balance"))
    
    bot.send_message(
        user_id, 
        "👋 *Welcome to Tufani Free Bot!*\n\nYahan Ads dekho aur uske badle 100% Free Instagram Likes aur Telegram Reactions pao!", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.message.chat.id
    
    if call.data == "earn_coins":
        bot.answer_callback_query(call.id, "Generating Ad Link...")
        
        # Ek secret token banao aur DB me save karo
        secret_token = generate_token()
        tokens_col.insert_one({'token': secret_token, 'user_id': user_id})
        
        # Deep link banao
        bot_username = bot.get_me().username
        destination_url = f"https://t.me/{bot_username}?start={secret_token}"
        
        # Shortlink API (Gplinks/Shareus) ko hit karo
        try:
            res = requests.get(f"{SHORTLINK_API}?api={SHORTLINK_KEY}&url={destination_url}").json()
            # Alag-alag APIs ka response format alag ho sakta hai, check shortenedUrl ya shortened
            ad_url = res.get('shortenedUrl') or res.get('shortened')
            
            if ad_url:
                bot.send_message(
                    user_id, 
                    f"🔗 **Apne Coins claim karne ke liye is link par click karein aur Ad dekhein:**\n\n👉 {ad_url}\n\n*(Link complete karne ke baad aap automatically bot me wapas aa jayenge aur coins add ho jayenge)*", 
                    parse_mode="Markdown"
                )
            else:
                bot.send_message(user_id, "❌ API error! Ad link generate nahi ho paya. Admin ko batao.")
                
        except Exception as e:
            bot.send_message(user_id, "❌ Abhi Ad Server down hai, thodi der baad try karein.")
            
    elif call.data == "balance":
        user_data = users_col.find_one({'user_id': user_id})
        coins = user_data['coins'] if user_data else 0
        bot.answer_callback_query(call.id, f"Aapke paas {coins} Coins hain!", show_alert=True)
        
    elif call.data == "buy_order":
        user_data = users_col.find_one({'user_id': user_id})
        coins = user_data['coins'] if user_data else 0
        
        if coins >= ORDER_PRICE:
            msg = bot.send_message(user_id, "👇 Apne Instagram Post ya Telegram Message ka **Link** bhejiye:")
            bot.register_next_step_handler(msg, process_order)
        else:
            bot.answer_callback_query(call.id, f"❌ Aapke paas coins nahi hain! (Required: {ORDER_PRICE} Coins)", show_alert=True)

def process_order(message):
    user_id = message.chat.id
    post_link = message.text
    
    bot.send_message(user_id, "⏳ Order place ho raha hai, kripya wait karein...")
    
    # SMM Panel pe order lagao
    payload = {
        'key': SMM_API_KEY,
        'action': 'add',
        'service': SERVICE_ID,
        'link': post_link,
        'quantity': ORDER_QUANTITY
    }
    
    try:
        response = requests.post(SMM_API_URL, data=payload).json()
        
        if 'order' in response: # Agar SMM panel ne Order ID return ki
            # User ke coins kaat lo MongoDB se
            users_col.update_one({'user_id': user_id}, {'$inc': {'coins': -ORDER_PRICE}})
            
            order_id = response['order']
            bot.send_message(
                user_id, 
                f"✅ **Order Successfully Placed!**\n\n🆔 Order ID: `{order_id}`\n🔗 Link: {post_link}\n📉 Baki Coins bache: Check balance.", 
                parse_mode="Markdown"
            )
        else:
            # Agar balance kam hai ya API error hai
            error_msg = response.get('error', 'Unknown Error')
            bot.send_message(user_id, f"❌ SMM Error: {error_msg}\n\nAapke coins nahi kate gaye hain. Kripya baad mein try karein.")
            
    except Exception as e:
        bot.send_message(user_id, "❌ SMM Server se connect nahi ho paya. Owner ko report karein.")

# Bot ko 24/7 on rakhne ka loop
print("🚀 Tufani Bot is running securely with MongoDB...")
bot.infinity_polling()
