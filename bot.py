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
    keyboard.add(InlineKeyboardButton("💲 Как зарабатывает подписчик", callback_data='how_to_earn'))
    if not referral_link:
        keyboard.add(InlineKeyboardButton("✔️ Подписаться на канал", url=invite_link))
        keyboard.add(InlineKeyboardButton("🛃 Проверить подписку", callback_data='check_subscription'))
    elif referral_link:
        keyboard.add(InlineKeyboardButton("💰 Проверить/обновить баланс", callback_data='update_balance'))
        
        
        text = f"""
👋 Привет, подпишись на 🍿Пуфик ☁️ Кино и стань партнером канала!
🔗 Приглашайте своих знакомых и получайте за это 💲 деньги! 
📋 Детальнее по ссылке:
{referral_link}
        """
        encoded_text = urllib.parse.quote(text)
        keyboard.add(InlineKeyboardButton("🔗 Пригласить знакомых", url=f"https://t.me/share/url?url={encoded_text}"))
        keyboard.add(InlineKeyboardButton("💲 Выплата денег", callback_data='withdraw_funds'))
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
    user.balance += 0.01
    user.referrer_count += 1
    session.commit()

    transaction = Transaction(user_id = user.id, description = '💲 Начисление средств за подписчика', amount = 0.01)
    session.add(transaction)
    session.commit()
    await bot.send_message(user.id, '💲 Вам было начислено <strong>0.01 USD</strong> за подписчика', parse_mode=types.ParseMode.HTML)
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
💼 Это ваш личный кабинет
🤝 Тут Вы можете стать подписчиком канала и зарабатывать 💲 деньги, приглашая 🔗 друзей и знакомых.


💰 Ваш баланс: <strong>UAH {user.balance:.2f}</strong>
👫 Количество Ваших подписчиков: <strong>{user.referrer_count}</strong>
🔗 Ваша ссылка для приглашения знакомых:
{user.referral_link}
""" if user.referral_link else """
👋 Привет, подпишись на 🍿Пуфик ☁️ Кино и стань партнером канала! 
🔗 Приглашайте своих 👫 знакомых и получайте за это 💲 деньги! 
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
        text = f"""
❌ Вы не подписаны на 🍿Пуфик ☁️ Кино, подпишитесь на 🍿Пуфик ☁️ Кино и зарабатывайте 💲. 
🔗 Приглашайте своих 👫 знакомых и зарабатывайте 💲 вместе! 
"""
        try:
            member = await bot.get_chat_member(TARGET_CHAT_ID, callback_query.from_user.id)
            if member.status != "left" and member.status != "kicked" and member.status != "banned":
                referrer_id = user.referrer_id
                await add_referral(referrer_id, callback_query.from_user.id)
                text = f"""
    💼 Это ваш личный кабинет
    🤝 Тут Вы можете стать подписчиком канала и зарабатывать 💲 деньги, приглашая 🔗 друзей и знакомых.


    💰 Ваш баланс: <strong>USD {user.balance:.2f}</strong>
    👫 Количество Ваших подписчиков: <strong>{user.referrer_count}</strong>
    🔗 Ваша ссылка для приглашения знакомых:
    {user.referral_link}
        """     
                await message.answer(
                    text,
                    reply_markup=get_menu_kb(user.referral_link),
                    parse_mode=types.ParseMode.HTML
                )
            else:
                await message.answer(text, reply_markup=get_menu_kb(invite_link=user.chat_link))
        except :
            await message.answer(text, reply_markup=get_menu_kb(invite_link=user.chat_link))
    elif callback_query.data == 'become_partner':
        await message.delete()
        user = get_or_create_user(callback_query.from_user.id)
        text = """
✔️ Подпишитесь на 🍿Пуфик ☁️ Кино и зарабатывайте 💲. 
🔗 Приглашайте своих 👫 знакомых и зарабатывайте 💲 вместе! 
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
        keyboard.add(types.InlineKeyboardButton('🤝 Стать партнером' if not user.referral_link else '◀️ Вернуться', callback_data='become_partner' if not user.referral_link else 'go_to_dashboard'))
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id, """Как 💲 заработать: 
1. Нажимаем "Пригласить знакомых" ✉️ Отправляем сообщение с приглашением подписаться на канал 🍿Пуфик ☁️ Кино.
                               
2. После того, как Вы станете партнером 🍿Пуфик ☁️ Кино, в Вашем личном кабинете будет Ваш 💰 баланс, количество 👫 подписчиков, которые подписались на канал благодаря Вам и Ваша уникальная 🔗 ссылка для приглашения знакомых.

3. Когда тот, кого Вы пригласили своей 🔗 ссылкой, подпишется на канал, у Вас в личном кабинете добавится 👫 подписчик и Вам будет начислено 💰 0,01 USD.

4. Все 👫 подписчики, включая 🔗 приглашенных до 5 уровня, получают по 0,01 USD за КАЖДОГО, кто подпишеться на канал 🍿Пуфик ☁️ Кино.

