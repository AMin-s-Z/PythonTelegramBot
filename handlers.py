import re
from enum import Enum
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
from datetime import datetime

# تعریف وضعیت‌های مکالمه
class State(Enum):
    SELECTING_PRODUCT, CONFIRMING_PURCHASE, AWAITING_RECEIPT = range(3)
    AWAITING_REJECTION_REASON = 11
    AWAITING_LINK_PRODUCT_CHOICE, AWAITING_LINKS_TO_ADD = range(20, 22)

# ==================================
# === بخش صفحه اصلی و کاربر ===
# ==================================
async def show_home_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """صفحه اصلی (داشبورد) را به کاربر نمایش می‌دهد."""
    user = update.effective_user
    db.add_or_update_user(user.id, user.first_name, user.username)
    text = f"سلام {user.first_name} عزیز! 👋\nبه ربات فروش ما خوش آمدید."

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
    user_id = update.effective_user.id
    user_links = db.get_user_links(user_id)

    if not user_links:
        text = "شما تاکنون هیچ خرید فعالی نداشته‌اید."
    else:
        text = "📄 **لیست سرویس‌های فعال شما:**\n\n"
        for i, (product_name, link, purchase_date) in enumerate(user_links, 1):
            text += f"🔹 **{product_name}** (خرید: {purchase_date})\n`{link}`\n\n"

    keyboard = [[InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="back_to_home")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown', disable_web_page_preview=True)

async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اطلاعات پشتیبانی را نمایش می‌دهد."""
    query = update.callback_query
    await query.answer()
    text = "📞 **پشتیبانی**\n\nبرای ارتباط با ما، لطفاً به آیدی @YourSupportID پیام دهید."
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="back_to_home")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
    context.user_data['selected_product_id'] = product_id
    context.user_data['selected_product'] = product
    name, price, description = product
    text = f"شما «{name}» را انتخاب کردید.\n💰 قیمت: {price:,} تومان\n\nآیا ادامه می‌دهید؟"
    keyboard = [
        [InlineKeyboardButton("✅ بله، دریافت اطلاعات پرداخت", callback_data='confirm_payment_info')],
        [InlineKeyboardButton("➡️ بازگشت به لیست محصولات", callback_data='back_to_products')],
        [InlineKeyboardButton("⬅️ بازگشت به داشبورد", callback_data="cancel_purchase")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return State.CONFIRMING_PURCHASE

async def show_payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    product_id = context.user_data['selected_product_id']
    product_name, price, _ = context.user_data['selected_product']
    transaction_id = db.create_pending_transaction(user_id, product_id, product_name, price)
    context.user_data['transaction_id'] = transaction_id
    text = (
        f"✅ **مرحله پرداخت برای «{product_name}»**\n\n"
        f" شناسه خرید شما: `{transaction_id}` (این کد رهگیری شماست)\n\n"
        f"لطفاً مبلغ **{price:,} تومان** را به کارت زیر واریز کنید:\n\n"
        f"💳 شماره کارت: `{config.BANK_CARD_INFO['card_number']}`\n"
        f"👤 به نام: **{config.BANK_CARD_INFO['card_holder']}**\n\n"
        f"‼️ **مهم:** پس از پرداخت، اسکرین‌شات واضح رسید را در همین صفحه ارسال کنید."
    )
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
    caption = (
        f"🔔 **درخواست جدید**\n\n"
        f"👤 کاربر: {user.first_name} (@{user.username or 'ندارد'})\n"
        f"🆔 آیدی کاربر: `{user.id}`\n"
        f"🛍️ محصول: **{product_name}** ({price:,} تومان)\n"
        f" شناسه خرید: `{transaction_id}`\n\n"
        f" وضعیت: ⏳ در انتظار بررسی"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ تایید خودکار", callback_data=f"admin_approve_{transaction_id}"),
            InlineKeyboardButton("❌ رد کردن", callback_data=f"admin_reject_{transaction_id}")
        ]
    ]
    await context.bot.send_photo(
        chat_id=config.ADMIN_CHANNEL_ID,
        photo=update.message.photo[-1].file_id,
        caption=caption,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ رسید شما با موفقیت ثبت شد. لطفاً منتظر تایید مدیر بمانید...")
    await context.bot.send_message(chat_id=config.ADMIN_TELEGRAM_ID, text=f"یک درخواست جدید با شناسه {transaction_id} در کانال مدیریت ثبت شد.")
    return ConversationHandler.END

async def invalid_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً فقط **عکس رسید پرداخت** را ارسال کنید.")
    return State.AWAITING_RECEIPT

async def universal_cancel_and_go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """یک تابع جامع برای لغو هر عملیات و بازگشت به منوی اصلی."""
    if update.callback_query:
        await show_home_menu(update, context)
    else:
        await start(update, context)
    return ConversationHandler.END

# ==================================
# === پنل ادمین هوشمند ===
# ==================================
async def admin_approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پرداخت را با استفاده از بانک لینک به صورت خودکار تایید و ارسال می‌کند."""
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
        await context.bot.send_message(chat_id=update.effective_user.id, text=f"خطا: موجودی لینک برای «{product_name}» تمام شده. لطفاً با دستور /addlinks آن را شارژ کنید.")

async def admin_reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """مکالمه برای رد کردن پرداخت را شروع می‌کند."""
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

    await query.edit_message_caption(
        caption=f"⏳ در حال رد کردن شناسه {transaction_id}...\nلطفاً دلیل را در چت خصوصی ربات ارسال کنید.",
        reply_markup=None
    )
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=f"شما در حال رد کردن تراکنش `{transaction_id}` هستید. لطفاً دلیل را ارسال کنید یا با /cancel لغو کنید."
    )
    return State.AWAITING_REJECTION_REASON

