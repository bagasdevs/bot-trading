import logging
from typing import List, Optional
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from keep_alive import keep_alive
import os
from dotenv import load_dotenv

# Configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

class MessageStore:
    def __init__(self):
        self.message_database = defaultdict(int)
        self.processed_messages: List[str] = []

    def add_message(self, text: str) -> int:
        self.message_database[text] += 1
        self.processed_messages.append(text)
        return self.message_database[text]

    def clear(self) -> None:
        self.message_database.clear()
        self.processed_messages.clear()

    def is_empty(self) -> bool:
        return len(self.processed_messages) == 0

    def get_messages_list(self) -> str:
        if self.is_empty():
            return 'Tidak ada pesan yang telah diproses.'
        return "Daftar pesan yang telah diproses:\n\n" + "\n".join(
            f"{idx}. {msg}" for idx, msg in enumerate(self.processed_messages, 1)
        )

class MessageExtractor:
    @staticmethod
    def extract_text(text: str) -> str:
        """Extract lines starting with 'Ca:' or 'User:'"""
        lines = [line.strip() for line in text.split('\n')
                if line.startswith(('Ca:', 'User:'))]
        return '\n'.join(lines) if lines else text

class TelegramBot:
    def __init__(self):
        self.message_store = MessageStore()
        self.extractor = MessageExtractor()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        keyboard = [
            [InlineKeyboardButton("🔍 Monitor Channel", callback_data='monitor'),
             InlineKeyboardButton("⏹️ Stop Monitor", callback_data='stop')],
            [InlineKeyboardButton("📋 List Messages", callback_data='list'),
             InlineKeyboardButton("🗑️ Clear Messages", callback_data='clear')],
            [InlineKeyboardButton("❓ Help", callback_data='help')]
        ]
        await update.message.reply_text(
            'Hai! Saya adalah bot yang mengumpulkan dan mengorganisir pesan dari channel.\n'
            'Silakan pilih menu di bawah ini:',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        handlers = {
            'monitor': lambda u, c: query.message.reply_text(
                'Silakan kirim channel ID yang ingin dipantau dengan format:\n'
                'channel: @channelname'
            ),
            'stop': self.stop_monitoring,
            'list': self.list_messages,
            'clear': self.clear_messages,
            'help': self.help_command
        }

        if handler := handlers.get(query.data):
            await handler(update, context)

    async def handle_channel_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_valid_channel_post(update, context):
            return

        original_text = update.channel_post.text
        if not original_text:
            return

        extracted_text = self.extractor.extract_text(original_text)
        if not extracted_text.strip():
            return

        count = self.message_store.add_message(extracted_text)
        formatted_text = f"{extracted_text}\n(Duplikat #{count})" if count > 1 else extracted_text

        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"Pesan baru diterima dan diproses:\n{formatted_text}"
        )

    def _is_valid_channel_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        return ('monitored_channel' in context.user_data and
                str(update.channel_post.chat_id) == context.user_data['monitored_channel'])

    async def monitor_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                            channel_id: Optional[str] = None) -> None:
        if not channel_id:
            return

        channel_id = f"@{channel_id}"
        context.user_data['monitored_channel'] = channel_id
        await update.message.reply_text(
            f'Mulai memantau channel: {channel_id}\n'
            'Mengekstrak baris Ca: dan User: secara otomatis'
        )

    async def stop_monitoring(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if 'monitored_channel' in context.user_data:
            channel = context.user_data.pop('monitored_channel')
            await update.message.reply_text(f'Berhenti memantau channel: {channel}')
        else:
            await update.message.reply_text('Tidak ada channel yang sedang dipantau.')

    async def list_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.callback_query.message if update.callback_query else update.message
        await message.reply_text(self.message_store.get_messages_list())

    async def clear_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.message_store.clear()
        await update.message.reply_text('Semua pesan telah dihapus.')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        help_text = (
            'Daftar perintah:\n'
            '/start - Memulai bot\n'
            '/help - Menampilkan pesan bantuan\n'
            '/getchannel <username> - Mendapatkan channel ID dari username channel\n'
            '/monitor <channel_id> - Mulai memantau channel dengan ID tertentu\n'
            '/stop - Berhenti memantau channel\n'
            '/list - Menampilkan daftar pesan yang telah diproses\n'
            '/clear - Menghapus semua pesan yang telah diproses'
        )
        await update.message.reply_text(help_text)

    def run(self) -> None:
        keep_alive()
        app = Application.builder().token(TOKEN).build()

        # Command handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("getchannel", self.get_channel_id))
        app.add_handler(CommandHandler("monitor", self.monitor_channel))
        app.add_handler(CommandHandler("stop", self.stop_monitoring))
        app.add_handler(CommandHandler("list", self.list_messages))
        app.add_handler(CommandHandler("clear", self.clear_messages))

        # Button handler
        app.add_handler(CallbackQueryHandler(self.button_handler))

        # Channel post handler
        app.add_handler(MessageHandler(filters.ChatType.CHANNEL, self.handle_channel_post))

        # Channel ID input handler
        app.add_handler(MessageHandler(
            filters.Regex(r'^channel: @\w+') & filters.ChatType.PRIVATE,
            lambda u, c: self.monitor_channel(u, c, u.message.text.split('@')[1])
        ))

        app.run_polling(allowed_updates=Update.ALL_TYPES)

    async def get_channel_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text(
                'Format: /getchannel <channel_username>\n'
                'Contoh: /getchannel myChannel'
            )
            return

        channel_username = context.args[0].replace('@', '')
        if '/' in channel_username:
            channel_username = channel_username.split('/')[-1]

        await update.message.reply_text(
            f'Channel ID untuk {channel_username} adalah:\n@{channel_username}'
        )

if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()