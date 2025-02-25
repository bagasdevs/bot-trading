import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from collections import defaultdict
from keep_alive import keep_alive
import re
import os
from dotenv import load_dotenv

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

# Menyimpan data pesan yang telah diproses
message_database = defaultdict(int)
processed_messages = []

# Fungsi untuk mengekstrak teks tertentu dari pesan
def extract_text(text, pattern=None):
    """
    Ekstrak teks berdasarkan pola tertentu.
    Khusus untuk baris yang dimulai dengan Ca: dan User:
    """
    lines = text.split('\n')
    extracted = []
    for line in lines:
        if line.startswith('Ca:') or line.startswith('User:'):
            extracted.append(line.strip())
    return '\n'.join(extracted) if extracted else text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan dengan tombol menu saat /start diterima."""
    keyboard = [
        [InlineKeyboardButton("🔍 Monitor Channel", callback_data='monitor'),
         InlineKeyboardButton("⏹️ Stop Monitor", callback_data='stop')],
        [InlineKeyboardButton("📋 List Messages", callback_data='list'),
         InlineKeyboardButton("🗑️ Clear Messages", callback_data='clear')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Hai! Saya adalah bot yang mengumpulkan dan mengorganisir pesan dari channel.\n'
        'Silakan pilih menu di bawah ini:',
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'monitor':
        await query.message.reply_text(
            'Silakan kirim channel ID yang ingin dipantau dengan format:\n'
            'channel: @channelname'
        )
    elif query.data == 'stop':
        await stop_monitoring(update, context)
    elif query.data == 'list':
        await list_messages(update, context)
    elif query.data == 'clear':
        await clear_messages(update, context)
    elif query.data == 'help':
        await help_command(update, context)

async def get_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mendapatkan channel ID dari link channel"""
    if not context.args:
        await update.message.reply_text('Format: /getchannel <channel_username>\nContoh: /getchannel myChannel')
        return
        
    channel_username = context.args[0].replace('@', '')
    if '/' in channel_username:
        channel_username = channel_username.split('/')[-1]
    
    channel_id = f"@{channel_username}"
    await update.message.reply_text(f'Channel ID untuk {channel_username} adalah:\n{channel_id}')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan bantuan saat command /help diterima."""
    help_text = (
        'Daftar perintah:\n'
        '/start - Memulai bot\n'
        '/help - Menampilkan pesan bantuan\n'
        '/getchannel <username> - Mendapatkan channel ID dari username channel\n'
        '/monitor <channel_id> - Mulai memantau channel dengan ID tertentu (ekstrak Ca: dan User:)\n'
        '/stop - Berhenti memantau channel\n'
        '/list - Menampilkan daftar pesan yang telah diproses\n'
        '/clear - Menghapus semua pesan yang telah diproses'
    )
    await update.message.reply_text(help_text)

async def monitor_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id=None) -> None:
    """
    Memulai pemantauan channel dengan ID tertentu.
    """
    if not channel_id:
        return
    
    channel_id = '@' + channel_id
    
    # Simpan informasi channel yang dipantau ke dalam context.user_data
    context.user_data['monitored_channel'] = channel_id
    
    await update.message.reply_text(f'Mulai memantau channel: {channel_id}\nMengekstrak baris Ca: dan User: secara otomatis')

async def stop_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Berhenti memantau channel."""
    if 'monitored_channel' in context.user_data:
        channel = context.user_data['monitored_channel']
        del context.user_data['monitored_channel']
        if 'pattern' in context.user_data:
            del context.user_data['pattern']
        await update.message.reply_text(f'Berhenti memantau channel: {channel}')
    else:
        await update.message.reply_text('Tidak ada channel yang sedang dipantau.')

async def list_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menampilkan daftar pesan yang telah diproses."""
    if not processed_messages:
        await update.message.reply_text('Tidak ada pesan yang telah diproses.')
        return
    
    result = "Daftar pesan yang telah diproses:\n\n"
    for idx, msg in enumerate(processed_messages, 1):
        result += f"{idx}. {msg}\n"
    
    await update.message.reply_text(result)

async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus semua pesan yang telah diproses."""
    global message_database, processed_messages
    message_database = defaultdict(int)
    processed_messages = []
    await update.message.reply_text('Semua pesan telah dihapus.')

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Menangani pesan yang masuk dari channel yang dipantau.
    Mengekstrak teks tertentu dan mengatur duplikat.
    """
    # Pastikan ada channel yang dipantau
    if 'monitored_channel' not in context.user_data:
        return
    
    # Pastikan pesan berasal dari channel yang dipantau
    channel_id = str(update.channel_post.chat_id)
    if channel_id != context.user_data['monitored_channel']:
        return
    
    # Dapatkan teks dari pesan
    if not update.channel_post.text:
        return
    
    original_text = update.channel_post.text
    
    # Ekstrak teks sesuai pola jika ada
    pattern = context.user_data.get('pattern')
    extracted_text = extract_text(original_text, pattern)
    
    # Periksa jika teks sudah ada dalam database
    message_database[extracted_text] += 1
    count = message_database[extracted_text]
    
    # Format pesan dengan menambahkan counter jika duplikat
    formatted_text = extracted_text
    if not formatted_text.strip():
        return  # Skip if no Ca: or User: lines found
    if count > 1:
        formatted_text += f"\n(Duplikat #{count})"
    
    # Tambahkan ke daftar pesan yang diproses
    processed_messages.append(formatted_text)
    
    # Kirim notifikasi ke pengguna
    user_id = update.effective_user.id
    await context.bot.send_message(
        chat_id=user_id,
        text=f"Pesan baru diterima dan diproses:\n{formatted_text}"
    )
def main() -> None:
    # Start the web server
    keep_alive()
    """Memulai bot."""
    # Buat aplikasi dan tambahkan handler
    application = Application.builder().token(TOKEN).build()

    # Tambahkan handler untuk command
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("getchannel", get_channel_id))
    application.add_handler(CommandHandler("monitor", monitor_channel))
    application.add_handler(CommandHandler("stop", stop_monitoring))
    application.add_handler(CommandHandler("list", list_messages))
    application.add_handler(CommandHandler("clear", clear_messages))
    
    # Handler untuk tombol
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Handler untuk pesan dari channel
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    
    # Handler untuk input channel ID
    application.add_handler(MessageHandler(
        filters.Regex(r'^channel: @\w+') & filters.ChatType.PRIVATE,
        lambda u, c: monitor_channel(u, c, u.message.text.split('@')[1])
    ))

    # Mulai polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)



if __name__ == "__main__":
    main()