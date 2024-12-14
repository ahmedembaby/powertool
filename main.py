import base64
import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
import sqlite3
from dotenv import load_dotenv
import os
from gettext import translation
from sqlite3 import DatabaseError

# تحميل متغيرات البيئة من ملف .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")  # استيراد رمز الوصول من متغير البيئة


# إعداد التسجيل (Logging)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# إنشاء قاعدة البيانات إذا لم تكن موجودة
def create_db():
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                preferred_language TEXT DEFAULT 'en'
            )
            """)
            conn.commit()
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users (username)")
            conn.commit()
    except DatabaseError as e:
        logger.error(f"Error while creating database: {e}")

create_db()

async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    try:
        new_language = context.args[0]
        if new_language not in ['ar', 'en']:
            raise ValueError("Invalid language")

        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET preferred_language = ? WHERE id = ?", (new_language, user_id))
            conn.commit()

        await update.message.reply_text(_("✅ تم تغيير اللغة إلى ") + new_language)
    except (IndexError, ValueError):
        await update.message.reply_text(_("⚠️ يرجى تحديد اللغة كالتالي: /change_language <ar|en>"))

def get_user_language(user_id):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT preferred_language FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
        return result[0] if result else 'en'
    except DatabaseError as e:
        logger.error(f"Error while getting user language: {e}")
        return 'en'

async def localized_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    user_language = get_user_language(update.effective_user.id)
    localization = translation('messages', localedir='locales', languages=[user_language])
    localization.install()
    _ = localization.gettext

    await update.message.reply_text(_(message))

# Admin
def is_admin(user_id):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
        return result and result[0] == 1
    except DatabaseError as e:
        logger.error(f"Error while checking admin status: {e}")
        return False

# حفظ معلومات المستخدم في قاعدة البيانات
def save_user(user):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            """, (user.id, user.username, user.first_name, user.last_name))
            conn.commit()
    except DatabaseError as e:
        logger.error(f"Error while saving user: {e}")

# وظيفة بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            is_first_user = cursor.fetchone()[0] == 0
            cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, first_name, last_name, is_admin)
            VALUES (?, ?, ?, ?, ?)
            """, (user.id, user.username, user.first_name, user.last_name, 1 if is_first_user else 0))
            conn.commit()

        await update.message.reply_text(_("مرحبًا! تم تسجيلك في قاعدة البيانات. اكتب /help لرؤية قائمة الأوامر."))
    except DatabaseError as e:
        logger.error(f"Error while starting bot: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء التسجيل في قاعدة البيانات."))

# وظيفة عرض قائمة الأوامر
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = _(
        """
قائمة الأوامر المتاحة:
/help - عرض قائمة الأوامر
/show_points - عرض النقاط
/add_points - إضافة نقاط (للمسؤولين فقط)
/remove_points - خصم نقاط (للمسؤولين فقط)
/promote - ترقية مستخدم إلى مسؤول (للمسؤولين فقط)
/show_users - عرض المستخدمين المسجلين (للمسؤولين فقط)
        """
    )
    await update.message.reply_text(commands)

# وظيفة لعرض المستخدمين المسجلين
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(_("🚫 هذا الأمر متاح فقط للمسؤولين."))
        return

    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, first_name, last_name, is_admin FROM users")
            users = cursor.fetchall()

        if users:
            response = _("") + "\n"
            response += "\n".join(
                [_(f"- {u[2]} {u[3]} (@{u[1]}) {'[مسؤول]' if u[4] else ''}") for u in users]
            )
        else:
            response = _("لا يوجد مستخدمون مسجلون بعد.")

        await update.message.reply_text(response)
    except DatabaseError as e:
        logger.error(f"Error while showing users: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء عرض المستخدمين."))

# وظيفة عرض النقاط
async def show_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT points FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()

        if result:
            points = result[0]
            await update.message.reply_text(_(f"🎉 لديك {points} نقطة!"))
        else:
            await update.message.reply_text(_("⚠️ لم يتم العثور على نقاط لك."))
    except DatabaseError as e:
        logger.error(f"Error while showing points: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء عرض النقاط."))

# إضافة نقاط
async def add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(_("🚫 هذا الأمر متاح فقط للمسؤولين."))
        return

    try:
        target_username = context.args[0]
        points_to_add = int(context.args[1])

        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
            user_id = cursor.fetchone()
            if not user_id:
                raise ValueError("User not found")
            cursor.execute("UPDATE users SET points = points + ? WHERE username = ?", (points_to_add, target_username))
            conn.commit()

        await update.message.reply_text(_(f"✅ تم إضافة {points_to_add} نقطة للمستخدم {target_username}."))
    except (IndexError, ValueError) as e:
        logger.error(f"Error while adding points: {e}")
        await update.message.reply_text(_("⚠️ يرجى تقديم المدخلات كالتالي: /add_points <USER_Name> <POINTS>"))

# خصم نقاط
async def remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(_("🚫 هذا الأمر متاح فقط للمسؤولين."))
        return

    try:
        target_username = context.args[0]
        points_to_remove = int(context.args[1])

        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
            user_id = cursor.fetchone()
            if not user_id:
                raise ValueError("User not found")
            cursor.execute("UPDATE users SET points = points - ? WHERE username = ?", (points_to_remove, target_username))
            conn.commit()

        await update.message.reply_text(_(f"✅ تم خصم {points_to_remove} نقطة من المستخدم {target_username}."))
    except (IndexError, ValueError) as e:
        logger.error(f"Error while removing points: {e}")
        await update.message.reply_text(_("⚠️ يرجى تقديم المدخلات كالتالي: /remove_points <USER_name> <POINTS>"))

# ترقية مستخدم
async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(_("🚫 هذا الأمر متاح فقط للمسؤولين."))
        return

    try:
        target_username = context.args[0]

        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (target_username,))
            if cursor.rowcount == 0:
                raise ValueError("User not found")
            conn.commit()

        await update.message.reply_text(_(f"✅ تم ترقية المستخدم {target_username} إلى مسؤول."))
    except (IndexError, ValueError) as e:
        logger.error(f"Error while promoting user: {e}")
        await update.message.reply_text(_("⚠️ يرجى تقديم معرف المستخدم كالتالي: /promote <USER_name>"))

def main():
    # إنشاء تطبيق البوت
    application = Application.builder().token(TOKEN).build()

    # إعداد قائمة الأوامر للبوت
    commands = [
        BotCommand("start", _("تسجيل المستخدم في قاعدة البيانات")),
        BotCommand("help", _("عرض قائمة الأوامر")),
        BotCommand("show_users", _("عرض المستخدمين المسجلين (للمسؤولين فقط)")),
        BotCommand("promote", _("ترقية مستخدم إلى مسؤول (للمسؤولين فقط)")),
        BotCommand("show_points", _("عرض نقاطك الحالية")),
        BotCommand("add_points", _("إضافة نقاط لمستخدم (للمسؤولين فقط)")),
        BotCommand("remove_points", _("خصم نقاط من مستخدم (للمسؤولين فقط)")),
        BotCommand("change_language", _("تغيير اللغة المفضلة")),
    ]
    application.bot.set_my_commands(commands)

    # إضافة Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("change_language", change_language))
    application.add_handler(CommandHandler("show_users", show_users))
    application.add_handler(CommandHandler("promote", promote_user))
    application.add_handler(CommandHandler("show_points", show_points))
    application.add_handler(CommandHandler("add_points", add_points))
    application.add_handler(CommandHandler("remove_points", remove_points))

    # بدء البوت
    application.run_polling()

if __name__ == "__main__":
    main()
