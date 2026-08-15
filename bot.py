import logging
import sqlite3
import time
import requests
import qrcode
import os
from flask import Flask
import threading
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ================= CONFIGURATION =================
BOT_TOKEN = "8967912234:AAEX20bHiStrGt2RqHWkpUwiiGt1A7A2Uek"
ADMIN_ID = 7088682169

config = {
    "bot_name": "GROWTH NINJA SMM BOT 🚀",
    "upi_id": "example@upi",
    "proof_channel": "https://t.me/your_proof_channel",
    "support_username": "your_tg_handle",
    "smm_url": "https://followeradda.com/api/v2",
    "smm_key": "YOUR_SMM_API_KEY",
    "default_markup": 70.0
}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Global cache for services
CACHE_SERVICES = []
CACHE_TIME = 0

def get_all_services():
    global CACHE_SERVICES, CACHE_TIME
    if CACHE_SERVICES and (time.time() - CACHE_TIME < 300):
        return CACHE_SERVICES
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = requests.post(config['smm_url'], data={'key': config['smm_key'], 'action': 'services'}, headers=headers, timeout=10).json()
        if isinstance(req, list):
            CACHE_SERVICES = req
            CACHE_TIME = time.time()
            return req
    except Exception as e:
        logging.error(f"Error fetching services: {e}")
    return CACHE_SERVICES

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect("smm_bot.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        balance REAL DEFAULT 0.0,
                        spent REAL DEFAULT 0.0,
                        is_reseller INTEGER DEFAULT 0,
                        custom_markup REAL DEFAULT NULL,
                        referred_by INTEGER DEFAULT NULL,
                        referral_count INTEGER DEFAULT 0
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS pending_payments (
                        user_id INTEGER PRIMARY KEY,
                        amount REAL,
                        timestamp REAL
                    )''')
    conn.commit()
    conn.close()

init_db()

def db_get_user(user_id):
    conn = sqlite3.connect("smm_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, spent, is_reseller, referral_count, custom_markup FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        res = (0.0, 0.0, 0, 0, None)
    conn.close()
    return res

def get_user_markup(user_id):
    bal, spent, is_reseller, refs, custom_m = db_get_user(user_id)
    if custom_m is not None:
        return float(custom_m)
    if is_reseller or spent >= 350:
        return config['default_markup'] / 2.0
    return config['default_markup']

def get_main_reply_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🛒 New Order"), KeyboardButton("💳 Deposit Cash")],
        [KeyboardButton("💎 Reseller Info"), KeyboardButton("👥 Refer & Earn")],
        [KeyboardButton("📢 Proof Channel"), KeyboardButton("🎧 24x7 Support")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args and len(context.args) > 0:
        try:
            ref_id = int(context.args[0])
            if ref_id != user_id:
                conn = sqlite3.connect("smm_bot.db")
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, ref_id))
                    cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (ref_id,))
                    conn.commit()
                conn.close()
        except ValueError:
            pass

    bal, spent, is_reseller, refs, custom_m = db_get_user(user_id)
    account_type = "🔥 Reseller User" if is_reseller else "👤 Standard User"

    text = (
        f"🎉 **Welcome to {config['bot_name']}!**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"🎖 **Status:** {account_type}\n"
        f"💰 **Balance:** ₹{bal:.2f}\n"
        f"📊 **Total Spent:** ₹{spent:.2f}\n"
        f"👥 **Referrals:** {refs}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"✨ Bottom Keyboard Menu se koi option select karein:"
    )

    reply_markup = get_main_reply_keyboard(user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get('state')

    if user_id == ADMIN_ID and state and state.startswith("adm_"):
        if state == "adm_url":
            config['smm_url'] = text
            await update.message.reply_text(f"✅ **SMM API URL Updated:** `{text}`", parse_mode="Markdown")
        elif state == "adm_key":
            config['smm_key'] = text
            await update.message.reply_text("✅ **SMM API Key Updated Successfully!**")
        elif state == "adm_markup":
            try:
                config['default_markup'] = float(text)
                await update.message.reply_text(f"✅ **Global Markup set to:** `{config['default_markup']}%`", parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("❌ Enter a valid number.")
        elif state == "adm_usr_markup":
            try:
                target_u, m_val = text.split()
                target_u, m_val = int(target_u), float(m_val)
                conn = sqlite3.connect("smm_bot.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET custom_markup = ? WHERE user_id = ?", (m_val, target_u))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"✅ User `{target_u}` Custom Markup set to **{m_val}%**", parse_mode="Markdown")
            except Exception:
                await update.message.reply_text("❌ Format wrong. Send like: `123456789 50`")
        elif state == "adm_upi":
            config['upi_id'] = text
            await update.message.reply_text(f"✅ **UPI ID Updated:** `{text}`", parse_mode="Markdown")
        elif state == "adm_proof":
            config['proof_channel'] = text
            await update.message.reply_text(f"✅ **Proof Link Updated:** `{text}`", parse_mode="Markdown")
        elif state == "adm_support":
            config['support_username'] = text.replace("@", "")
            await update.message.reply_text(f"✅ **Support Username Updated:** `@{config['support_username']}`", parse_mode="Markdown")

        context.user_data.clear()
        return

    if state == 'awaiting_custom_amt':
        try:
            amt = float(text)
            if amt < 1:
                await update.message.reply_text("❌ Minimum ₹1 required.")
                return
            context.user_data.clear()
            await trigger_qr_code(update, user_id, amt)
            return
        except ValueError:
            await update.message.reply_text("❌ Valid number enter karein (e.g. 100).")
            return

    # ===== ORDER FLOW: STEP 3 (LINK INPUT) =====
    if state == 'awaiting_order_link':
        context.user_data['order_link'] = text
        context.user_data['state'] = 'awaiting_order_qty'
        service = context.user_data.get('selected_service')
        min_q = int(service.get('min', 1))
        max_q = int(service.get('max', 100000))
        await update.message.reply_text(
            f"🔗 **Link Received:** `{text}`\n\n"
            f"✍️ Ab **Quantity** enter karein:\n"
            f"📌 Min: `{min_q}` | Max: `{max_q}`",
            parse_mode="Markdown"
        )
        return

    # ===== ORDER FLOW: STEP 4 (QUANTITY INPUT & CONFIRMATION) =====
    if state == 'awaiting_order_qty':
        try:
            qty = int(text)
            service = context.user_data.get('selected_service')
            min_q = int(service.get('min', 1))
            max_q = int(service.get('max', 100000))

            if qty < min_q or qty > max_q:
                await update.message.reply_text(f"❌ Quantity `{min_q}` se `{max_q}` ke beech honi chahiye.")
                return

            context.user_data['order_qty'] = qty
            context.user_data['state'] = None

            # Calculate Price
            rate_per_1000 = float(service.get('rate', 0))
            markup = get_user_markup(user_id)
            final_rate_per_1000 = rate_per_1000 * (1 + markup / 100.0)
            total_cost = round((final_rate_per_1000 / 1000.0) * qty, 2)
            context.user_data['total_cost'] = total_cost

            bal, _, _, _, _ = db_get_user(user_id)

            confirm_msg = (
                f"📋 **ORDER CONFIRMATION**\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 **Service:** {service.get('name')}\n"
                f"🔗 **Link:** `{context.user_data.get('order_link')}`\n"
                f"📊 **Quantity:** `{qty}`\n"
                f"💰 **Total Price:** ₹{total_cost:.2f}\n"
                f"💳 **Your Balance:** ₹{bal:.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
            )

            if bal < total_cost:
                confirm_msg += "\n❌ **Insufficient Balance!** Please deposit funds first."
                keyboard = [[InlineKeyboardButton("💳 Deposit Cash", callback_data="pay_custom")]]
            else:
                confirm_msg += "\nConfirm order karne ke liye neeche button dabaayein:"
                keyboard = [
                    [InlineKeyboardButton("✅ Confirm & Place Order", callback_data="confirm_place_order")],
                    [InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_order")]
                ]

            await update.message.reply_text(confirm_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        except ValueError:
            await update.message.reply_text("❌ Valid quantity number enter karein.")
            return

    if text == "🛒 New Order":
        await fetch_and_show_categories(update, context)

    elif text == "💳 Deposit Cash":
        keyboard = [
            [InlineKeyboardButton("₹10", callback_data="pay_10"), InlineKeyboardButton("₹30", callback_data="pay_30"), InlineKeyboardButton("₹50", callback_data="pay_50")],
            [InlineKeyboardButton("✏️ Custom Amount", callback_data="pay_custom")]
        ]
        await update.message.reply_text("💳 **Select Amount to Add:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif text == "💎 Reseller Info":
        reseller_msg = (
            "💎 **Reseller VIP Benefits**\n\n"
            "✨ Automatically become a Reseller when you spend **₹350** total!\n"
            "📉 Get **50% OFF** on all SMM Services.\n"
            "⚡ Fast Priority Speed for Orders."
        )
        await update.message.reply_text(reseller_msg, parse_mode="Markdown")

    elif text == "👥 Refer & Earn":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        ref_msg = (
            "👥 **Refer & Earn Program**\n\n"
            f"Share your link with friends:\n`{ref_link}`\n\n"
            "🎁 Get bonus benefits on every active referral!"
        )
        await update.message.reply_text(ref_msg, parse_mode="Markdown")

    elif text == "📢 Proof Channel":
        keyboard = [[InlineKeyboardButton("📢 Join Proof Channel", url=config['proof_channel'])]]
        await update.message.reply_text("Click below to check active proofs:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "🎧 24x7 Support":
        keyboard = [[InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{config['support_username']}")] ]
        await update.message.reply_text("Need help? Click below:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "⚙️ Admin Panel" and user_id == ADMIN_ID:
        await show_admin_panel(update, context)

async def show_admin_panel(update, context):
    msg = (
        "⚙️ **Admin Control Panel**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 **Bot Name:** `{config['bot_name']}`\n"
        f"💳 **UPI ID:** `{config['upi_id']}`\n"
        f"🔗 **API URL:** `{config['smm_url']}`\n"
        f"🎧 **Support:** `@{config['support_username']}`\n"
        f"📢 **Proof Link:** `{config['proof_channel']}`\n"
        f"📈 **Global Markup:** `{config['default_markup']}%`\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Services Cache", callback_data="adm_import")],
        [InlineKeyboardButton("⚡ Test API Connection", callback_data="adm_test_api")],
        [InlineKeyboardButton("🔗 Set API URL", callback_data="adm_set_url"), InlineKeyboardButton("🔑 Set API Key", callback_data="adm_set_key")],
        [InlineKeyboardButton("📈 Global Markup %", callback_data="adm_set_markup"), InlineKeyboardButton("👤 User Specific Markup", callback_data="adm_user_markup")],
        [InlineKeyboardButton("💳 Change UPI", callback_data="adm_change_upi"), InlineKeyboardButton("📢 Change Proof", callback_data="adm_change_proof")],
        [InlineKeyboardButton("🎧 Change Support TG", callback_data="adm_change_support"), InlineKeyboardButton("📊 Bot Statistics", callback_data="adm_stats")]
    ]
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== ORDER FLOW: STEP 1 (SHOW CATEGORIES) =====
async def fetch_and_show_categories(update_or_query, context):
    services = get_all_services()
    if services:
        categories = list(dict.fromkeys([s['category'] for s in services if 'category' in s]))
        context.user_data['all_categories'] = categories
        keyboard = []
        for idx, cat in enumerate(categories[:25]): # Limit to top 25 categories
            keyboard.append([InlineKeyboardButton(cat[:35], callback_data=f"cat_{idx}")])
        msg = "📂 **Select Service Category:**"
    else:
        msg = "❌ SMM Services load nahi ho payi. Please Admin Panel me API details check karein."
        keyboard = []

    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None, parse_mode="Markdown")

async def handle_inline_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # ===== CATEGORY SELECTED -> SHOW SERVICES =====
    if data.startswith("cat_"):
        cat_idx = int(data.split("_")[1])
        categories = context.user_data.get('all_categories', [])
        if not categories or cat_idx >= len(categories):
            services = get_all_services()
            categories = list(dict.fromkeys([s['category'] for s in services if 'category' in s]))
            context.user_data['all_categories'] = categories

        selected_cat = categories[cat_idx]
        context.user_data['selected_category'] = selected_cat

        all_services = get_all_services()
        cat_services = [s for s in all_services if s.get('category') == selected_cat]
        context.user_data['cat_services'] = cat_services

        markup = get_user_markup(user_id)

        keyboard = []
        for idx, srv in enumerate(cat_services[:20]): # Limit items per category
            rate = float(srv.get('rate', 0)) * (1 + markup / 100.0)
            btn_text = f"{srv.get('name')[:30]} - ₹{rate:.2f}/k"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"srv_{idx}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="back_to_cats")])

        await query.edit_message_text(
            f"📁 **Category:** `{selected_cat}`\n\n👇 **Select Service:**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ===== SERVICE SELECTED -> ASK FOR LINK =====
    elif data.startswith("srv_"):
        srv_idx = int(data.split("_")[1])
        cat_services = context.user_data.get('cat_services', [])
        if not cat_services or srv_idx >= len(cat_services):
            await query.edit_message_text("❌ Service detail expire ho gayi. Phir se try karein.")
            return

        selected_service = cat_services[srv_idx]
        context.user_data['selected_service'] = selected_service
        context.user_data['state'] = 'awaiting_order_link'

        rate = float(selected_service.get('rate', 0)) * (1 + get_user_markup(user_id) / 100.0)

        msg = (
            f"🛒 **Service Selected:**\n"
            f"📌 **{selected_service.get('name')}**\n\n"
            f"💵 **Price:** ₹{rate:.2f} per 1000\n"
            f"📌 **Min:** {selected_service.get('min')} | **Max:** {selected_service.get('max')}\n\n"
            f"✍️ **Ab Target Link / Username chat me send karein:**"
        )
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif data == "back_to_cats":
        await fetch_and_show_categories(query, context)

    # ===== CONFIRM & PLACE ORDER =====
    elif data == "confirm_place_order":
        service = context.user_data.get('selected_service')
        link = context.user_data.get('order_link')
        qty = context.user_data.get('order_qty')
        cost = context.user_data.get('total_cost')

        bal, spent, is_reseller, refs, custom_m = db_get_user(user_id)

        if bal < cost:
            await query.edit_message_text("❌ Insufficient Balance. Order Cancelled.")
            return

        # Place Order via API
        try:
            payload = {
                'key': config['smm_key'],
                'action': 'add',
                'service': service['service'],
                'link': link,
                'quantity': qty
            }
            res = requests.post(config['smm_url'], data=payload, timeout=15).json()

            if 'order' in res:
                order_id = res['order']
                # Deduct balance
                conn = sqlite3.connect("smm_bot.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET balance = balance - ?, spent = spent + ? WHERE user_id = ?", (cost, cost, user_id))
                conn.commit()
                conn.close()

                success_msg = (
                    f"🎉 **ORDER PLACED SUCCESSFULLY!**\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 **Order ID:** `{order_id}`\n"
                    f"🔹 **Service:** {service.get('name')}\n"
                    f"🔗 **Link:** `{link}`\n"
                    f"📊 **Quantity:** `{qty}`\n"
                    f"💰 **Amount Deducted:** ₹{cost:.2f}\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ Speed: Instant / In Progress"
                )
                await query.edit_message_text(success_msg, parse_mode="Markdown")
                context.user_data.clear()
            else:
                err = res.get('error', 'API Provider Error')
                await query.edit_message_text(f"❌ **Order Failed:** `{err}`\nBalance nahi kata hai.", parse_mode="Markdown")

        except Exception as e:
            await query.edit_message_text(f"❌ **Error placing order:** {str(e)}")

    elif data == "cancel_order":
        context.user_data.clear()
        await query.edit_message_text("❌ Order Cancelled.")

    elif data.startswith("pay_"):
        amt_str = data.split("_")[1]
        if amt_str == "custom":
            await query.edit_message_text("✍️ Send custom amount in chat (e.g. `100`):", parse_mode="Markdown")
            context.user_data['state'] = 'awaiting_custom_amt'
            return
        await trigger_qr_code(query, user_id, float(amt_str))

    elif data == "adm_import":
        global CACHE_TIME
        CACHE_TIME = 0
        get_all_services()
        await query.edit_message_text("✅ SMM Services refreshed successfully from SMM Panel!")

    elif data == "adm_test_api":
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.post(config['smm_url'], data={'key': config['smm_key'], 'action': 'balance'}, headers=headers, timeout=10).json()
            if 'balance' in res:
                msg = f"✅ **API Connected!**\n\n💰 **Balance:** {res.get('currency', '')} {res.get('balance', '')}"
            else:
                msg = f"❌ **API Error:** {res.get('error', 'Invalid Key/URL')}"
        except Exception as e:
            msg = f"❌ **Connection Failed:** {str(e)}"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_admin")]]))

    elif data == "btn_admin":
        await show_admin_panel(update, context)

    elif data == "adm_set_url":
        await query.edit_message_text("✍️ Send new **SMM Provider API URL**:")
        context.user_data['state'] = 'adm_url'
    elif data == "adm_set_key":
        await query.edit_message_text("✍️ Send new **SMM Provider API Key**:")
        context.user_data['state'] = 'adm_key'
    elif data == "adm_set_markup":
        await query.edit_message_text("✍️ Send new **Global Default Markup %**:")
        context.user_data['state'] = 'adm_markup'
    elif data == "adm_user_markup":
        await query.edit_message_text("✍️ Send `USER_ID MARKUP_PERCENTAGE` (e.g. `12345 50`):")
        context.user_data['state'] = 'adm_usr_markup'
    elif data == "adm_change_upi":
        await query.edit_message_text("✍️ Send new **UPI ID**:")
        context.user_data['state'] = 'adm_upi'
    elif data == "adm_change_proof":
        await query.edit_message_text("✍️ Send new **Proof Channel Link**:")
        context.user_data['state'] = 'adm_proof'
    elif data == "adm_change_support":
        await query.edit_message_text("✍️ Send new **Support Telegram Username** (without @):")
        context.user_data['state'] = 'adm_support'

    elif data == "adm_stats":
        conn = sqlite3.connect("smm_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(spent) FROM users")
        u_cnt, s_total = cursor.fetchone()
        conn.close()
        msg = f"📊 **Bot Statistics**\n\n👥 Total Users: {u_cnt}\n💰 Total Spent: ₹{s_total or 0.0:.2f}"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_admin")]]))

    elif data == "paid_check":
        await query.message.reply_text("📸 **Upload Payment Screenshot in chat now:**\n(Make sure UTR / Txn ID is clearly visible)")

    elif data == "not_paid":
        await query.edit_message_text("❌ Payment process cancelled.")

async def trigger_qr_code(query_or_msg, user_id, amount):
    conn = sqlite3.connect("smm_bot.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO pending_payments (user_id, amount, timestamp) VALUES (?, ?, ?)", (user_id, amount, time.time()))
    conn.commit()
    conn.close()

    upi_string = f"upi://pay?pa={config['upi_id']}&pn={config['bot_name']}&am={amount}&cu=INR"
    qr_img = qrcode.make(upi_string)
    bio = BytesIO()
    qr_img.save(bio, 'PNG')
    bio.seek(0)

    caption = (
        f"🏷️ **Payment QR - {config['bot_name']}**\n\n"
        f"💵 **Amount:** ₹{amount}\n"
        f"⏳ **Expiry:** `2 Minutes`\n\n"
        f"Pay via UPI and click **I Have Paid**."
    )

    keyboard = [
        [InlineKeyboardButton("✅ I Have Paid", callback_data="paid_check")],
        [InlineKeyboardButton("❌ Cancel", callback_data="not_paid")]
    ]

    if hasattr(query_or_msg, 'message') and query_or_msg.message:
        await query_or_msg.message.reply_photo(photo=bio, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query_or_msg.reply_photo(photo=bio, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("smm_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT amount, timestamp FROM pending_payments WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text("❌ Payment session expired or not found. Please click 'Deposit Cash' first.")
        conn.close()
        return

    amount, ts = row
    if time.time() - ts > 180:
        cursor.execute("DELETE FROM pending_payments WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("⏰ **Payment Session Expired!**\nPlease click Deposit Cash to create a new QR.")
        return

    file_id = update.message.photo[-1].file_id

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"appr_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reje_{user_id}")
        ]
    ]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=file_id,
        caption=f"📥 **New Deposit Request**\n\n👤 **User ID:** `{user_id}`\n💰 **Amount:** ₹{amount}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    await update.message.reply_text("⏳ **Screenshot submitted to Admin for verification!**")

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action, target_user = data[0], int(data[1])

    if action == "appr":
        amount = float(data[2])
        conn = sqlite3.connect("smm_bot.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ?, spent = spent + ? WHERE user_id = ?", (amount, amount, target_user))
        cursor.execute("DELETE FROM pending_payments WHERE user_id = ?", (target_user,))
        conn.commit()
        conn.close()

        await query.edit_message_caption(caption=f"✅ Approved ₹{amount} for User `{target_user}`")
        await context.bot.send_message(
            chat_id=target_user,
            text=f"🎉 **Payment Approved!**\n\n₹{amount} has been added to your balance.",
            parse_mode="Markdown"
        )

    elif action == "reje":
        await query.edit_message_caption(caption=f"❌ Rejected deposit for User `{target_user}`")
        await context.bot.send_message(
            chat_id=target_user,
            text="❌ **Payment Verification Failed!** Your payment was rejected."
        )

# Render dummy web server
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ================= MAIN RUNNER =================
if __name__ == "__main__":
    threading.Thread(target=run_web).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_inline_buttons, pattern="^(cat_|srv_|back_to_cats|confirm_place_order|cancel_order|pay_|adm_|paid_check|not_paid|btn_admin)"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(appr_|reje_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))
    app.add_handler(MessageHandler(filters.PHOTO, process_photo))

    print("🚀 GROWTH NINJA SMM BOT Engine Started!")
    app.run_polling()
