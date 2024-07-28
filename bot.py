from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.utils import executor
from db import session, User, Transaction
import logging
from aiogram.utils.exceptions import MessageNotModified
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import pandas as pd
import urllib.parse
import sqlite3, os, dotenv


dotenv.load_dotenv()

API_TOKEN = os.environ.get('API_TOKEN')
PAYMENT_PROVIDER_TOKEN = os.environ.get('PAYMENT_PROVIDER_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID'))
BOT_USERNAME = os.environ.get('BOT_USERNAME')
TARGET_CHAT_ID = int(os.environ.get('TARGET_CHAT_ID'))

bot = Bot(token=API_TOKEN)

class BotStates(StatesGroup):
    SEND_PAYNAMENT_METHOD = State()

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

logging.basicConfig(level=logging.INFO)

def get_menu_kb(referral_link=None, invite_link=None):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("Як заробляє партнер каналу", callback_data='how_to_earn'))
    if not referral_link:
        keyboard.add(InlineKeyboardButton("Підпсиатися на канал", url=invite_link))
        keyboard.add(InlineKeyboardButton("Провірити підписку", callback_data='check_subscription'))
    elif referral_link:
        keyboard.add(InlineKeyboardButton("Перевірити баланс", callback_data='update_balance'))
        
        
        text = f"""
Привіт, підпишіться на Pyramida media та станьте партнером каналу. 
Запрошуйте ваших знайомих та заробляйте разом! 
Детальніше за посиланням:
{referral_link}
        """
        encoded_text = urllib.parse.quote(text)
        keyboard.add(InlineKeyboardButton("Запросити знайомих приєднатись", url=f"https://t.me/share/url?url={encoded_text}"))
        keyboard.add(InlineKeyboardButton("Вивід коштів", callback_data='withdraw_funds'))
    return keyboard

def get_or_create_user(telegram_id: int, username: str = None) -> User:
    user = session.query(User).filter_by(id=telegram_id).first()
    if not user:
        user = User(id=telegram_id, username=username)
        session.add(user)
        session.commit()
    return user

async def add_referral(referrer_id: int, new_user_id: int):
    new_user = get_or_create_user(new_user_id)
    new_user.referral_link = f'https://t.me/{BOT_USERNAME}?start={new_user_id}'
    session.commit()
    if referrer_id:
        referrer = get_or_create_user(referrer_id)
        if referrer_id != new_user_id:
            await distribute_bonus(referrer)

