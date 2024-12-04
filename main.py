import base64
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
import sqlite3
from dotenv import load_dotenv
import os

# تحميل متغيرات البيئة من ملف .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")  # استيراد رمز الوصول من متغير البيئة

# Admin
def is_admin(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()

    conn.close()
    return result and result[0] == 1  # إرجاع True إذا كان المسؤول


# حفظ معلومات المستخدم في قاعدة البيانات
def save_user(user):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO users (id, username, first_name, last_name)
    VALUES (?, ?, ?, ?)
    """, (user.id, user.username, user.first_name, user.last_name))

    conn.commit()
    conn.close()

# وظيفة بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # إذا كانت قاعدة البيانات فارغة، اجعل أول مستخدم مسؤولًا
    cursor.execute("SELECT COUNT(*) FROM users")
    is_first_user = cursor.fetchone()[0] == 0

    cursor.execute("""
    INSERT OR IGNORE INTO users (id, username, first_name, last_name, is_admin)
    VALUES (?, ?, ?, ?, ?)
    """, (user.id, user.username, user.first_name, user.last_name, 1 if is_first_user else 0))

    conn.commit()
    conn.close()

    await update.message.reply_text("مرحبًا! تم تسجيلك في قاعدة البيانات. اكتب /help لرؤية قائمة الأوامر.")

# وظيفة عرض قائمة الأوامر
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = """
قائمة الأوامر المتاحة:
/help - عرض قائمة الأوامر
/show_points - عرض النقاط
    """
    await update.message.reply_text(commands)

# وظيفة لعرض المستخدمين المسجلين
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("🚫 هذا الأمر متاح فقط للمسؤولين.")
        return

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, username, first_name, last_name, is_admin FROM users")
    users = cursor.fetchall()
    conn.close()

    if users:
        response = "المستخدمون المسجلون:\n"
        response += "\n".join(
            [f"- {u[2]} {u[3]} (@{u[1]}) {'[مسؤول]' if u[4] else ''}" for u in users]
        )
    else:
        response = "لا يوجد مستخدمون مسجلون بعد."

    await update.message.reply_text(response)

#وظيفة عرض النقاط
async def show_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT points FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        points = result[0]
        await update.message.reply_text(f"🎉 لديك {points} نقطة!")
    else:
        await update.message.reply_text("⚠️ لم يتم العثور على نقاط لك.")


#اضافة نقاط
async def add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("🚫 هذا الأمر متاح فقط للمسؤولين.")
        return

    try:
        target_id = context.args[0]
        points_to_add = int(context.args[1])

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET points = points + ? WHERE username = ?", (points_to_add, target_id))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم إضافة {points_to_add} نقطة للمستخدم {target_id}.")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ يرجى تقديم المدخلات كالتالي: /add_points <USER_Name> <POINTS>")

#خصم نقاط
async def remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("🚫 هذا الأمر متاح فقط للمسؤولين.")
        return

    try:
        target_id = context.args[0]
        points_to_remove = int(context.args[1])

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET points = points - ? WHERE username = ?", (points_to_remove, target_id))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم خصم {points_to_remove} نقطة من المستخدم {target_id}.")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ يرجى تقديم المدخلات كالتالي: /remove_points <USER_name> <POINTS>")


#وظيفه لترقية مستخدم
async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("🚫 هذا الأمر متاح فقط للمسؤولين.")
        return

    try:
        target_id = context.args[0]
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (target_id,))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم ترقية المستخدم {target_id} إلى مسؤول.")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ يرجى تقديم معرف المستخدم كالتالي: /promote <USER_name>")


def main():
    # إنشاء تطبيق البوت
    application = Application.builder().token(TOKEN).build()

    # إعداد قائمة الأوامر للبوت
    commands = [
    BotCommand("start", "تسجيل المستخدم في قاعدة البيانات"),
    BotCommand("help", "عرض قائمة الأوامر"),
    BotCommand("show_users", "عرض المستخدمين المسجلين (للمسؤولين فقط)"),
    BotCommand("promote", "ترقية مستخدم إلى مسؤول (للمسؤولين فقط)"),
    BotCommand("show_points", "عرض نقاطك الحالية"),
    BotCommand("add_points", "إضافة نقاط لمستخدم (للمسؤولين فقط)"),
    BotCommand("remove_points", "خصم نقاط من مستخدم (للمسؤولين فقط)"),
]
    application.bot.set_my_commands(commands)



    # إضافة Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("show_users", show_users))
    application.add_handler(CommandHandler("promote", promote_user))
    application.add_handler(CommandHandler("show_points", show_points))
    application.add_handler(CommandHandler("add_points", add_points))
    application.add_handler(CommandHandler("remove_points", remove_points))
   
    # بدء البوت
    application.run_polling()

if __name__ == "__main__":
    main()
