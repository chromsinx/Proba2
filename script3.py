import asyncio
from telethon import TelegramClient, events
from config import DESTINATION, STOP_WORDS_DESTINATION, API_ID, API_HASH, SESSION, CHATS, KEY_WORDS, STOP_WORDS
from datetime import datetime, timedelta
from rapidfuzz import fuzz  # Используем rapidfuzz для повышения производительности
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

# Инициализация клиента Telethon для работы с личным аккаунтом
client = TelegramClient(SESSION, API_ID, API_HASH)

# Хранилище сообщений с метками времени для фильтрации (24 часа хранения)
message_store = {}

# Период фильтрации сообщений (24 часа)
FILTER_DURATION = timedelta(days=1)

# Порог схожести сообщений для фильтрации (90%)
SIMILARITY_THRESHOLD = 90

# Оптимизация: создаем множество стоп-слов в нижнем регистре один раз
STOP_WORDS_SET = {word.lower() for word in STOP_WORDS}

# Оптимизация: создаем множество ключевых слов в нижнем регистре один раз
KEY_WORDS_SET = {word.lower() for word in KEY_WORDS}

def validate_config():
    """
    Проверка наличия всех обязательных конфигурационных переменных.
    Генерирует ошибку, если какая-либо переменная отсутствует или пуста.
    """
    required_globals = {
        'API_ID': API_ID,
        'API_HASH': API_HASH,
        'SESSION': SESSION,
        'DESTINATION': DESTINATION,
        'STOP_WORDS_DESTINATION': STOP_WORDS_DESTINATION,
        'CHATS': CHATS,
        'KEY_WORDS': KEY_WORDS,
        'STOP_WORDS': STOP_WORDS
    }
    for var_name, var_value in required_globals.items():
        if not var_value:
            raise ValueError(f"The required config variable '{var_name}' is not set or is empty")

def log_with_time(message):
    """ Логирование с добавлением отметки времени """
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"[{current_time}] {message}")

def is_similar(message_text):
    """
    Проверка схожести нового сообщения с уже существующими в хранилище.
    Если схожесть превышает порог SIMILARITY_THRESHOLD, то сообщение считается дубликатом.
    """
    for stored_message in message_store.keys():
        similarity = fuzz.ratio(stored_message, message_text)
        if similarity >= SIMILARITY_THRESHOLD:
            return True
    return False

def contains_stop_words(message_text):
    """
    Проверяет, содержит ли сообщение слова из стоп-листа.
    Возвращает True, если хотя бы одно слово из стоп-листа присутствует в тексте сообщения.
    """
    return any(stop_word in message_text.lower() for stop_word in STOP_WORDS_SET)

async def remove_old_messages():
    """
    Удаляет сообщения, которые старше FILTER_DURATION (24 часа), из хранилища.
    Это помогает поддерживать актуальность фильтрации дубликатов сообщений.
    """
    current_time = datetime.now()
    to_remove = [msg for msg, timestamp in message_store.items() if current_time - timestamp > FILTER_DURATION]
    
    for msg in to_remove:
        del message_store[msg]

@client.on(events.NewMessage(chats=CHATS))
async def new_message_handler(event):
    """
    Основной обработчик новых сообщений.
    Фильтрует сообщения по схожести, стоп-словам и ключевым словам.
    Пересылает сообщения в целевой чат, если они соответствуют всем условиям.
    """
    try:
        log_with_time(f'Получено новое сообщение из чата {event.chat_id}...')

        # Проверяем, есть ли текст в сообщении
        if not event.message.text:
            log_with_time("Сообщение без текста, пропускаем.")
            return  # Пропускаем сообщения без текста

        # Удаляем устаревшие сообщения из фильтра
        await remove_old_messages()

        # Проверка на наличие стоп-слов
        if contains_stop_words(event.message.text):
            await client.forward_messages(STOP_WORDS_DESTINATION, event.message)
            log_with_time("Сообщение содержит стоп-слова, переслано в канал для стоп-слов.")
            return  # Сообщение содержит запрещённые слова, игнорируем его

        # Проверка на схожесть с уже существующими сообщениями
        if is_similar(event.message.text):
            log_with_time("Сообщение похоже на уже существующее (>= 90% схожести), фильтруем...")
            return  # Сообщение похоже на уже отправленное, игнорируем его

        # Добавляем новое сообщение в хранилище с текущей меткой времени
        message_store[event.message.text] = datetime.now()

        # Проверка на ключевые слова
        if any(key_word in event.message.text.lower() for key_word in KEY_WORDS_SET):
            # Пересылка сообщения в целевой чат
            await client.forward_messages(DESTINATION, event.message)
            log_with_time(f"Сообщение переслано: {event.message.text}")
            await asyncio.sleep(2)  # 2-секундная задержка между пересылками сообщений
        else:
            log_with_time("Сообщение не содержит ключевых слов, не пересылаем.")

    except Exception as ex:
        # Обработка исключений с задержкой в 60 секунд для восстановления
        log_with_time(f'Ошибка при обработке сообщения: {ex}')
        await asyncio.sleep(60)

async def main():
    """
    Основная функция, запускающая клиента Telethon.
    Выполняется до тех пор, пока не будет завершено соединение.
    """
    async with client:
        log_with_time("Бот запущен...")
        await client.start()
        await client.run_until_disconnected()

# Запуск бота
if __name__ == "__main__":
    # Проверяем конфигурацию перед запуском
    validate_config()
    # Запускаем основную асинхронную функцию
    asyncio.run(main())