async def distribute_bonus(user: User, level=1):
    if level > 5 or not user:
        return
    user.balance += 5.0
    user.referrer_count += 1
    session.commit()

    transaction = Transaction(user_id = user.id, description = 'Начислення коштів за рефрала', amount = 5.0)
    session.add(transaction)
    session.commit()
    await bot.send_message(user.id, 'Вам було нараховано <strong>5.0 UAH</strong> за реферала', parse_mode=types.ParseMode.HTML)
    if user.referrer:
        await distribute_bonus(user.referrer, level + 1)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    ref_start = message.text.split(" ")
    ref_id = int(ref_start[1]) if len(ref_start) == 2 else None
    user = get_or_create_user(message.from_id, message.from_user.mention)
    if not user.chat_link:
        invite = await bot.create_chat_invite_link(TARGET_CHAT_ID, member_limit=1)
        user.chat_link = invite.invite_link
        session.commit()
    if ref_id:
        if ref_id != message.from_id:
            user.referrer_id = ref_id
            session.commit()

    text = f"""
Це ваш особистий кабінет
Тут ви можете стати партнером та отримувати бонуси


Ваш баланс: <strong>UAH {user.balance:.2f} (бали нараховуються за запрошених знайомих, які підписались на канали (за кожний канал 5 балів). </strong>
Кількість Ваших рефералів: <strong>{user.referrer_count}</strong>
Ваше реферальне посилання:
{user.referral_link}
""" if user.referral_link else """
Привіт, підпишіться на Pyramida media та станьте партнером каналу. 
Запрошуйте ваших знайомих та заробляйте разом! 
"""
    await message.answer(
        text,
        reply_markup=get_menu_kb(user.referral_link, user.chat_link),
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data in ['check_subscription',  'how_to_earn', 'become_partner', 'withdraw_funds', 'update_balance'])
async def process_callback(callback_query: types.CallbackQuery, state: FSMContext):
    message = callback_query.message
    if callback_query.data == 'check_subscription':
        await message.delete()
        user = get_or_create_user(callback_query.from_user.id)
        if await bot.get_chat_member(TARGET_CHAT_ID, callback_query.from_user.id):
            referrer_id = user.referrer_id
            await add_referral(referrer_id, callback_query.from_user.id)
            text = f"""
Це ваш особистий кабінет
Тут ви можете стати партнером та отримувати бонуси


Ваш баланс: <strong>UAH {user.balance:.2f} (бали нараховуються за запрошених знайомих, які підписались на канали (за кожний канал 5 балів). </strong>
Кількість Ваших рефералів: <strong>{user.referrer_count}</strong>
Ваше реферальне посилання:
{user.referral_link}
    """     
            await message.answer(
                text,
                reply_markup=get_menu_kb(user.referral_link),
                parse_mode=types.ParseMode.HTML
            )
        else:
            text = f"""
Ви не підписані, підпишіться на Pyramida media та станьте партнером каналу. 
Запрошуйте ваших знайомих та заробляйте разом! 
        """
            await message.answer(text, reply_markup=get_menu_kb(invite_link=user.chat_link))
    elif callback_query.data == 'become_partner':
        await message.delete()
        user = get_or_create_user(callback_query.from_user.id)
        text = """
Підпишіться на Pyramida media та станьте партнером каналу. 
Запрошуйте ваших знайомих та заробляйте разом! 
"""
        await message.answer(
            text,
            reply_markup=get_menu_kb(invite_link=user.chat_link),
            parse_mode=types.ParseMode.HTML
        ) 
    elif callback_query.data == 'how_to_earn':
        await message.delete()
        user = get_or_create_user(callback_query.from_user.id)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(types.InlineKeyboardButton('Стати партнером' if not user.referral_link else 'Повернутися', callback_data='become_partner' if not user.referral_link else 'go_to_dashboard'))
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id, """Схема заробітку: 
Як заробляє партнер каналу відправляє на повідомлення де розписана схема заробітку і є кнопка Стати партнером.
                               
1)Після повернення в особистий кабінет користувач бачить свій баланс, кількість рефералів та унікальне посилання для запрошення.

2)Коли хтось з його контактів, або контактів його контактів сплачує 40 грн, бот відправляє повідомлення: "У вас з'явився новий реферал", і користувач отримує 5 бали за кожного нового учасника.

3)Всі учасники, включаючи реферів та рефералів до 8 рівня, отримують по 5 бали за людину, яка увійде в канал по запрошеню (реферала).
""", reply_markup=keyboard)
    elif callback_query.data == 'withdraw_funds':
        await message.delete()
        user = get_or_create_user(callback_query.from_user.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton('Повернутися', callback_data='go_to_dashboard'))
        if user.balance >= 40.00:
            await bot.send_message(callback_query.from_user.id, "Будь ласка, надішліть свої реквізити для виводу коштів.", reply_markup=keyboard)
            await state.set_state(BotStates.SEND_PAYNAMENT_METHOD)
        else:
            await bot.send_message(callback_query.from_user.id, "Ваш баланс менше 40 грн. Ви не можете вивести кошти.", reply_markup=keyboard)
    elif callback_query.data == 'update_balance':
        user = get_or_create_user(callback_query.from_user.id)
        try:
            await callback_query.message.edit_text(f"""
Це ваш особистий кабінет
Тут ви можете стати партнером та отримувати бонуси


Ваш баланс: <strong>UAH {user.balance:.2f} (бали нараховуються за запрошених знайомих, які підписались на канали (за кожний канал 5 балів). </strong>
Кількість Ваших рефералів: <strong>{user.referrer_count}</strong>
Ваше реферальне посилання:
{user.referral_link}
            """, reply_markup=get_menu_kb(user.referral_link), parse_mode=types.ParseMode.HTML)
        except MessageNotModified:
            pass
        await callback_query.answer('Баланс оновлено.', show_alert=True)