Таким образом, Вы получите 0,01 USD за каждого, кто подпишется по вашей 🔗 ссылке или 🔗 ссылке Ваших 👫 подписчиков до 5 уровня.
   
Вместе с ростом количества подписчиков 🍿Пуфик ☁️ Кино будет расти и ваш 💰 баланс!

*Вывод денег от 10 USD.
""", reply_markup=keyboard)
    elif callback_query.data == 'withdraw_funds':
        await message.delete()
        user = get_or_create_user(callback_query.from_user.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton('◀️ Вернуться', callback_data='go_to_dashboard'))
        if user.balance >= 10.00:
            await bot.send_message(callback_query.from_user.id, "💳 Напишите свои реквизиты для выплаты денег", reply_markup=keyboard)
            await state.set_state(BotStates.SEND_PAYNAMENT_METHOD)
        else:
            await bot.send_message(callback_query.from_user.id, "💰 Ваш баланс меньше 10 USD. Вы не можете вывести деньги.", reply_markup=keyboard)
    elif callback_query.data == 'update_balance':
        user = get_or_create_user(callback_query.from_user.id)
        try:
            await callback_query.message.edit_text(f"""
💼 Это ваш личный кабинет
🤝 Тут Вы можете стать подписчиком канала и зарабатывать 💲 деньги, приглашая 🔗 друзей и знакомых.


💰 Ваш баланс: <strong>UAH {user.balance:.2f}</strong>
👫 Количество Ваших подписчиков: <strong>{user.referrer_count}</strong>
🔗 Ваша ссылка для приглашения знакомых:
{user.referral_link}
            """, reply_markup=get_menu_kb(user.referral_link), parse_mode=types.ParseMode.HTML)
        except MessageNotModified:
            pass
        await callback_query.answer('💰 Баланс обновлен', show_alert=True)


@dp.message_handler(content_types=types.ContentType.TEXT, state=BotStates.SEND_PAYNAMENT_METHOD)
async def handle_withdrawal_details(message: types.Message, state: FSMContext):
    await message.delete()
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('◀️ Вернуться', callback_data='become_partner'))
    user = get_or_create_user(message.from_user.id)
    if user.balance >= 10.00:
        transaction = Transaction(user_id = message.from_id, description = '💲 Выплата денег', amount = user.balance)
        session.add(transaction)
        session.commit()
        
        withdrawal_request = f"Пользователь <strong>{message.from_user.mention}</strong> запросил вывод средств.\nБаланс: {user.balance}\nРеквизиты: {message.text}"
        user.balance = 0
        session.commit()
        
        await bot.send_message(ADMIN_ID, withdrawal_request, parse_mode=types.ParseMode.HTML)
        await bot.send_message(message.from_user.id, "✉️ Ваш запрос на выплату денег отправлен администратору.", reply_markup=keyboard)
    else:
        await bot.send_message(message.from_user.id, "💰 Ваш баланс меньше 10 USD. Вы не можете вывести деньги.", reply_markup=keyboard)
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'go_to_dashboard')
async def go_to_dashboard(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    user = get_or_create_user(callback_query.from_user.id)
    await bot.send_message(
        callback_query.from_user.id,
f"""
💼 Это ваш личный кабинет
🤝 Тут Вы можете стать подписчиком канала и зарабатывать 💲 деньги, приглашая 🔗 друзей и знакомых.


💰 Ваш баланс: <strong>UAH {user.balance:.2f}</strong>
👫 Количество Ваших подписчиков: <strong>{user.referrer_count}</strong>
🔗 Ваша ссылка для приглашения знакомых:
{user.referral_link}
""" if user.referral_link else """
✔️ Подпишитесь на 🍿Пуфик ☁️ Кино и зарабатывайте 💲. 
🔗 Приглашайте своих 👫 знакомых и зарабатывайте 💲 вместе! 
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
            f"Всего пользователей: <strong>{total_users}</strong>\n"
            f"Всего рефералов: <strong>{total_referrals}</strong>\n"
            f"Пользователей с активной реферальной программой: <strong>{active_referrals}</strong>\n"
            f"Пользователей с неактивной реферальной программой: <strong>{inactive_referrals}</strong>"
        )

        await bot.send_message(message.from_user.id, stats_text, parse_mode = types.ParseMode.HTML)
    else:
        await bot.send_message(message.from_user.id, "👮 У вас нет прав для выполнения данной команды.")

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
        await message.answer("👮 У вас нет прав для выполнения данной команды.")

@dp.message_handler(commands=['set_chat_id'])
async def set_chat_id(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        try:
            chat_id = int(message.get_args())
            global TARGET_CHAT_ID
            TARGET_CHAT_ID = chat_id
            await message.answer(f"TARGET_CHAT_ID has been set to {chat_id}.")
        except ValueError:
            await message.answer("Вы должны ввести id")
    else:
        await message.answer("👮 У вас нет прав для выполнения данной команды.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
