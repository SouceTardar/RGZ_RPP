import asyncio
import logging
import os
import datetime
import requests
import psycopg2
from aiogram import Dispatcher, Bot, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BotCommand, BotCommandScopeDefault

# Подключение к базе данных

conn = psycopg2.connect(dbname="finance_bot", user="maxim_rgz_bot",
                        password="3005", host="127.0.0.1")
cursor = conn.cursor()


router = Router()

# Класс состояния для регистрации
class Registration(StatesGroup):
    waiting_for_login = State()

# Класс состояния для добавления операции
class AddOperation(StatesGroup):
    waiting_for_operation_type = State()
    waiting_for_amount = State()
    waiting_for_date = State()
    waiting_for_category = State()

# Команда /reg
@router.message(Command("reg"))
async def cmd_reg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    # Проверяем, зарегистрирован ли пользователь
    cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
    if cursor.fetchone():
        await message.answer("Вы уже зарегистрированы!")
        return

    # Если не зарегистрирован, переводим в состояние ожидания логина
    await state.set_state(Registration.waiting_for_login)
    await message.answer("Введите ваш логин:")

# Обработчик состояния ожидания логина
@router.message(Registration.waiting_for_login)
async def process_login(message: Message, state: FSMContext):
    login = message.text
    user_id = message.from_user.id
    registration_date = datetime.datetime.now()

    # Сохраняем логин и дату регистрации в базу данных
    cursor.execute("INSERT INTO users (user_id, login, data) VALUES (%s, %s, %s)",
                   (user_id, login, registration_date))
    conn.commit()

    await state.clear()

    await message.answer(f"Вы успешно зарегистрированы с логином: {login}")


# Команда /add_operation
@router.message(Command("add_operation"))
async def cmd_add_operation(message: Message, state: FSMContext):
    user_id = message.from_user.id
    # Проверяем, зарегистрирован ли пользователь
    cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        await message.answer("Вы не зарегистрированы! Используйте команду /reg для регистрации.")
        return

    # Предлагаем выбрать тип операции
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="РАСХОД"), KeyboardButton(text="ДОХОД")]
    ], resize_keyboard=True)
    await message.answer("Выберите тип операции:", reply_markup=keyboard)
    await state.set_state(AddOperation.waiting_for_operation_type)