@dp.message_handler(content_types=types.ContentType.TEXT, state=BotStates.SEND_PAYNAMENT_METHOD)
async def handle_withdrawal_details(message: types.Message, state: FSMContext):
    await message.delete()
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('Повернутися', callback_data='become_partner'))
    user = get_or_create_user(message.from_user.id)
    if user.balance >= 40.00:
        transaction = Transaction(user_id = message.from_id, description = 'Вивід коштів', amount = -40.00)
        session.add(transaction)
        session.commit()
        
        withdrawal_request = f"Користувач <strong>{message.from_user.mention}</strong> запросив вивід коштів.\nБаланс: {user.balance}\nРеквізити: {message.text}"
        user.balance = 0
        session.commit()
        
        await bot.send_message(ADMIN_ID, withdrawal_request, parse_mode=types.ParseMode.HTML)
        await bot.send_message(message.from_user.id, "Ваш запит на вивід коштів було відправлено адміністратору.", reply_markup=keyboard)
    else:
        await bot.send_message(message.from_user.id, "Ваш баланс менше 40 грн. Ви не можете вивести кошти.", reply_markup=keyboard)
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'go_to_dashboard')
async def go_to_dashboard(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    user = get_or_create_user(callback_query.from_user.id)
    await bot.send_message(
        callback_query.from_user.id,
f"""
Це ваш особистий кабінет
Тут ви можете стати партнером та отримувати бонуси


Ваш баланс: <strong>UAH {user.balance:.2f} (бали нараховуються за запрошених знайомих, які підписались на канали (за кожний канал 5 балів). </strong>
Кількість Ваших рефералів: <strong>{user.referrer_count}</strong>
Ваше реферальне посилання:
{user.referral_link}
""" if user.referral_link else """
Підпишіться на Pyramida media та станьте партнером каналу. 
Запрошуйте ваших знайомих та заробляйте разом! 
""",
        reply_markup=get_menu_kb(user.referral_link, user.chat_link),
        parse_mode=types.ParseMode.HTML
    )

@dp.chat_join_request_handler()
async def join_request_handler(request: types.ChatJoinRequest):
    if request.chat.id == TARGET_CHAT_ID:
        user = get_or_create_user(request.from_user.id)
        if user:
            if user.referral_link:
                return await request.approve()
        await request.decline()

@dp.message_handler(commands=['stats'])
async def admin_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        total_users = session.query(User).count()
        total_referrals = session.query(User).filter(User.referrer_id.isnot(None)).count()
        active_referrals = session.query(User).filter(User.referral_link.isnot(None)).count()
        inactive_referrals = session.query(User).filter(User.referral_link.is_(None)).count()

        stats_text = (
            f"Загальна кількість користувачів: <strong>{total_users}</strong>\n"
            f"Загальна кількість рефералів: <strong>{total_referrals}</strong>\n"
            f"Користувачів з активованою реферальною програмою: <strong>{active_referrals}</strong>\n"
            f"Користувачів з неактивованою реферальною програмою: <strong>{inactive_referrals}</strong>"
        )

        await bot.send_message(message.from_user.id, stats_text, parse_mode = types.ParseMode.HTML)
    else:
        await bot.send_message(message.from_user.id, "У вас немає прав для виконання цієї команди.")

def export_db_to_excel(db_path, excel_path):
    conn = sqlite3.connect(db_path)
    query = """
    SELECT u.id, u.username, u.balance, u.referrer_count, u.referral_link, u.chat_link, 
           r.username AS referrer_username
    FROM users u
    LEFT JOIN users r ON u.referrer_id = r.id
    """
    users_df = pd.read_sql_query(query, conn)
    transactions_df = pd.read_sql_query("SELECT * FROM transactions", conn)
    
    conn.close()
    with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
        users_df.to_excel(writer, sheet_name='Users', index=False)
        transactions_df.to_excel(writer, sheet_name='Transactions', index=False)


@dp.message_handler(commands=['export_db'])
async def handle_export_db(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        db_path = 'referral_system.db'
        excel_path = 'referral_system.xlsx'
        export_db_to_excel(db_path, excel_path)
        file = types.InputFile(excel_path)
        await bot.send_document(message.from_user.id, file)
    else:
        await message.answer("У вас немає прав для виконання цієї команди.")

@dp.message_handler(commands=['set_chat_id'])
async def set_chat_id(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        try:
            chat_id = int(message.get_args())
            global TARGET_CHAT_ID
            TARGET_CHAT_ID = chat_id
            await message.answer(f"TARGET_CHAT_ID has been set to {chat_id}.")
        except ValueError:
            await message.answer("Ви повинні ввести айді.")
    else:
        await message.answer("8У вас немає прав для виконання цієї команди.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
