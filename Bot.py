import os
import re
import json
import time
import logging
from dotenv import load_dotenv
from telegram import *
from telegram.ext import *

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Storage files
for file in ["users.txt", "groups.txt", "warns.json"]:
    if not os.path.exists(file):
        open(file, "w").close()
if os.path.getsize("warns.json") == 0:
    with open("warns.json", "w") as f:
        f.write("{}")

MUTE_DURATION = 2  # default in hours

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    name = user.first_name

    # Track private user
    if update.message.chat.type == "private":
        if str(uid) not in open("users.txt").read():
            with open("users.txt", "a") as f:
                f.write(f"{uid}\n")

    # Check channel join
    try:
        member = context.bot.get_chat_member(f"@{UPDATE_CHANNEL}", uid)
        if member.status not in ['member', 'administrator', 'creator']:
            raise Exception("Not joined")
    except:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{UPDATE_CHANNEL}")]])
        return update.message.reply_text("🔒 Please join our update channel to use me.", reply_markup=keyboard)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])
    update.message.reply_text(f"👋 Welcome {name}!\n\nI'm your anti-link bot to mute spammers with links in bio or messages.", reply_markup=keyboard)

def help_button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    text = (
        "🤖 *Bot Commands:*\n\n"
        "/start - Start the bot\n"
        "/help - Show help menu\n"
        "/setmute <hours> - Set mute duration (owner only)\n"
        "/status - Show bot status (owner only)\n"
        "/broadcast -user - Send to users and groups\n"
        "/broadcast -user -pin - Pin in groups too\n"
        "/restart - Restart bot (owner only)"
    )
    query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

def add_group(update: Update, context: CallbackContext):
    chat = update.effective_chat
    if str(chat.id) not in open("groups.txt").read():
        with open("groups.txt", "a") as f:
            f.write(f"{chat.id}\n")
            from telegram.ext.filters import Filters
from telegram.error import BadRequest, Unauthorized

def is_link(text):
    return bool(re.search(r"(https?://|t\.me/|www\.)", text))

def bio_or_msg_has_link(user, message):
    bio = user.bio or ""
    text = message.text or ""
    return is_link(bio) or is_link(text)

def warn_user(user_id):
    with open("warns.json", "r") as f:
        warns = json.load(f)
    warns[str(user_id)] = warns.get(str(user_id), 0) + 1
    with open("warns.json", "w") as f:
        json.dump(warns, f)
    return warns[str(user_id)]

def reset_warn(user_id):
    with open("warns.json", "r") as f:
        warns = json.load(f)
    warns[str(user_id)] = 0
    with open("warns.json", "w") as f:
        json.dump(warns, f)

def mute_user(chat_id, user_id, hours, context):
    until_date = int(time.time() + hours * 3600)
    try:
        context.bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=until_date)
        return True
    except:
        return False

