import asyncio
import json
import os
from functools import lru_cache

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

TOKEN = os.getenv("TOKEN")
DATABASE_URI = os.getenv("DATABASE")
API_KEY = os.getenv("API_KEY")
NEWSAPI_URL = "https://newsapi.org/v2/everything"

with open("popular_cities.json", "r", encoding="utf-8") as f:
    POPULAR_CITIES = set(city.title() for city in json.load(f)["popular_cities"])

bot = Bot(token=TOKEN)
dp = Dispatcher()

engine = create_async_engine(
    DATABASE_URI,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"timeout": 10, "command_timeout": 10},
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Вибрати основне місто")],
        [KeyboardButton(text="Новини")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

Base = declarative_base()


class Info(Base):
    __tablename__ = "info"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False)
    city = Column(String, nullable=False)


class CityState(StatesGroup):
    set_main_city = State()
    news_city = State()


class NewsState(StatesGroup):
    option = State()


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@lru_cache(maxsize=128)
def valid_city(city: str):
    return city in POPULAR_CITIES


async def create_or_update_city(session: AsyncSession, user_id: int, city: str):
    try:
        result = await session.execute(
            select(Info).where(Info.user_id == user_id).limit(1)
        )
        info = result.scalar_one_or_none()

        if info:
            info.city = city
            await session.commit()
            return info

        new_info = Info(user_id=user_id, city=city)
        session.add(new_info)
        await session.commit()
        return new_info
    except Exception as e:
        await session.rollback()
        print(f"Помилка бази даних: {e}")
        raise


async def fetch_news(query: str, page_size: int = 5):
    params = {
        "q": query,
        "language": "uk",
        "sortBy": "publishedAt",
        "apiKey": API_KEY,
        "pageSize": page_size,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                NEWSAPI_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("articles", [])
                else:
                    return []
    except Exception as e:
        print(f"Помилка при запиті новин: {e}")
        return []


@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привіт! Я NewsBot. Доступні команди:\n/start\n/choosecity\n/news",
        reply_markup=main_kb,
    )


@dp.message(Command("choosecity"))
@dp.message(F.text.lower() == "вибрати основне місто")
async def choose_city_start(message: types.Message, state: FSMContext):
    await state.set_state(CityState.set_main_city)
    await message.answer(
        "Напишіть назву вашого основного міста:", reply_markup=ReplyKeyboardRemove()
    )


# Встановлення основного міста
@dp.message(CityState.set_main_city)
async def set_main_city(message: types.Message, state: FSMContext):
    city = message.text.strip().title()
    if not valid_city(city):
        await message.answer("Такого міста немає в базі. Спробуйте ще раз.")
        return

    try:
        async with AsyncSessionLocal() as session:
            await create_or_update_city(session, message.from_user.id, city)
        await message.answer(
            f"Місто '{city}' успішно встановлено!", reply_markup=main_kb
        )
    except Exception as e:
        await message.answer(
            f"Помилка при збереженні міста. Спробуйте ще раз. {str(e)}"
        )
    finally:
        await state.clear()


@dp.message(Command("news"))
@dp.message(F.text.lower() == "новини")
async def news_start(message: types.Message, state: FSMContext):
    await state.set_state(NewsState.option)

    user_city = None
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Info.city).where(Info.user_id == message.from_user.id).limit(1)
            )
            user_city = result.scalar_one_or_none()
    except Exception as e:
        print(f"Помилка при читанні міста: {e}")

    buttons = []
    if user_city:
        buttons.append([KeyboardButton(text=user_city)])
    buttons.append([KeyboardButton(text="Вся Україна")])
    buttons.append([KeyboardButton(text="Пошук по містах")])

    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer("Виберіть опцію для новин:", reply_markup=keyboard)


@dp.message(NewsState.option)
async def choose_news_option(message: types.Message, state: FSMContext):
    user_input = message.text.strip()

    user_city = None
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Info.city).where(Info.user_id == message.from_user.id).limit(1)
            )
            user_city = result.scalar_one_or_none()
    except Exception as e:
        print(f"Помилка при читанні міста: {e}")

    if user_input == "Пошук по містах":
        await state.set_state(CityState.news_city)
        await message.answer(
            "Напишіть назву міста для новин:", reply_markup=ReplyKeyboardRemove()
        )
        return

    if user_input in ["Україна", "Вся Україна"]:
        query = "Україна"
    elif user_city and user_input == user_city:
        query = user_city
    else:
        await message.answer(
            f"Невідомий варіант. Спробуйте '{user_city}' або 'Вся Україна'."
        )
        await state.clear()
        return

    articles = await fetch_news(query)
    if not articles:
        await message.answer(f"Новин за '{query}' не знайдено 😕")
    else:
        for article in articles:
            try:
                await message.answer(
                    f"📰 <b>{article['title']}</b>\n{article['url']}", parse_mode="HTML"
                )
            except Exception as e:
                print(f"Помилка при відправці новини: {e}")

    await state.clear()
    await message.answer("Операція завершена", reply_markup=main_kb)


@dp.message(CityState.news_city)
async def search_news_by_city(message: types.Message, state: FSMContext):
    city = message.text.strip().title()
    if not valid_city(city):
        await message.answer("Такого міста немає в базі. Спробуйте ще раз.")
        return

    articles = await fetch_news(city)
    if not articles:
        await message.answer(f"Новин за '{city}' не знайдено 😕")
    else:
        for article in articles:
            try:
                await message.answer(
                    f"📰 <b>{article['title']}</b>\n{article['url']}", parse_mode="HTML"
                )
            except Exception as e:
                print(f"Помилка при відправці новини: {e}")

    await state.clear()
    await message.answer("Операція завершена", reply_markup=main_kb)


async def main():
    await init_models()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