async def receive_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دلیل رد را دریافت و به کاربر ارسال می‌کند."""
    reason = update.message.text
    admin_user = update.effective_user

    target_user_id = context.chat_data.pop('target_user_id')
    transaction_id = context.chat_data.pop('transaction_id')
    channel_id = context.chat_data.pop('channel_id')
    message_id = context.chat_data.pop('channel_message_id')

    db.update_transaction_status(transaction_id, 'rejected')

    await context.bot.send_message(
        chat_id=target_user_id,
        text=f" متاسفانه پرداخت شما برای شناسه خرید `{transaction_id}` توسط مدیر رد شد.\n\n"
             f"**دلیل:** {reason}",
        parse_mode='Markdown'
    )

    _, product_name, _, _ = db.get_transaction(transaction_id)
    final_caption = (
        f"❌ **رد شد**\nمحصول: {product_name}\nشناسه: {transaction_id}\nتوسط: {admin_user.first_name}\nدلیل: {reason}"
    )
    await context.bot.edit_message_caption(
        chat_id=channel_id, message_id=message_id, caption=final_caption, parse_mode='Markdown'
    )
    await update.message.reply_text(f"پیام رد پرداخت برای کاربر `{target_user_id}` ارسال و وضعیت در کانال آپدیت شد.")
    return ConversationHandler.END

# --- فرآیند افزودن لینک به بانک ---
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
    if update.callback_query:
        await update.callback_query.edit_message_text("عملیات افزودن لینک لغو شد.")
    else:
        await update.message.reply_text("عملیات افزودن لینک لغو شد.")
    context.chat_data.clear()
    return ConversationHandler.END

# --- دستور مشاهده وضعیت بانک لینک ---
async def link_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = db.get_link_bank_status()
    if not status:
        text = "بانک لینک خالی است."
    else:
        text = "📊 **وضعیت موجودی بانک لینک:**\n\n"
        for product_name, count in status:
            text += f"🔹 **{product_name}**: {count} لینک باقی‌مانده\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.chat_data.clear()
    await update.message.reply_text("عملیات ادمین لغو شد.")
    return ConversationHandler.END
# ==================================
# === دستورات ویژه ادمین ===
# ==================================
async def backup_database_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """یک نسخه از فایل دیتابیس را به کانال ادمین ارسال می‌کند."""
    user_id = update.effective_user.id
    if user_id != config.ADMIN_TELEGRAM_ID:
        # این دستور فقط برای ادمین اصلی است
        return

    await update.message.reply_text("در حال آماده‌سازی فایل بکاپ... لطفاً صبر کنید.")

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        caption_text = f" backup\n {timestamp}"

        await context.bot.send_document(
            chat_id=config.ADMIN_CHANNEL_ID,
            document=open("store.db", "rb"),
            filename=f"backup_{timestamp}.db",
            caption=caption_text
        )
        await update.message.reply_text("✅ بکاپ دیتابیس با موفقیت به کانال مدیریت ارسال شد.")
    except Exception as e:
        print(f"Error during backup: {e}")
        await update.message.reply_text(f"❌ خطایی در هنگام ارسال فایل بکاپ رخ داد: {e}")