def send_mute_notice(context, user, reason, group_name):
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
            [InlineKeyboardButton(f"🔓 Unmute – @{BOT_USERNAME}", url=f"https://t.me/{BOT_USERNAME}")]
        ])
        context.bot.send_message(
            chat_id=user.id,
            text=f"⚔️ *Bio mute*\n👤 {user.first_name} (`{user.id}`)\n⛔ {reason}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    except:
        pass  # user blocked bot

def message_handler(update: Update, context: CallbackContext):
    message = update.effective_message
    user = message.from_user
    chat = update.effective_chat
    uid = user.id
    fname = user.first_name

    # Skip non-group
    if chat.type != "group" and chat.type != "supergroup":
        return

    # Track group
    if str(chat.id) not in open("groups.txt").read():
        with open("groups.txt", "a") as f:
            f.write(f"{chat.id}\n")

    # Skip admins
    member = chat.get_member(uid)
    if member.status in ["administrator", "creator"]:
        return

    # Check for link in message or bio
    bio = user.bio or ""
    text = message.text or ""
    if is_link(text) or is_link(bio):
        message.delete()
        count = warn_user(uid)
        if count < 4:
            context.bot.send_message(chat.id, f"⚠️ Warning {count}/3 to [{fname}](tg://user?id={uid}) for link in bio/message.", parse_mode=ParseMode.MARKDOWN)
        else:
            reset_warn(uid)
            if mute_user(chat.id, uid, MUTE_DURATION, context):
                reason = f"Muted for {MUTE_DURATION} hours due to repeated link spam."
                # Group mute notice
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
                    [InlineKeyboardButton(f"🔓 Unmute – @{BOT_USERNAME}", url=f"https://t.me/{BOT_USERNAME}")]
                ])
                context.bot.send_message(chat.id, f"⚔️ *Bio mute*\n👤 {fname} (`{uid}`)\n⛔ {reason}", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
                # DM mute notice
                send_mute_notice(context, user, reason, chat.title)
    elif "@" in text:
        pass  # allow username

def join_handler(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        uid = member.id
        fname = member.first_name
        chat = update.effective_chat

        # If first name contains link/username → mute permanently
        if is_link(fname) or "@" in fname:
            mute_user(chat.id, uid, 999999, context)
            send_mute_notice(context, member, "Permanently muted due to link in name.", chat.title)
            from telegram.ext import CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ChatMemberHandler
from telegram.utils.helpers import mention_html

def broadcast(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id != OWNER_ID:
        return update.message.reply_text("⛔ Only the bot owner can use this command.")

    args = context.args
    pin = "-pin" in args
    to_users = "-user" in args
    count = 0
    msg = update.message.reply_to_message or update.message

    with open("groups.txt") as f: groups = f.read().splitlines()
    with open("users.txt") as f: users = f.read().splitlines()

    for gid in groups:
        try:
            if msg.photo:
                sent = context.bot.send_photo(chat_id=int(gid), photo=msg.photo[-1].file_id, caption=msg.caption)
            else:
                sent = context.bot.send_message(chat_id=int(gid), text=msg.text or msg.caption)
            if pin:
                context.bot.pin_chat_message(chat_id=int(gid), message_id=sent.message_id, disable_notification=True)
            count += 1
        except:
            remove_id("groups.txt", gid)

    if to_users:
        for uid in users:
            try:
                if msg.photo:
                    context.bot.send_photo(chat_id=int(uid), photo=msg.photo[-1].file_id, caption=msg.caption)
                else:
                    context.bot.send_message(chat_id=int(uid), text=msg.text or msg.caption)
                count += 1
            except:
                remove_id("users.txt", uid)

    update.message.reply_text(f"✅ Broadcast sent to {count} chats.")

def remove_id(filename, id_):
    lines = open(filename).read().splitlines()
    if id_ in lines:
        lines.remove(id_)
        with open(filename, "w") as f:
            f.write("\n".join(lines))

def setmute(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id != OWNER_ID:
        return update.message.reply_text("⛔ Owner only.")
    try:
        global MUTE_DURATION
        MUTE_DURATION = int(context.args[0])
        update.message.reply_text(f"✅ Mute duration set to {MUTE_DURATION} hour(s).")
    except:
        update.message.reply_text("Usage: /setmute 2")

def status(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return
    gcount = len(open("groups.txt").read().splitlines())
    ucount = len(open("users.txt").read().splitlines())
    update.message.reply_text(f"📊 Status:\n👥 Groups: {gcount}\n👤 Users: {ucount}\n⏱ Mute Time: {MUTE_DURATION} hour(s)")

def restart(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return
    update.message.reply_text("♻️ Restarting bot...")
    os.execl(sys.executable, sys.executable, *sys.argv)

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_button))
    dp.add_handler(CommandHandler("broadcast", broadcast, filters=Filters.reply))
    dp.add_handler(CommandHandler("setmute", setmute))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("restart", restart))

    # Buttons
    dp.add_handler(CallbackQueryHandler(help_button, pattern="help"))

    # Handlers
    dp.add_handler(MessageHandler(Filters.text & Filters.group, message_handler))
    dp.add_handler(ChatMemberHandler(join_handler, ChatMemberHandler.CHAT_MEMBER))

    # Start
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
