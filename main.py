import base64
import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
import sqlite3
from dotenv import load_dotenv
import os
from gettext import translation
import aiohttp
import requests
import aiofiles
from PIL import Image
import io

# إعداد السجل لتسجيل الأخطاء والأنشطة
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تحميل متغيرات البيئة من ملف .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")  # استيراد رمز الوصول من متغير البيئة

# إعداد الترجمة
localization = translation('messages', localedir='locales', languages=['ar', 'en'])
localization.install()
_ = localization.gettext

# إنشاء قاعدة البيانات إذا لم تكن موجودة
conn = sqlite3.connect("users.db")
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
conn.close()

def verify_translations():
    for lang in ['ar', 'en']:
        path = f"locales/{lang}/LC_MESSAGES/messages.mo"
        if not os.path.exists(path):
            logger.warning(f"Translation file not found for language: {lang}")


def load_translation(user_id):
    """تحميل الترجمة بناءً على لغة المستخدم"""
    language = get_user_language(user_id)
    try:
        localization = translation('messages', localedir='locales', languages=[language])
        localization.install()
        global _
        _ = localization.gettext
    except Exception as e:
        logger.error(f"Error loading translation for language {language}: {e}")



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

        # تحميل الترجمة الجديدة وتحديث _
        localization = translation('messages', localedir='locales', languages=[new_language])
        localization.install()
        global _
        _ = localization.gettext

        await update.message.reply_text(_("✅ تم تغيير اللغة إلى ") + new_language)
    except (IndexError, ValueError):
        await update.message.reply_text(_("⚠️ يرجى تحديد اللغة كالتالي: /change_language <ar|en>"))
    except Exception as e:
        logger.error(f"Error changing language: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء تغيير اللغة."))



def get_user_language(user_id):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT preferred_language FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
        return result[0] if result else 'en'
    except sqlite3.DatabaseError as e:
        logger.error(f"Error while getting user language: {e}")
        return 'en'

# Admin

def is_admin(user_id):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
        return result and result[0] == 1  # إرجاع True إذا كان المسؤول
    except sqlite3.DatabaseError as e:
        logger.error(f"Error checking admin status: {e}")
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
    except sqlite3.DatabaseError as e:
        logger.error(f"Error saving user: {e}")

