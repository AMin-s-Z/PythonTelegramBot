import re
from enum import Enum
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import database as db
import config

# تعریف وضعیت‌های مکالمه
class State(Enum):
    SELECTING_PRODUCT, CONFIRMING_PURCHASE, AWAITING_RECEIPT, AWAITING_DISCOUNT_CODE = range(4)
    AWAITING_REJECTION_REASON = 11
    AWAITING_LINK_PRODUCT_CHOICE, AWAITING_LINKS_TO_ADD = range(20, 22)
    AWAITING_SUPPORT_MESSAGE = 30

# ==================================
# === بخش صفحه اصلی و کاربر ===
# ==================================
async def show_home_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """صفحه اصلی (داشبورد) را به کاربر نمایش می‌دهد."""
    user = update.effective_user
    db.add_or_update_user(user.id, user.first_name, user.username)
    text = f"سلام {user.first_name} عزیز! 👋\nبه ربات فروش آلبالو خوش آمدید."
    keyboard = [
        [InlineKeyboardButton("🛍 خرید سرویس جدید", callback_data="go_to_purchase")],
        [InlineKeyboardButton("📁 خریدهای من", callback_data="my_purchases")],
        [
            InlineKeyboardButton("📢 کانال تلگرام", url=config.TELEGRAM_CHANNEL_URL),
            InlineKeyboardButton("📞 پشتیبانی", callback_data="support")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start را مدیریت کرده و به صفحه اصلی می‌برد."""
    await show_home_menu(update, context)

async def my_purchases_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لینک‌های خریداری شده کاربر را نمایش می‌دهد."""
    query = update.callback_query
    await query.answer()
    user_links = db.get_user_links(update.effective_user.id)
    if not user_links:
        text = "شما تاکنون هیچ خرید فعالی نداشته‌اید."
    else:
        text = "📄 **لیست سرویس‌های فعال شما:**\n\n"
        for _, product_name, link, purchase_date in enumerate(user_links, 1):
            text += f"🔹 **{product_name}** (خرید: {purchase_date})\n`{link}`\n\n"
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="back_to_home")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown', disable_web_page_preview=True)

# ==================================
# === فرآیند خرید کاربر ===
# ==================================
async def start_purchase_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    products = db.get_products()
    if not products:
        await query.edit_message_text("در حال حاضر محصولی برای فروش وجود ندارد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_home")]]))
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(f"{name} - {price:,} تومان", callback_data=f"product_{product_id}")] for product_id, name, price in products]
    keyboard.append([InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="cancel_purchase")])
    await query.edit_message_text("لطفاً سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return State.SELECTING_PRODUCT

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split('_')[1])
    product = db.get_product_details(product_id)
    context.user_data.pop('final_price', None)
    context.user_data.pop('discount_code', None)
    context.user_data['selected_product_id'] = product_id
    context.user_data['selected_product'] = product
    name, price, description = product
    text = f"شما «{name}» را انتخاب کردید.\n💰 قیمت: {price:,} تومان\n\nبرای ادامه دکمه‌ای را انتخاب کنید."
    keyboard = [
        [InlineKeyboardButton("✅ ادامه و پرداخت", callback_data='confirm_payment_info')],
        [InlineKeyboardButton("🎁 اعمال کد تخفیف", callback_data='apply_discount_code')],
        [InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="cancel_purchase")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return State.CONFIRMING_PURCHASE

async def prompt_for_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = "لطفاً کد تخفیف خود را ارسال کنید:"
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت", callback_data=f"product_{context.user_data['selected_product_id']}")] ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return State.AWAITING_DISCOUNT_CODE

async def process_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code_text = update.message.text
    product_name, price, _ = context.user_data['selected_product']

    if context.user_data.get('discount_code'):
        await update.message.reply_text("شما قبلاً یک کد تخفیف اعمال کرده‌اید.")
        # Re-show the confirmation message
        final_price = context.user_data.get('final_price', price)
        text = (f"✅ کد تخفیف قبلاً اعمال شده.\n\n"
                f"قیمت اصلی: ~~{price:,} تومان~~\n"
                f"**قیمت نهایی: {final_price:,} تومان**\n\n"
                "آیا خرید را با این قیمت تایید می‌کنید؟")
        keyboard = [[InlineKeyboardButton("✅ بله، ادامه و پرداخت", callback_data='confirm_payment_info')],
                    [InlineKeyboardButton("⬅️ بازگشت", callback_data=f"product_{context.user_data['selected_product_id']}")]
                    ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return State.CONFIRMING_PURCHASE

    discount = db.validate_and_apply_code(code_text)

    if discount:
        new_price = 0
        if discount['type'] == 'percent':
            new_price = price - ((price * discount['value']) // 100)
        elif discount['type'] == 'fixed':
            new_price = price - discount['value']

        if new_price < 0: new_price = 0
        context.user_data['final_price'] = new_price
        context.user_data['discount_code'] = code_text.upper()

        text = (f"✅ کد تخفیف با موفقیت اعمال شد!\n\n"
                f"قیمت اصلی: ~~{price:,} تومان~~\n"
                f"**قیمت نهایی: {new_price:,} تومان**\n\n"
                "آیا خرید را با این قیمت تایید می‌کنید؟")
        keyboard = [
            [InlineKeyboardButton("✅ بله، ادامه و پرداخت", callback_data='confirm_payment_info')],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data=f"product_{context.user_data['selected_product_id']}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return State.CONFIRMING_PURCHASE
    else:
        await update.message.reply_text("❌ کد تخفیف نامعتبر یا منقضی شده است. لطفاً دوباره تلاش کنید.")
        return State.AWAITING_DISCOUNT_CODE

async def show_payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    product_id = context.user_data['selected_product_id']
    product_name, original_price, _ = context.user_data['selected_product']
    final_price = context.user_data.get('final_price', original_price)

    transaction_id = db.create_pending_transaction(user_id, product_id, product_name, final_price)
    context.user_data['transaction_id'] = transaction_id

    text = (f"✅ **مرحله پرداخت برای «{product_name}»**\n\n"
            f" شناسه خرید شما: `{transaction_id}`\n"
            f"**مبلغ قابل پرداخت: {final_price:,} تومان**\n\n"
            f"لطفاً مبلغ را به کارت زیر واریز کنید:\n"
            f"💳 `{config.BANK_CARD_INFO['card_number']}`\n"
            f"👤 به نام: **{config.BANK_CARD_INFO['card_holder']}**\n\n"
            f"‼️ پس از پرداخت، اسکرین‌شات رسید را ارسال کنید.")
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="cancel_purchase")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    return State.AWAITING_RECEIPT

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    transaction_id = context.user_data.get('transaction_id')
    if not transaction_id:
        await update.message.reply_text("خطا: شناسه خرید یافت نشد. لطفاً فرآیند را از ابتدا شروع کنید.")
        return ConversationHandler.END

    transaction_info = db.get_transaction(transaction_id)
    if not transaction_info:
        await update.message.reply_text("خطا: اطلاعات تراکنش یافت نشد.")
        return ConversationHandler.END

    _, product_name, price, _ = transaction_info
    caption = (f"🔔 **درخواست جدید**\n\n"
               f"👤 کاربر: {user.first_name} (@{user.username or 'ندارد'})\n"
               f"🆔 آیدی کاربر: `{user.id}`\n"
               f"🛍️ محصول: **{product_name}** ({price:,} تومان)\n"
               f" شناسه خرید: `{transaction_id}`\n\n"
               f" وضعیت: ⏳ در انتظار بررسی")
    keyboard = [[InlineKeyboardButton("✅ تایید خودکار", callback_data=f"admin_approve_{transaction_id}"),
                 InlineKeyboardButton("❌ رد کردن", callback_data=f"admin_reject_{transaction_id}")]]
    await context.bot.send_photo(chat_id=config.ADMIN_CHANNEL_ID, photo=update.message.photo[-1].file_id, caption=caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ رسید شما با موفقیت ثبت شد. لطفاً منتظر تایید مدیر بمانید...")
    await context.bot.send_message(chat_id=config.ADMIN_TELEGRAM_ID, text=f"یک درخواست جدید با شناسه {transaction_id} در کانال مدیریت ثبت شد.")
    return ConversationHandler.END

async def invalid_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً فقط **عکس رسید پرداخت** را ارسال کنید.")
    return State.AWAITING_RECEIPT

async def universal_cancel_and_go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.callback_query:
        await show_home_menu(update, context)
    else:
        await start(update, context)
    return ConversationHandler.END

# ==================================
# === سیستم تیکتینگ پشتیبانی ===
# ==================================
async def start_support_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("⬅️ لغو و بازگشت", callback_data="cancel_support")]]
    await query.edit_message_text(
        "لطفاً پیام خود را برای تیم پشتیبانی ارسال کنید. می‌توانید عکس هم بفرستید.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return State.AWAITING_SUPPORT_MESSAGE

async def forward_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    ticket_header = (f"📩 **تیکت پشتیبانی جدید**\n\n"
                     f"👤 **از طرف:** {user.first_name} (@{user.username or 'ندارد'})\n"
                     f"🆔 **آیدی کاربر:** `{user.id}`\n"
                     f"➖➖➖")
    await context.bot.send_message(chat_id=config.ADMIN_CHANNEL_ID, text=ticket_header, parse_mode='Markdown')
    forwarded_message = await update.message.forward(chat_id=config.ADMIN_CHANNEL_ID)
    db.create_support_ticket(user.id, forwarded_message.message_id)
    await update.message.reply_text("✅ پیام شما با موفقیت برای تیم پشتیبانی ارسال شد. لطفاً منتظر پاسخ بمانید.")
    return ConversationHandler.END

async def cancel_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await show_home_menu(update, context)
    return ConversationHandler.END

# ==================================
# === پنل ادمین ===
# ==================================
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    replied_message_id = update.message.reply_to_message.message_id
    target_user_id = db.get_user_from_ticket(replied_message_id)
    if target_user_id:
        admin_name = update.effective_user.first_name
        try:
            await context.bot.copy_message(chat_id=target_user_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            await context.bot.send_message(chat_id=target_user_id, text=f"💬 پاسخ جدید از طرف پشتیبانی ({admin_name}).")
            await update.message.reply_text("✅ پاسخ شما با موفقیت برای کاربر ارسال شد.")
        except Exception as e:
            await update.message.reply_text(f"❌ ارسال پیام به کاربر ناموفق بود: {e}")

async def admin_approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    transaction_id = query.data.split('_')[-1]

    transaction_info = db.get_transaction(transaction_id)
    if not transaction_info:
        await query.edit_message_caption(caption="خطا: این تراکنش قبلاً پردازش شده یا نامعتبر است.")
        return

    user_id, product_name, _, product_id = transaction_info
    link = db.fetch_and_assign_link(product_id, user_id, transaction_id)

    if link:
        db.update_transaction_status(transaction_id, 'approved')
        db.save_user_link(user_id, transaction_id, product_name, link)
        await context.bot.send_message(chat_id=user_id, text=f"✅ سرویس شما تایید و فعال شد!\n\nلینک اتصال:\n`{link}`", parse_mode='Markdown')
        final_caption = f"✅ **تایید و ارسال شد**\nمحصول: {product_name}\nشناسه: {transaction_id}\nتوسط: {update.effective_user.first_name}"
        await query.edit_message_caption(caption=final_caption, parse_mode='Markdown', reply_markup=None)
    else:
        await query.answer("⚠️ موجودی بانک لینک برای این محصول صفر است!", show_alert=True)
        await context.bot.send_message(chat_id=update.effective_user.id, text=f"خطا: موجودی لینک برای «{product_name}» تمام شده. لطفاً با /addlinks شارژ کنید.")

async def admin_reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    transaction_id = query.data.split('_')[-1]
    context.chat_data['channel_message_id'] = query.message.message_id
    context.chat_data['channel_id'] = query.message.chat_id

    transaction_info = db.get_transaction(transaction_id)
    if not transaction_info:
        await query.edit_message_caption(caption="خطا: این تراکنش قبلاً پردازش شده است.")
        return ConversationHandler.END

    context.chat_data['target_user_id'] = transaction_info[0]
    context.chat_data['transaction_id'] = transaction_id

    await query.edit_message_caption(caption=f"⏳ در حال رد کردن شناسه {transaction_id}...\nلطفاً دلیل را در چت خصوصی ربات ارسال کنید.", reply_markup=None)
    await context.bot.send_message(chat_id=update.effective_user.id, text=f"شما در حال رد کردن تراکنش `{transaction_id}` هستید. لطفاً دلیل را ارسال کنید یا با /cancel لغو کنید.")
    return State.AWAITING_REJECTION_REASON

async def receive_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text
    admin_user = update.effective_user
    target_user_id = context.chat_data.pop('target_user_id')
    transaction_id = context.chat_data.pop('transaction_id')
    channel_id = context.chat_data.pop('channel_id')
    message_id = context.chat_data.pop('channel_message_id')

    db.update_transaction_status(transaction_id, 'rejected')

    await context.bot.send_message(chat_id=target_user_id, text=f" متاسفانه پرداخت شما برای شناسه خرید `{transaction_id}` توسط مدیر رد شد.\n\n**دلیل:** {reason}", parse_mode='Markdown')

    _, product_name, _, _ = db.get_transaction(transaction_id)
    final_caption = f"❌ **رد شد**\nمحصول: {product_name}\nشناسه: {transaction_id}\nتوسط: {admin_user.first_name}\nدلیل: {reason}"
    await context.bot.edit_message_caption(chat_id=channel_id, message_id=message_id, caption=final_caption, parse_mode='Markdown')
    await update.message.reply_text(f"پیام رد پرداخت برای کاربر `{target_user_id}` ارسال و وضعیت در کانال آپدیت شد.")
    return ConversationHandler.END

async def add_links_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    products = db.get_products()
    keyboard = [[InlineKeyboardButton(p[1], callback_data=f"linkprod_{p[0]}")] for p in products]
    keyboard.append([InlineKeyboardButton("لغو", callback_data="cancel_addlink")])
    await update.message.reply_text("لطفاً انتخاب کنید لینک‌ها برای کدام محصول هستند:", reply_markup=InlineKeyboardMarkup(keyboard))
    return State.AWAITING_LINK_PRODUCT_CHOICE

async def add_links_product_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split('_')[1])
    context.chat_data['product_id_for_links'] = product_id
    await query.edit_message_text("عالی. حالا لیست لینک‌ها را ارسال کنید (هر لینک در یک خط جداگانه).")
    return State.AWAITING_LINKS_TO_ADD

async def add_links_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    product_id = context.chat_data.get('product_id_for_links')
    if not product_id:
        await update.message.reply_text("خطا! لطفاً فرآیند را از ابتدا با /addlinks شروع کنید.")
        return ConversationHandler.END

    links = [line.strip() for line in update.message.text.split('\n') if line.strip().startswith('http')]

    if not links:
        await update.message.reply_text("هیچ لینک معتبری یافت نشد. لطفاً دوباره تلاش کنید یا با /cancel لغو کنید.")
        return State.AWAITING_LINKS_TO_ADD

    added_count = db.add_links_to_bank(product_id, links)
    await update.message.reply_text(f"✅ {added_count} لینک جدید با موفقیت به بانک اضافه شد.")
    context.chat_data.clear()
    return ConversationHandler.END

async def cancel_addlink_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.chat_data.clear()
    if update.callback_query:
        await update.callback_query.edit_message_text("عملیات افزودن لینک لغو شد.")
    else:
        await update.message.reply_text("عملیات افزودن لینک لغو شد.")
    return ConversationHandler.END

async def link_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = db.get_link_bank_status()
    if not status:
        text = "بانک لینک خالی است."
    else:
        text = "📊 **وضعیت موجودی بانک لینک:**\n\n"
        for product_name, count in status:
            text += f"🔹 **{product_name}**: {count} لینک باقی‌مانده\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def backup_database_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != config.ADMIN_TELEGRAM_ID: return
    await update.message.reply_text("در حال آماده‌سازی فایل بکاپ...")
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        await context.bot.send_document(chat_id=config.ADMIN_CHANNEL_ID, document=open("store.db", "rb"), filename=f"backup_{timestamp}.db", caption=f"Backup\n{timestamp}")
        await update.message.reply_text("✅ بکاپ دیتابیس با موفقیت به کانال مدیریت ارسال شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطایی در هنگام ارسال فایل بکاپ رخ داد: {e}")

async def add_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.split()
        if len(parts) < 5: raise ValueError()
        code, type, value, uses = parts[1], parts[2], int(parts[3]), int(parts[4])
        expiry = parts[5] if len(parts) > 5 else None
        if type not in ['percent', 'fixed']:
            await update.message.reply_text("نوع تخفیف باید 'percent' یا 'fixed' باشد.")
            return
        if db.create_discount_code(code, type, value, uses, expiry):
            await update.message.reply_text(f"کد تخفیف {code.upper()} با موفقیت ساخته شد.")
        else:
            await update.message.reply_text("این کد از قبل وجود دارد.")
    except (IndexError, ValueError):
        await update.message.reply_text("فرمت دستور اشتباه است.\nمثال: `/addcode CODE1 percent 10 50 2025-12-31`", parse_mode='Markdown')

async def list_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codes = db.list_all_codes()
    if not codes:
        await update.message.reply_text("هیچ کد تخفیف فعالی وجود ندارد.")
        return
    text = "📜 **لیست کدهای تخفیف فعال:**\n\n"
    for code, type, value, used, total, expiry in codes:
        val_str = f"{value}%" if type == 'percent' else f"{value:,} تومان"
        expiry_str = f" | انقضا: {expiry}" if expiry else ""
        text += f"- `{code}` | {val_str} | {used}/{total}{expiry_str}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.chat_data.clear()
    await update.message.reply_text("عملیات ادمین لغو شد.")
    return ConversationHandler.END

# handlers.py
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta

# ... (سایر ایمپورت‌ها)

# ==================================
# === بخش گزارش‌گیری پیشرفته ===
# ==================================

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی گزارش‌گیری را به ادمین نمایش می‌دهد."""
    keyboard = [
        [InlineKeyboardButton("📊 گزارش ۷ روز اخیر", callback_data="report_7_days")],
        # می‌توانید دکمه‌های گزارش روزانه، ماهانه و کلی را هم بعدا اضافه کنید
    ]
    await update.message.reply_text("لطفاً نوع گزارش مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

def generate_sales_chart(daily_data):
    """یک نمودار میله‌ای از فروش روزانه ساخته و به صورت فایل ذخیره می‌کند."""
    if not daily_data:
        return None

    # استخراج تاریخ‌ها و مقادیر
    dates = [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d") for d, _ in daily_data]
    revenues = [r for _, r in daily_data]

    plt.figure(figsize=(10, 6))
    plt.bar(dates, revenues, color='#4CAF50')

    plt.title('Daily Sales Revenue (Last 7 Days)')
    plt.xlabel('Date')
    plt.ylabel('Revenue (Toman)')
    plt.grid(axis='y', linestyle='--')

    # ذخیره نمودار در یک فایل
    chart_path = "sales_chart.png"
    plt.savefig(chart_path)
    plt.close()

    return chart_path

async def generate_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش را بر اساس انتخاب ادمین تولید و ارسال می‌کند."""
    query = update.callback_query
    await query.answer()

    report_type = query.data
    await query.edit_message_text("در حال پردازش گزارش... لطفاً صبر کنید.")

    if report_type == "report_7_days":
        # دریافت داده‌های ۷ روز اخیر
        daily_data = db.get_daily_sales_for_chart(days=7)

        # محاسبه آمار کلی
        total_sales = len(daily_data) # This is number of days with sales, not total sales
        total_revenue = sum(price for _, price in daily_data)

        # ساخت نمودار
        chart_file = generate_sales_chart(daily_data)

        caption = (
            f"📊 **گزارش عملکرد ۷ روز اخیر**\n\n"
            f"💰 **درآمد کل:** {total_revenue:,} تومان\n"
            f"📈 **تعداد کل فروش‌ها:** (Needs a separate query)\n\n"
            f"نمودار روند فروش روزانه:"
        )

        if chart_file:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=open(chart_file, "rb"),
                caption=caption,
                parse_mode='Markdown'
            )
            os.remove(chart_file) # پاک کردن فایل پس از ارسال
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="در ۷ روز اخیر هیچ فروشی ثبت نشده است.")

    await query.delete_message() # حذف پیام "در حال پردازش"