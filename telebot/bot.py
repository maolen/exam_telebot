from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor

from config import TOKEN
from epub_writer import package_fanfic

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message):
    await message.answer("""
Привет! Этот бот скачивает работы с fanfiction.net в формате epub. 
Отправьте адрес произведения, чтобы скачать.
""")


@dp.message_handler()
async def process_download(message: types.Message):
    try:
        user_id = message.from_user.id
        await message.answer("Собираю файл...")
        filename = await package_fanfic(message.text)
        book = open(filename, 'rb')
        await bot.send_chat_action(user_id, types.ChatActions.UPLOAD_DOCUMENT)
        await bot.send_document(user_id, book)
    except FileNotFoundError as e:
        await message.answer(e.args[0])
    except Exception as e:
        await message.answer(e.args[0])


if __name__ == '__main__':
    executor.start_polling(dp)