# وظيفة بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()

            # إذا كانت قاعدة البيانات فارغة، اجعل أول مستخدم مسؤولًا
            cursor.execute("SELECT COUNT(*) FROM users")
            is_first_user = cursor.fetchone()[0] == 0

            cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, first_name, last_name, is_admin)
            VALUES (?, ?, ?, ?, ?)
            """, (user.id, user.username, user.first_name, user.last_name, 1 if is_first_user else 0))

            conn.commit()

        await update.message.reply_text(_("مرحبًا! تم تسجيلك في قاعدة البيانات. اكتب /help لرؤية قائمة الأوامر."))
    except sqlite3.DatabaseError as e:
        logger.error(f"Error during start: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء تسجيلك."))

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
/change_language - تغيير اللغة المفضلة
/make_session - عمل جلسة
/get_session - استدعاء جلسه
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
            response = _("المستخدمون المسجلون:") + "\n"
            response += "\n".join(
                [_(f"- {u[2]} {u[3]} (@{u[1]}) {'[مسؤول]' if u[4] else ''}") for u in users]
            )
        else:
            response = _("لا يوجد مستخدمون مسجلون بعد.")

        await update.message.reply_text(response)
    except sqlite3.DatabaseError as e:
        logger.error(f"Error fetching users: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء جلب قائمة المستخدمين."))

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
    except sqlite3.DatabaseError as e:
        logger.error(f"Error fetching points: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء جلب النقاط."))

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
            cursor.execute("UPDATE users SET points = points + ? WHERE username = ?", (points_to_add, target_username))
            if cursor.rowcount == 0:
                raise ValueError("User not found")

            conn.commit()

        await update.message.reply_text(_(f"✅ تم إضافة {points_to_add} نقطة للمستخدم {target_username}."))
    except (IndexError, ValueError):
        await update.message.reply_text(_("⚠️ يرجى تقديم المدخلات كالتالي: /add_points <USER_Name> <POINTS>"))
    except sqlite3.DatabaseError as e:
        logger.error(f"Error adding points: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء إضافة النقاط."))

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
            cursor.execute("UPDATE users SET points = points - ? WHERE username = ?", (points_to_remove, target_username))
            if cursor.rowcount == 0:
                raise ValueError("User not found")

            conn.commit()

        await update.message.reply_text(_(f"✅ تم خصم {points_to_remove} نقطة من المستخدم {target_username}."))
    except (IndexError, ValueError):
        await update.message.reply_text(_("⚠️ يرجى تقديم المدخلات كالتالي: /remove_points <USER_name> <POINTS>"))
    except sqlite3.DatabaseError as e:
        logger.error(f"Error removing points: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء خصم النقاط."))

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
    except (IndexError, ValueError):
        await update.message.reply_text(_("⚠️ يرجى تقديم معرف المستخدم كالتالي: /promote <USER_name>"))
    except sqlite3.DatabaseError as e:
        logger.error(f"Error promoting user: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء ترقية المستخدم."))


#makesession
async def make_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user.username
    url = f"https://flayers.onrender.com/add-session/{user_id}/{user}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    await update.message.reply_text(_(f"📄 تم جلب البيانات بنجاح:\n{data}"))
                else:
                    await update.message.reply_text(_(f"⚠️ فشل في جلب البيانات. كود الحالة: {response.status}"))
    except Exception as e:
        logger.error(f"Error fetching session data: {e}")
        await update.message.reply_text(_("⚠️ حدث خطأ أثناء جلب البيانات."))


#getsession
async def get_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id    
    url = f"https://flayers.onrender.com/qrcode/{user_id}"
    try:
        # طلب HTTP لجلب الصورة
       async with aiohttp.ClientSession() as session:
       async with session.get(url) as response:
        content_type = response.headers.get('Content-Type', '')
        if 'image' not in content_type:
            logger.error(f"Invalid content type: {content_type}")
            await update.message.reply_text("⚠️ الرابط لا يُرجع صورة.")
        else:
            image_data = await response.read()

                    # التحقق من أن البيانات تمثل صورة صالحة
                    try:
                        image = Image.open(io.BytesIO(image_data))
                        image.verify()  # التحقق من صحة الصورة

                        # حفظ الصورة مؤقتًا
                        file_path = f"temp_qrcode_{user_id}.png"
                        async with aiofiles.open(file_path, "wb") as file:
                            await file.write(image_data)

                        # إرسال الصورة إلى المستخدم
                        with open(file_path, "rb") as file:
                            await update.message.reply_photo(file, caption="📸 هذا هو رمز الاستجابة السريعة الخاص بك!")

                        # حذف الملف المؤقت
                        os.remove(file_path)
                    except Exception as img_error:
                        logger.error(f"Image processing failed: {img_error}")
                        await update.message.reply_text("⚠️ البيانات المستلمة ليست صورة صالحة.")
                else:
                    await update.message.reply_text(f"⚠️ حدث خطأ أثناء جلب الصورة. كود الحالة: {response.status}")
    except Exception as e:
        logger.error(f"Error fetching session image: {e}")
        await update.message.reply_text("⚠️ حدث خطأ أثناء جلب الصورة.")


def main():
    # إنشاء تطبيق البوت
    application = Application.builder().token(TOKEN).build()

    # إعداد قائمة الأوامر للبوت
    commands = [
        BotCommand("start", _( "تسجيل المستخدم في قاعدة البيانات")),
        BotCommand("help", _( "عرض قائمة الأوامر")),
        BotCommand("show_users", _( "عرض المستخدمين المسجلين (للمسؤولين فقط)")),
        BotCommand("promote", _( "ترقية مستخدم إلى مسؤول (للمسؤولين فقط)")),
        BotCommand("show_points", _( "عرض نقاطك الحالية")),
        BotCommand("add_points", _( "إضافة نقاط لمستخدم (للمسؤولين فقط)")),
        BotCommand("remove_points", _( "خصم نقاط من مستخدم (للمسؤولين فقط)")),
        BotCommand("change_language", _( "تغيير اللغة المفضلة")),
        BotCommand("make_session", _( "عمل جلسة جديدة")),
        BotCommand("get_session", _( "استدعاء جلسة ")),
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
    application.add_handler(CommandHandler("make_session", make_session))
    application.add_handler(CommandHandler("get_session", get_session))

    # بدء البوت
    application.run_polling()

if __name__ == "__main__":
    verify_translations()
    main()
