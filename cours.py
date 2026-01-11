import telebot
from telebot import types
import psycopg2
import time
import os
import urllib.parse as urlparse

# ================= কনফিগারেশন =================
API_TOKEN = '8405621803:AAHOAVRDSP5cmbEiCmitXRbqOmwqe3I0naE'
ADMIN_ID = 7710861687
DEFAULT_CHANNELS = ['@todayinstantoffer', '@instantoffertoday', '@MAHIDAdvancePanel']

# ডাটাবেস ইউআরএল (Render এর Environment Variable থেকে নিবে)
# যদি লোকালি টেস্ট করেন, তাহলে এখানে স্ট্রিং বসাতে পারেন, তবে সার্ভারে os.environ লাগবে
DATABASE_URL = os.environ.get('DATABASE_URL')

bot = telebot.TeleBot(API_TOKEN)

# ডাটাবেস কানেকশন ফাংশন
def get_db_connection():
    url = urlparse.urlparse(DATABASE_URL)
    dbname = url.path[1:]
    user = url.username
    password = url.password
    host = url.hostname
    port = url.port
    
    conn = psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port
    )
    return conn

# টেবিল তৈরি (PostgreSQL সিনট্যাক্স)
def setup_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        balance INTEGER DEFAULT 0,
                        total_refer INTEGER DEFAULT 0,
                        referred_by BIGINT,
                        joined_date TEXT
                    )''')
    
    # SERIAL ব্যবহার করা হয়েছে AUTOINCREMENT এর বদলে
    cursor.execute('''CREATE TABLE IF NOT EXISTS courses (
                        id SERIAL PRIMARY KEY,
                        name TEXT,
                        photo_id TEXT,
                        description TEXT,
                        fee INTEGER
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (
                        username TEXT PRIMARY KEY
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value INTEGER
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS coupons (
                        code TEXT PRIMARY KEY,
                        amount INTEGER,
                        usage_limit INTEGER,
                        used_count INTEGER DEFAULT 0
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS used_coupons (
                        user_id BIGINT,
                        code TEXT
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS trending (
                        id SERIAL PRIMARY KEY,
                        photo_id TEXT,
                        caption TEXT
                    )''')

    # ডিফল্ট চ্যানেল সেটআপ
    for ch in DEFAULT_CHANNELS:
        try:
            cursor.execute("INSERT INTO channels (username) VALUES (%s) ON CONFLICT DO NOTHING", (ch,))
        except:
            pass
    
    # ডিফল্ট রেফার বোনাস
    cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING", ('refer_bonus', 1))
    
    conn.commit()
    cursor.close()
    conn.close()

# ডাটাবেস সেটআপ রান করা
try:
    setup_db()
except Exception as e:
    print(f"Database Setup Error: {e}")

# ================= হেল্পার ফাংশন =================

def check_membership(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM channels")
    channels = cursor.fetchall()
    cursor.close()
    conn.close()
    
    not_joined = []
    for ch in channels:
        channel_username = ch[0]
        try:
            status = bot.get_chat_member(channel_username, user_id).status
            if status not in ['creator', 'administrator', 'member']:
                not_joined.append(channel_username)
        except:
            pass
    return not_joined

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def register_user(user_id, referrer_id=None):
    if not get_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        current_date = time.strftime("%Y-%m-%d")
        
        cursor.execute("INSERT INTO users (user_id, referred_by, joined_date) VALUES (%s, %s, %s)",
                       (user_id, referrer_id, current_date))
        conn.commit()

        if referrer_id and referrer_id != user_id:
            cursor.execute("SELECT value FROM settings WHERE key='refer_bonus'")
            bonus = cursor.fetchone()[0]
            cursor.execute("UPDATE users SET balance = balance + %s, total_refer = total_refer + 1 WHERE user_id=%s", (bonus, referrer_id))
            conn.commit()
            try:
                bot.send_message(referrer_id, f"**🎉 আপনার রেফারেল লিংক দিয়ে নতুন একজন জয়েন করেছে! আপনি +{bonus} পয়েন্ট পেয়েছেন।**", parse_mode='Markdown')
            except:
                pass
        
        cursor.close()
        conn.close()
        return True
    return False

# ================= কীবোর্ড মেনু =================

def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 My Account")
    markup.add("📚 Available Course", "🔥 Trending Course")
    markup.add("💰 Add Credit", "🔗 Refer To Credit")
    markup.add("🎟 My Coupons", "☎️ Support Admin")
    return markup

# ================= স্টার্ট এবং জয়েন চেকিং =================

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            val = args[1]
            if val.startswith("ref_"):
                referrer_id = int(val.replace("ref_", ""))
            else:
                referrer_id = int(val)
        except:
            pass

    not_joined = check_membership(user_id)

    if not_joined:
        markup = types.InlineKeyboardMarkup()
        for ch in not_joined:
            markup.add(types.InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@', '')}"))

        ref_data = f"verify_{referrer_id}" if referrer_id else "verify_none"
        markup.add(types.InlineKeyboardButton("✅ Verified / Joined", callback_data=ref_data))

        bot.send_message(user_id, "**⚠️ দয়া করে নিচের চ্যানেলগুলোতে জয়েন করুন, অন্যথায় আপনি বট ব্যবহার করতে পারবেন না।**", reply_markup=markup, parse_mode='Markdown')
    else:
        if not get_user(user_id):
            register_user(user_id, referrer_id)
        
        welcome_text = """👋 স্বাগতম — Education For All!

🎓 রেফার করে ফ্রি প্রিমিয়াম কোর্স আনলক করুন।
━━━━━━━━━━━━━━━━
🙌 দ্রুত Course ফ্রি পেতে :
1️⃣ নিচের রেফারেল লিংক শেয়ার করুন  
2️⃣ প্রতিটি জয়েন = +1 Point  
3️⃣ ১০ Point হলে কোর্স ক্লেইম করুন (১০০% ফ্রি) 🎉

✅ স্বাগতম! মেইন মেনু থেকে অপশন সিলেক্ট করুন।"""
        
        bot.send_photo(user_id, "https://i.ibb.co.com/nNrbHB5p/IMG-20260110-213219-375.jpg", caption=f"**{welcome_text}**", reply_markup=main_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('verify_'))
def verify_join(call):
    user_id = call.message.chat.id
    referrer_str = call.data.split('_')[1]
    referrer_id = int(referrer_str) if referrer_str != "none" else None

    not_joined = check_membership(user_id)

    if not_joined:
        bot.answer_callback_query(call.id, "❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি!", show_alert=True)
    else:
        register_user(user_id, referrer_id)
        bot.delete_message(user_id, call.message.message_id)
        
        welcome_text = """👋 স্বাগতম — Education For All!

🎓 রেফার করে ফ্রি প্রিমিয়াম কোর্স আনলক করুন।
━━━━━━━━━━━━━━━━
🙌 দ্রুত Course ফ্রি পেতে :
1️⃣ নিচের রেফারেল লিংক শেয়ার করুন  
2️⃣ প্রতিটি জয়েন = +1 Point  
3️⃣ ১০ Point হলে কোর্স ক্লেইম করুন (১০০% ফ্রি) 🎉

✅ স্বাগতম! মেইন মেনু থেকে অপশন সিলেক্ট করুন।"""

        bot.send_photo(user_id, "https://i.ibb.co.com/nNrbHB5p/IMG-20260110-213219-375.jpg", caption=f"**{welcome_text}**", reply_markup=main_menu_keyboard(), parse_mode='Markdown')

# ================= বাটন হ্যান্ডলার =================

@bot.message_handler(func=lambda message: message.text in ["👤 My Account", "📚 Available Course", "🔥 Trending Course", "🔗 Refer To Credit", "💰 Add Credit", "🎟 My Coupons", "☎️ Support Admin", "🔙 Back"])
def menu_handler(message):
    user_id = message.chat.id

    if message.text == "🔙 Back":
        bot.send_message(user_id, "**🏠 মেইন মেনুতে ফিরে আসা হয়েছে।**", reply_markup=main_menu_keyboard(), parse_mode='Markdown')
        return

    if check_membership(user_id):
        bot.send_message(user_id, "**⚠️ আপনাকে চ্যানেলগুলো জয়েন থাকতে হবে। /start দিয়ে আবার চেষ্টা করুন।**", parse_mode='Markdown')
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    if message.text == "👤 My Account":
        user = get_user(user_id)
        raw_name = message.from_user.first_name
        user_name = raw_name.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") if raw_name else "User"
        bot_username = bot.get_me().username
        
        msg = f"""
**👤 আপনার প্রোফাইল**

**🧾 নাম: {user_name}**
**🆔 ID: {user[0]}**
**💎 পয়েন্ট: {user[1]}** 
**🔗 আপনার লিংক: https://t.me/{bot_username}?start=ref\_{user[0]}**

**🎯 লক্ষ্য: ১০ পয়েন্ট পূর্ণ করে কোর্স আনলক করুন**
        """
        bot.send_photo(user_id, "https://i.ibb.co.com/9kcjQD3c/IMG-20260110-213233-448.jpg", caption=msg, parse_mode='Markdown')

    elif message.text == "🔗 Refer To Credit":
        bot_username = bot.get_me().username
        link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        msg = f"""
**🔗 Invite & Earn**

**আপনি সহজ পথে ফ্রি কোর্স পেতে চান? নিচের লিংক শেয়ার করুন:**

**📎 আপনার লিংক:**
`{link}`

**🎯 নিয়ম:**
**👥 ১ জন জয়েন = +1 Point**
**🔟 ১০ Point = ১টি প্রিমিয়াম কোর্স (ফ্রি)**

**🔥 বিস্তারিত জানতে ভিডিওটি দেখুন 👉 https://t.me/+opeABW3v-F41NzY1**
        """
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏆 Leaderboard", callback_data="show_leaderboard"))
        bot.send_photo(user_id, "https://i.ibb.co.com/0xCjqkD/IMG-20260111-163125-686.jpg", caption=msg, reply_markup=markup, parse_mode='Markdown')

    elif message.text == "📚 Available Course":
        cursor.execute("SELECT id, name, fee FROM courses")
        courses = cursor.fetchall()

        if not courses:
            bot.send_message(user_id, "**📂 বর্তমানে কোনো কোর্স নেই।**", parse_mode='Markdown')
        else:
            header_msg = """
**💎 Premium Courses**

**📝 নিয়ম:**
**🔟 ১০ পয়েন্ট = ১টি কোর্স ক্লেইম করার যোগ্যতা**
**📌 আপনার পয়েন্ট >= 10 হলে “Claim Course” সক্রিয় হবে**
            """
            markup = types.InlineKeyboardMarkup()
            for c in courses:
                markup.add(types.InlineKeyboardButton(f"📘 {c[1]}", callback_data=f"buy_course_{c[0]}"))
            
            bot.send_photo(user_id, "https://i.ibb.co.com/XxP8q8Pd/IMG-20260110-213223-779.jpg", caption=header_msg + "\n**নিচের কোর্সগুলো কিনুন:**", reply_markup=markup, parse_mode='Markdown')

    elif message.text == "🔥 Trending Course":
        cursor.execute("SELECT photo_id, caption FROM trending ORDER BY id DESC LIMIT 1")
        post = cursor.fetchone()
        if post:
            caption_text = f"**{post[1]}**"
            try:
                if post[0] == 'none':
                    bot.send_message(user_id, caption_text, parse_mode='Markdown')
                else:
                    bot.send_photo(user_id, post[0], caption=caption_text, parse_mode='Markdown')
            except:
                bot.send_message(user_id, "**❌ পোস্ট লোড করতে সমস্যা হয়েছে।**", parse_mode='Markdown')
        else:
            bot.send_message(user_id, "**❌ বর্তমানে কোনো ট্রেন্ডিং কোর্স নেই।**", parse_mode='Markdown')

    elif message.text == "💰 Add Credit":
        msg = """
**💳 Buy credit**

**⏩ দ্রুত পয়েন্ট চান? কিনে নিন:**

**💎 10 Points = 300৳**
        """
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📩 Contact Admin", url="https://t.me/FCBAdminBD_Bot"))
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode='Markdown')

    elif message.text == "🎟 My Coupons":
        msg = "**🎟 কুপন ব্যবহার করে বোনাস পয়েন্ট নিন!**\n\n**নিচের বাটনে ক্লিক করে কুপন কোড সাবমিট করুন।**"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎁 Use Coupon", callback_data="use_coupon"))
        bot.send_photo(user_id, "https://i.ibb.co.com/2YZk6N8f/IMG-20260110-213248-444.jpg", caption=msg, reply_markup=markup, parse_mode='Markdown')

    elif message.text == "☎️ Support Admin":
        msg = "**☎️ Support Admin**\n\n**👉 @FCBAdminBD\_Bot**"
        bot.send_message(user_id, msg, parse_mode='Markdown')
    
    cursor.close()
    conn.close()

# ================= লিডারবোর্ড হ্যান্ডলার =================

@bot.callback_query_handler(func=lambda call: call.data == "show_leaderboard")
def show_leaderboard_handler(call):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, total_refer FROM users ORDER BY total_refer DESC LIMIT 10")
    top_users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not top_users:
        bot.answer_callback_query(call.id, "❌ কোনো ডাটা পাওয়া যায়নি!", show_alert=True)
        return

    msg = "**🏆 Top 10 Referrers 🏆**\n\n"
    for i, user in enumerate(top_users, 1):
        uid = user[0]
        count = user[1]
        try:
            chat_info = bot.get_chat(uid)
            name = chat_info.first_name
            if not name: name = "Unknown"
            name = name.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
        except:
            name = "User"
        msg += f"**{i}. {name}** — {count} Refers\n"
    
    bot.send_message(call.message.chat.id, msg, parse_mode='Markdown')

# ================= কুপন রিডিম হ্যান্ডলার =================

@bot.callback_query_handler(func=lambda call: call.data == "use_coupon")
def ask_coupon_code(call):
    msg = bot.send_message(call.message.chat.id, "**📝 আপনার কুপন কোডটি লিখুন:**", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_coupon_redeem)

def process_coupon_redeem(message):
    user_id = message.chat.id
    code = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM coupons WHERE code=%s", (code,))
    coupon = cursor.fetchone()

    if not coupon:
        bot.send_message(user_id, "**❌ ভুল কুপন কোড!**", parse_mode='Markdown')
        cursor.close()
        conn.close()
        return

    if coupon[3] >= coupon[2]:
        bot.send_message(user_id, "**❌ এই কুপনটির মেয়াদ শেষ (লিমিট শেষ)।**", parse_mode='Markdown')
        cursor.close()
        conn.close()
        return

    cursor.execute("SELECT * FROM used_coupons WHERE user_id=%s AND code=%s", (user_id, code))
    already_used = cursor.fetchone()

    if already_used:
        bot.send_message(user_id, "**⚠️ আপনি ইতিমধ্যে এই কুপনটি ব্যবহার করেছেন।**", parse_mode='Markdown')
        cursor.close()
        conn.close()
        return

    amount = coupon[1]
    cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, user_id))
    cursor.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code=%s", (code,))
    cursor.execute("INSERT INTO used_coupons (user_id, code) VALUES (%s, %s)", (user_id, code))
    conn.commit()
    cursor.close()
    conn.close()

    bot.send_message(user_id, f"**🎉 অভিনন্দন! কুপন সফল হয়েছে। আপনি {amount} পয়েন্ট পেয়েছেন।**", parse_mode='Markdown')

# ================= কোর্স বাই হ্যান্ডলার =================

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_course_'))
def buy_course_handler(call):
    user_id = call.message.chat.id
    course_id = int(call.data.split('_')[2])

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM courses WHERE id=%s", (course_id,))
    course = cursor.fetchone() 

    user_bal = get_user(user_id)[1]
    required_points = course[4] # Usually 10

    if user_bal >= required_points:
        cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id=%s", (required_points, user_id))
        conn.commit()
        
        delivery_msg = f"**🎉 অভিনন্দন! আপনি {course[1]} কোর্সটি সফলভাবে কিনেছেন।**\n\n**📝 বিবরণ:**\n{course[3]}"
        
        if course[2] and course[2] != 'none':
            bot.send_photo(user_id, course[2], caption=delivery_msg, parse_mode='Markdown')
        else:
            bot.send_message(user_id, delivery_msg, parse_mode='Markdown')
    else:
        bot_username = bot.get_me().username
        link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        no_bal_msg = f"**❌ আপনার ACC এ পর্যাপ্ত পয়েন্ট নেই। দয়া করে পয়েন্ট অ্যাড করুন অথবা রেফার করুন।**\n\n**🔗 আপনার রেফারেল লিংক:**\n`{link}`"
        
        bot.send_message(user_id, no_bal_msg, parse_mode='Markdown')
        bot.answer_callback_query(call.id, "❌ পর্যাপ্ত পয়েন্ট নেই!", show_alert=False)
    
    cursor.close()
    conn.close()

# ================= অ্যাডমিন হ্যান্ডলার =================

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔥 Trending Course", callback_data='adm_trending'),
        types.InlineKeyboardButton("📚 Course Manage", callback_data='adm_course'),
        types.InlineKeyboardButton("📢 Channel Manage", callback_data='adm_channel'),
        types.InlineKeyboardButton("🎟 Ad Coupon", callback_data='adm_coupon'),
        types.InlineKeyboardButton("💎 Refer Balance", callback_data='adm_ref_bal'),
        types.InlineKeyboardButton("📄 User UID File", callback_data='adm_export'),
        types.InlineKeyboardButton("📊 Total Users", callback_data='adm_stats'),
        types.InlineKeyboardButton("📩 Send SMS", callback_data='adm_sms')
    )
    bot.send_message(message.chat.id, "**🔧 Admin Panel**", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith(('adm_', 'ch_', 'sms_', 'del_course_', 'cpn_', 'trend_')))
def admin_actions(call):
    if call.message.chat.id != ADMIN_ID: return
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # Trending Course Management
    if call.data == 'adm_trending':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Ad Post", callback_data='trend_add'),
                   types.InlineKeyboardButton("❌ Remove Post", callback_data='trend_rem'))
        bot.edit_message_text("**🔥 Trending Course Management:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == 'trend_add':
        msg = bot.send_message(ADMIN_ID, "**পোস্টের ফটো দিন:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_trend_photo)

    elif call.data == 'trend_rem':
        cursor.execute("DELETE FROM trending")
        conn.commit()
        bot.answer_callback_query(call.id, "পোস্ট রিমুভ করা হয়েছে!", show_alert=True)
        bot.send_message(ADMIN_ID, "**✅ ট্রেন্ডিং পোস্ট রিমুভ করা হয়েছে।**", parse_mode='Markdown')

    # Coupon Management
    elif call.data == 'adm_coupon':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add Coupon", callback_data='cpn_add'),
                   types.InlineKeyboardButton("❌ Remove Coupon", callback_data='cpn_rem'))
        bot.edit_message_text("**🎟 Coupon Management:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == 'cpn_add':
        msg = bot.send_message(ADMIN_ID, "**নতুন কুপন কোড (Code Name) লিখুন:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_coupon_name)

    elif call.data == 'cpn_rem':
        cursor.execute("SELECT code, amount, usage_limit FROM coupons")
        coupons = cursor.fetchall()
        markup = types.InlineKeyboardMarkup()
        for cp in coupons:
            markup.add(types.InlineKeyboardButton(f"🗑 {cp[0]} ({cp[1]}Pts - {cp[2]} Limit)", callback_data=f"cpn_del_{cp[0]}"))
        bot.edit_message_text("**ডিলিট করতে কুপন সিলেক্ট করুন:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith('cpn_del_'):
        code = call.data.replace('cpn_del_', '')
        cursor.execute("DELETE FROM coupons WHERE code=%s", (code,))
        conn.commit()
        bot.answer_callback_query(call.id, "কুপন ডিলিট করা হয়েছে!")
        admin_panel(call.message)

    # Course Management
    elif call.data == 'adm_course':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add Course", callback_data='adm_add_course'),
                   types.InlineKeyboardButton("❌ Remove Course", callback_data='adm_rem_course'))
        bot.edit_message_text("**কোর্স ম্যানেজমেন্ট:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == 'adm_add_course':
        msg = bot.send_message(ADMIN_ID, "**কোর্সের নাম দিন:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_course_name)

    elif call.data == 'adm_rem_course':
        cursor.execute("SELECT id, name FROM courses")
        courses = cursor.fetchall()
        markup = types.InlineKeyboardMarkup()
        for c in courses:
            markup.add(types.InlineKeyboardButton(f"🗑 {c[1]}", callback_data=f"del_course_{c[0]}"))
        bot.edit_message_text("**কোর্স রিমুভ করতে সিলেক্ট করুন:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith('del_course_'):
        cid = call.data.split('_')[2]
        cursor.execute("DELETE FROM courses WHERE id=%s", (cid,))
        conn.commit()
        bot.answer_callback_query(call.id, "কোর্স ডিলিট করা হয়েছে!")
        admin_panel(call.message)

    # Channel & Others
    elif call.data == 'adm_channel':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add Channel", callback_data='ch_add'),
                   types.InlineKeyboardButton("❌ Remove Channel", callback_data='ch_rem'))
        bot.edit_message_text("**চ্যানেল ম্যানেজমেন্ট:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == 'ch_add':
        msg = bot.send_message(ADMIN_ID, "**চ্যানেলের ইউজারনেম দিন (@ সহ):**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_add_channel)

    elif call.data == 'ch_rem':
        cursor.execute("SELECT username FROM channels")
        chs = cursor.fetchall()
        markup = types.InlineKeyboardMarkup()
        for c in chs:
            markup.add(types.InlineKeyboardButton(f"🗑 {c[0]}", callback_data=f"ch_del_act_{c[0]}"))
        bot.edit_message_text("**ডিলিট করতে সিলেক্ট করুন:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith('ch_del_act_'):
        ch_name = call.data.replace('ch_del_act_', '')
        cursor.execute("DELETE FROM channels WHERE username=%s", (ch_name,))
        conn.commit()
        bot.answer_callback_query(call.id, "চ্যানেল রিমুভ করা হয়েছে!")
        admin_panel(call.message)

    elif call.data == 'adm_stats':
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        bot.answer_callback_query(call.id, f"মোট ইউজার: {count}", show_alert=True)

    elif call.data == 'adm_export':
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        file_text = "\n".join([str(u[0]) for u in users])
        with open("users.txt", "w") as f: f.write(file_text)
        with open("users.txt", "rb") as f: bot.send_document(ADMIN_ID, f, caption="**সকল ইউজার আইডি**", parse_mode='Markdown')

    elif call.data == 'adm_ref_bal':
        msg = bot.send_message(ADMIN_ID, "**রেফার বোনাস কত সেট করতে চান? (সংখ্যা দিন):**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_set_ref_bonus)

    elif call.data == 'adm_sms':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 All Users", callback_data='sms_all'),
                   types.InlineKeyboardButton("👤 Target User", callback_data='sms_target'))
        bot.edit_message_text("**কাকে মেসেজ পাঠাবেন?**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == 'sms_all':
        msg = bot.send_message(ADMIN_ID, "**মেসেজ লিখুন (সকল ইউজারকে পাঠানো হবে):**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_broadcast_all)

    elif call.data == 'sms_target':
        msg = bot.send_message(ADMIN_ID, "**টার্গেট ইউজারের ID দিন:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_sms_target_id)
        
    cursor.close()
    conn.close()

# ---- অ্যাডমিন ইনপুট স্টেপস ----

def step_trend_photo(message):
    if message.content_type == 'photo':
        photo_id = message.photo[-1].file_id
        msg = bot.send_message(ADMIN_ID, "**পোস্টের ক্যাপশন লিখুন:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_trend_caption, photo_id)
    else:
        bot.send_message(ADMIN_ID, "**❌ দয়া করে একটি ফটো পাঠান।**", parse_mode='Markdown')

def step_trend_caption(message, photo_id):
    caption = message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trending")
    cursor.execute("INSERT INTO trending (photo_id, caption) VALUES (%s, %s)", (photo_id, caption))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(ADMIN_ID, "**✅ ট্রেন্ডিং পোস্ট সফলভাবে অ্যাড করা হয়েছে।**", parse_mode='Markdown')

def step_coupon_name(message):
    name = message.text.strip()
    msg = bot.send_message(ADMIN_ID, "**এই কুপনে কত পয়েন্ট বোনাস দিবেন? (সংখ্যা):**", parse_mode='Markdown')
    bot.register_next_step_handler(msg, step_coupon_amount, name)

def step_coupon_amount(message, name):
    try:
        amount = int(message.text)
        msg = bot.send_message(ADMIN_ID, "**কত জন ইউজার এই কুপনটি ব্যবহার করতে পারবে? (সংখ্যা):**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_coupon_limit, name, amount)
    except:
        bot.send_message(ADMIN_ID, "**❌ দয়া করে সংখ্যা দিন।**", parse_mode='Markdown')

def step_coupon_limit(message, name, amount):
    try:
        limit = int(message.text)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO coupons (code, amount, usage_limit) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET amount = EXCLUDED.amount, usage_limit = EXCLUDED.usage_limit", (name, amount, limit))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(ADMIN_ID, f"**✅ কুপন '{name}' সফলভাবে তৈরি হয়েছে।**\n**বোনাস: {amount} Pts**\n**লিমিট: {limit} জন**", parse_mode='Markdown')
    except:
        bot.send_message(ADMIN_ID, "**❌ দয়া করে সংখ্যা দিন।**", parse_mode='Markdown')

def step_course_name(message):
    c_name = message.text
    msg = bot.send_message(ADMIN_ID, "**কোর্সের লিংক দিন:**", parse_mode='Markdown')
    bot.register_next_step_handler(msg, step_course_link, c_name)

def step_course_link(message, c_name):
    c_link = message.text
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("No Photo")
    msg = bot.send_message(ADMIN_ID, "**কোর্সের ফটো দিন (অথবা 'No Photo' বাটনে ক্লিক করুন):**", reply_markup=markup, parse_mode='Markdown')
    bot.register_next_step_handler(msg, step_course_photo, c_name, c_link)

def step_course_photo(message, c_name, c_link):
    photo_id = 'none'
    if message.content_type == 'photo':
        photo_id = message.photo[-1].file_id

    markup = types.ReplyKeyboardRemove()
    msg = bot.send_message(ADMIN_ID, "**কোর্সের ডিটেইলস দিন:**", reply_markup=markup, parse_mode='Markdown')
    bot.register_next_step_handler(msg, step_course_details, c_name, c_link, photo_id)

def step_course_details(message, c_name, c_link, photo_id):
    details = message.text
    full_description = f"**🔗 Link:** {c_link}\n\n**📝 Details:**\n{details}"
    fee = 10
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO courses (name, photo_id, description, fee) VALUES (%s, %s, %s, %s)", (c_name, photo_id, full_description, fee))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(ADMIN_ID, "**✅ কোর্স সফলভাবে যোগ করা হয়েছে! (Fee: 10 Points)**", parse_mode='Markdown')

def step_add_channel(message):
    ch = message.text
    if not ch.startswith('@'):
        bot.send_message(ADMIN_ID, "**❌ @ সহ ইউজারনেম দিন।**", parse_mode='Markdown')
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO channels (username) VALUES (%s) ON CONFLICT DO NOTHING", (ch,))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(ADMIN_ID, f"**✅ চ্যানেল {ch} যোগ করা হয়েছে।**", parse_mode='Markdown')

def step_set_ref_bonus(message):
    try:
        val = int(message.text)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ('refer_bonus', val))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(ADMIN_ID, f"**✅ রেফার বোনাস {val} সেট করা হয়েছে।**", parse_mode='Markdown')
    except:
        bot.send_message(ADMIN_ID, "**❌ সংখ্যা দিন।**", parse_mode='Markdown')

def step_broadcast_all(message):
    txt = f"**{message.text}**"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    count = 0
    bot.send_message(ADMIN_ID, "**📨 ব্রডকাস্ট শুরু হচ্ছে...**", parse_mode='Markdown')
    for u in users:
        try:
            bot.send_message(u[0], txt, parse_mode='Markdown')
            count += 1
            time.sleep(0.05)
        except: pass
    bot.send_message(ADMIN_ID, f"**✅ মোট {count} জন ইউজারকে মেসেজ পাঠানো হয়েছে।**", parse_mode='Markdown')

def step_sms_target_id(message):
    try:
        uid = int(message.text)
        msg = bot.send_message(ADMIN_ID, "**মেসেজটি লিখুন:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, step_sms_target_send, uid)
    except:
        bot.send_message(ADMIN_ID, "**❌ ভুল ID!**", parse_mode='Markdown')

def step_sms_target_send(message, uid):
    try:
        bot.send_message(uid, f"**{message.text}**", parse_mode='Markdown')
        bot.send_message(ADMIN_ID, "**✅ মেসেজ পাঠানো হয়েছে।**", parse_mode='Markdown')
    except Exception as e:
        bot.send_message(ADMIN_ID, f"**❌ মেসেজ পাঠানো যায়নি।**", parse_mode='Markdown')

print("🤖 Bot is running...")
bot.infinity_polling()