# Обработчик выбора типа операции
@router.message(AddOperation.waiting_for_operation_type)
async def process_operation_type(message: Message, state: FSMContext):
    operation_type = message.text

    if operation_type not in ("РАСХОД", "ДОХОД"):
        await message.answer("Неверный тип операции. Выберите РАСХОД или ДОХОД.")
        return

    await state.update_data(operation_type=operation_type)
    await message.answer("Введите сумму операции в рублях:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AddOperation.waiting_for_amount)

# Обработчик ввода суммы операции
@router.message(AddOperation.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Неверный формат суммы. Введите число.")
        return

    await state.update_data(amount=amount)
    await message.answer("Укажите дату операции в формате YYYY-MM-DD:")
    await state.set_state(AddOperation.waiting_for_date)

# Обработчик ввода даты операции
@router.message(AddOperation.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    try:
        operation_date = datetime.datetime.strptime(message.text, "%Y-%m-%d").date()
    except ValueError:
        await message.answer("Неверный формат даты. Используйте YYYY-MM-DD.")
        return

    user_data = await state.get_data()
    operation_type = user_data['operation_type']
    amount = user_data['amount']
    user_id = message.from_user.id

    # Сохраняем операцию в базу данных
    cursor.execute("INSERT INTO operations (data, sum, chat_id, type_operation) VALUES (%s, %s, %s, %s)",
                   (operation_date, amount, user_id, operation_type))
    conn.commit()

    # Завершаем состояние добавления операции
    await state.clear()
    await message.answer("Операция успешно добавлена!")

async def main():
    bot_token = os.getenv('TOKEN')
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(router)


    await dp.start_polling(bot)

class ViewOperations(StatesGroup):
    waiting_for_currency = State()

# Команда /operations
@router.message(Command("operations"))
async def operations(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # Проверяем, зарегистрирован ли пользователь
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        await message.answer('Вы не зарегистрированы! Для регистрации используйте команду /reg')
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="RUB"), KeyboardButton(text="EUR"), KeyboardButton(text="USD")],
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите валюту:", reply_markup=keyboard)
    await state.set_state(ViewOperations.waiting_for_currency)

@router.message(ViewOperations.waiting_for_currency)
async def process_currency(message: Message, state: FSMContext):
    currency = message.text.upper()

    if currency not in ("RUB", "EUR", "USD"):
        await message.answer("Пожалуйста, выберите валюту, используя кнопки.")
        return

    user_id = message.from_user.id
    cursor.execute("SELECT * FROM operations WHERE chat_id = %s", (user_id,))
    operations = cursor.fetchall()

    if not operations:
        await message.answer("У вас пока нет операций.")
        return

    output = ""
    if currency == "RUB":
        for operation in operations:
            output += f"Дата: {operation[1]}, Тип: {operation[4]}, Сумма: {operation[2]} RUB\n"
    else:
        try:
            response = requests.get(f"http://127.0.0.1:5001/rate?currency={currency}")
            response.raise_for_status()  # Проверяем на HTTP ошибки

            rate = response.json()["rate"]
            for operation in operations:
                # Преобразуем Decimal в float
                converted_amount = float(operation[2]) / rate
                output += f"Дата: {operation[1]}, Тип: {operation[4]}, Сумма: {converted_amount:.2f} {currency}\n"
        except requests.exceptions.RequestException as e:
            await message.answer(f"Ошибка при получении курса валют: {e}")
            await state.clear()
            return


class ViewOperations(StatesGroup):
    waiting_for_category = State()
    
# Доработка команды /operations
@router.message(ViewOperations.waiting_for_category)
async def process_category(message: Message, state: FSMContext):
    category_name = message.text

    # Проверяем, что категория выбрана верно
    user_id = message.from_user.id
    cursor.execute("SELECT 1 FROM categories WHERE name = %s AND chat_id = %s", (category_name, user_id))
    if not cursor.fetchone():
        await message.answer(f"Категория '{category_name}' не найдена. Повторите попытку.")
        return

    # Получаем id категории
    cursor.execute("SELECT id FROM categories WHERE name = %s AND chat_id = %s", (category_name, user_id))
    category_id = cursor.fetchone()[0]

    # Фильтруем операции по валюте, категории и chat_id
    currency = state.get_data()['currency']
    cursor.execute("SELECT * FROM operations WHERE chat_id = %s AND currency = %s AND category_id = %s", (user_id, currency, category_id))
    operations = cursor.fetchall()

    # Обрабатываем операции
    if not operations:
        await message.answer("У вас пока нет операций в этой валюте и категории.")
        await state.clear()
        return

    output = ""
    for operation in operations:
        output += f"Дата: {operation[1]}, Тип: {operation[4]}, Сумма: {operation[2]} {currency}\n"


    await message.answer(output)
    await state.clear()

class AddCategory(StatesGroup):
    waiting_for_category_name = State()

# вариант 12: Команда /add_category
@router.message(Command("add_category"))
async def add_category(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # Проверяем, зарегистрирован ли пользователь
    cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        await message.answer("Вы не зарегистрированы! Используйте команду /reg для регистрации.")
        return

    # Предлагаем ввести название категории
    await message.answer("Введите название категории:")
    await state.set_state(AddCategory.waiting_for_category_name)

class AddCategory(StatesGroup):
    waiting_for_category_name = State()

@router.message(AddCategory.waiting_for_category_name)
async def process_category_name(message: Message, state: FSMContext):
    category_name = message.text.strip()

    # Проверяем, что название категории не пустое
    if not category_name:
        await message.answer("Название категории не может быть пустым. Повторите попытку.")
        return

    # Сохраняем название категории и chat_id пользователя
    cursor.execute("INSERT INTO categories (name, chat_id) VALUES (%s, %s)", (category_name, message.from_user.id))
    conn.commit()

    await message.answer(f"Категория '{category_name}' успешно добавлена!")
    await state.clear()

async def main():
    bot_token = os.getenv('TOKEN')
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.set_my_commands([
        BotCommand(command='reg', description='Регистрация'),
        BotCommand(command='add_operation', description='Добавить операцию'),
        BotCommand(command='operations', description='Просмотреть операции'),
        BotCommand(command='add_category', description='Посмотреть категории')
    ], scope=BotCommandScopeDefault())

    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

cursor.close()
conn.close()