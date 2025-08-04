import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from config import TOKEN, ADMIN_TELEGRAM_ID
import database as db
import handlers as h

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def main() -> None:
    db.setup_database()
    application = Application.builder().token(TOKEN).build()

    purchase_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(h.start_purchase_flow, pattern="^go_to_purchase$")],
        states={
            h.State.SELECTING_PRODUCT: [CallbackQueryHandler(h.select_product, pattern=r"^product_\d+$")],
            h.State.CONFIRMING_PURCHASE: [
                CallbackQueryHandler(h.show_payment_info, pattern="^confirm_payment_info$"),
                CallbackQueryHandler(h.prompt_for_discount_code, pattern="^apply_discount_code$"),
                CallbackQueryHandler(h.start_purchase_flow, pattern="^back_to_products$")
            ],
            h.State.AWAITING_DISCOUNT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, h.process_discount_code),
                CallbackQueryHandler(h.select_product, pattern=r"^product_\d+$")
            ],
            h.State.AWAITING_RECEIPT: [
                MessageHandler(filters.PHOTO, h.handle_receipt),
                MessageHandler(~filters.PHOTO, h.invalid_receipt)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(h.universal_cancel_and_go_home, pattern="^cancel_purchase$"),
            CommandHandler("start", h.start)
        ],
        conversation_timeout=1800
    )

    add_link_conv = ConversationHandler(
        entry_points=[CommandHandler("addlinks", h.add_links_start, filters=filters.User(ADMIN_TELEGRAM_ID))],
        states={
            h.State.AWAITING_LINK_PRODUCT_CHOICE: [CallbackQueryHandler(h.add_links_product_chosen, pattern=r"^linkprod_\d+$")],
            h.State.AWAITING_LINKS_TO_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, h.add_links_received)],
        },
        fallbacks=[
            CommandHandler("cancel", h.cancel_admin_action),
            CallbackQueryHandler(h.cancel_addlink_action, pattern="^cancel_addlink$")
        ],
        conversation_timeout=600
    )

    reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(h.admin_reject_start, pattern=r"^admin_reject_\d+$")],
        states={
            h.State.AWAITING_REJECTION_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, h.receive_rejection_reason)]
        },
        fallbacks=[CommandHandler("cancel", h.cancel_admin_action)],
        conversation_timeout=300
    )

    # --- ثبت هندلرها ---
    application.add_handler(purchase_conv)
    application.add_handler(add_link_conv)
    application.add_handler(reject_conv)

    # دستورات ادمین
    application.add_handler(CommandHandler("linkstatus", h.link_status_handler, filters=filters.User(ADMIN_TELEGRAM_ID)))
    application.add_handler(CommandHandler("backup", h.backup_database_handler, filters=filters.User(ADMIN_TELEGRAM_ID)))
    application.add_handler(CommandHandler("addcode", h.add_code_command, filters=filters.User(ADMIN_TELEGRAM_ID)))
    application.add_handler(CommandHandler("listcodes", h.list_codes_command, filters=filters.User(ADMIN_TELEGRAM_ID)))

    # دکمه‌های ادمین
    application.add_handler(CallbackQueryHandler(h.admin_approve_handler, pattern=r"^admin_approve_\d+$"))

    # دستورات و دکمه‌های عمومی کاربر
    application.add_handler(CommandHandler("start", h.start))
    application.add_handler(CallbackQueryHandler(h.support_handler, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(h.my_purchases_handler, pattern="^my_purchases$"))
    application.add_handler(CallbackQueryHandler(h.universal_cancel_and_go_home, pattern="^back_to_home$"))

    print("ربات آلبالو با تمام قابلیت‌ها با موفقیت اجرا شد...")
    application.run_polling()

if __name__ == "__main__":
    main()