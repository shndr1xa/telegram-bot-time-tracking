import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

ENTRIES_FILE = DATA_DIR / "entries.json"
META_FILE = DATA_DIR / "meta.json"
EMPLOYEES_FILE = DATA_DIR / "employees.json"

NORM_HOURS_PER_DAY = 8.0
REMINDER_HOUR = 18
REMINDER_MINUTE = 0
REMINDER_CHECK_INTERVAL = 300

COMMON_SERVICES = [
    "Разработка",
    "Тестирование",
    "Аналитика",
    "Документация",
    "Совещание",
    "Поддержка",
]


class AuthForm(StatesGroup):
    full_name = State()
    secret_key = State()


class EntryForm(StatesGroup):
    choose_date = State()
    choose_mode = State()
    choose_recent = State()
    work_item_id = State()
    service = State()
    custom_service = State()
    hours = State()
    comment = State()
    confirm = State()


class EditLastForm(StatesGroup):
    choose_field = State()
    work_item_id = State()
    service = State()
    custom_service = State()
    hours = State()
    comment = State()
    confirm = State()


def today_str() -> str:
    return date.today().isoformat()


def yesterday_str() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сегодня"), KeyboardButton(text="Вчера")],
            [KeyboardButton(text="Статус"), KeyboardButton(text="Мои записи")],
            [KeyboardButton(text="Повторить последнюю"), KeyboardButton(text="Изменить последнюю")],
            [KeyboardButton(text="Удалить последнюю"), KeyboardButton(text="Проверить часы")],
            [KeyboardButton(text="Завершить день"), KeyboardButton(text="Очистить сегодня")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def hours_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3"), KeyboardButton(text="4")],
            [KeyboardButton(text="5"), KeyboardButton(text="6"), KeyboardButton(text="7"), KeyboardButton(text="8")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def service_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Разработка"), KeyboardButton(text="Тестирование")],
            [KeyboardButton(text="Аналитика"), KeyboardButton(text="Документация")],
            [KeyboardButton(text="Совещание"), KeyboardButton(text="Поддержка")],
            [KeyboardButton(text="Другое"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def date_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сегодня"), KeyboardButton(text="Вчера")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def entry_mode_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Новая запись"), KeyboardButton(text="Последние задачи")],
            [KeyboardButton(text="Повторить последнюю"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def confirm_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сохранить"), KeyboardButton(text="Изменить комментарий")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def edit_last_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Задача"), KeyboardButton(text="Вид работы")],
            [KeyboardButton(text="Часы"), KeyboardButton(text="Комментарий")],
            [KeyboardButton(text="Сохранить"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def smart_reminder_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сегодня"), KeyboardButton(text="Мои записи")],
            [KeyboardButton(text="Проверить часы"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True
    )


def load_entries():
    if not ENTRIES_FILE.exists():
        return defaultdict(list)

    with open(ENTRIES_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    data = defaultdict(list)
    for user_id, entries in raw_data.items():
        normalized_entries = []
        for entry in entries:
            if "date" not in entry:
                entry["date"] = today_str()
            normalized_entries.append(entry)
        data[int(user_id)] = normalized_entries

    return data


def save_entries():
    serializable_data = {str(user_id): entries for user_id, entries in daily_entries.items()}
    with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable_data, f, ensure_ascii=False, indent=2)


def load_meta():
    if not META_FILE.exists():
        return {}

    with open(META_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def save_meta():
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, ensure_ascii=False, indent=2)


def load_employees():
    if not EMPLOYEES_FILE.exists():
        raise FileNotFoundError("Не найден data/employees.json. Создай этот файл в папке data.")

    with open(EMPLOYEES_FILE, "r", encoding="utf-8") as f:
        rows = json.load(f)

    result = {}
    for row in rows:
        full_name = row["full_name"].strip()
        key = row["key"].strip().upper()
        result[full_name.lower()] = {"full_name": full_name, "key": key}
    return result


daily_entries = load_entries()
meta_data = load_meta()
employees_data = load_employees()


def is_user_verified(user_id: int) -> bool:
    return str(user_id) in meta_data and meta_data[str(user_id)].get("is_verified", False)


def ensure_user_meta(user_id: int, telegram_name: str | None = None):
    key = str(user_id)
    if key not in meta_data:
        meta_data[key] = {
            "telegram_name": telegram_name or "",
            "last_reminder_date": "",
            "is_verified": False,
            "full_name": "",
            "employee_key": "",
        }
    else:
        if telegram_name:
            meta_data[key]["telegram_name"] = telegram_name
    save_meta()


def verify_employee(full_name: str, employee_key: str):
    employee = employees_data.get(full_name.strip().lower())
    if not employee:
        return None
    if employee["key"] != employee_key.strip().upper():
        return None
    return employee


def get_entries_by_date(user_id: int, target_date: str) -> list:
    return [entry for entry in daily_entries[user_id] if entry.get("date") == target_date]


def get_today_entries(user_id: int) -> list:
    return get_entries_by_date(user_id, today_str())


def get_total_hours(user_id: int, target_date: str | None = None) -> float:
    if target_date is None:
        target_date = today_str()
    return sum(entry["hours"] for entry in daily_entries[user_id] if entry.get("date") == target_date)


def get_last_three_templates(user_id: int) -> list:
    seen = set()
    result = []

    for entry in reversed(daily_entries[user_id]):
        key = (entry.get("workItemId", ""), entry.get("service", ""), entry.get("comment", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "workItemId": entry.get("workItemId", ""),
            "service": entry.get("service", ""),
            "comment": entry.get("comment", ""),
        })
        if len(result) >= 3:
            break

    return result


def get_last_entry(user_id: int):
    if not daily_entries[user_id]:
        return None
    return daily_entries[user_id][-1]


def format_entry_card(entry: dict) -> str:
    return (
        f"Дата: {entry.get('date', '')}\n"
        f"Задача: {entry.get('workItemId', '')}\n"
        f"Вид работы: {entry.get('service', '')}\n"
        f"Часы: {entry.get('hours', 0)}\n"
        f"Комментарий: {entry.get('comment', '')}"
    )


def compact_entries_text(entries: list, header: str = "Мои записи") -> str:
    if not entries:
        return f"{header}\n\nЗаписей нет."

    text = f"{header}\n\n"
    total = 0.0
    for i, entry in enumerate(entries, start=1):
        total += float(entry["hours"])
        text += f"{i}. {entry['workItemId']} — {entry['hours']} ч. — {entry['service']}\n"
    text += f"\nИтого: {total} ч."
    return text


async def send_daily_reminders():
    while True:
        try:
            now = datetime.now()
            if now.hour > REMINDER_HOUR or (now.hour == REMINDER_HOUR and now.minute >= REMINDER_MINUTE):
                for user_id_str, user_meta in meta_data.items():
                    user_id = int(user_id_str)

                    if not user_meta.get("is_verified", False):
                        continue

                    total = get_total_hours(user_id, today_str())
                    already_reminded = user_meta.get("last_reminder_date") == today_str()

                    if total < NORM_HOURS_PER_DAY and not already_reminded:
                        remaining = NORM_HOURS_PER_DAY - total
                        await bot.send_message(
                            user_id,
                            f"Напоминание: {user_meta.get('full_name', 'сотрудник')},\n"
                            f"сегодня внесено {total} ч. из {NORM_HOURS_PER_DAY}.\n"
                            f"Осталось внести: {remaining} ч.\n\n"
                            f"Выбери действие ниже.",
                            reply_markup=smart_reminder_keyboard()
                        )
                        user_meta["last_reminder_date"] = today_str()
                        save_meta()
        except Exception as e:
            print(f"[REMINDER ERROR] {e}")

        await asyncio.sleep(REMINDER_CHECK_INTERVAL)


async def ask_for_auth(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AuthForm.full_name)
    await message.answer(
        "Сначала нужно пройти идентификацию.\n"
        "Введите ФИО полностью, как в списке сотрудников."
    )


def build_confirm_text(data: dict) -> str:
    return (
        "Проверьте запись перед сохранением:\n\n"
        f"Дата: {data.get('date', '')}\n"
        f"Задача: {data.get('workItemId', '')}\n"
        f"Вид работы: {data.get('service', '')}\n"
        f"Часы: {data.get('hours', '')}\n"
        f"Комментарий: {data.get('comment', '')}"
    )


async def start_entry_flow(message: Message, state: FSMContext, preset_date: str | None = None):
    if preset_date:
        await state.update_data(date=preset_date)
        await state.set_state(EntryForm.choose_mode)
        await message.answer(
            f"Выбрана дата: {preset_date}\nВыберите способ ввода:",
            reply_markup=entry_mode_keyboard()
        )
    else:
        await state.set_state(EntryForm.choose_date)
        await message.answer("Выберите дату для записи:", reply_markup=date_keyboard())


async def begin_new_entry(message: Message, state: FSMContext):
    await state.set_state(EntryForm.work_item_id)
    await message.answer("Введите WorkItemID / номер задачи:", reply_markup=main_menu_keyboard())


async def use_last_entry_template(message: Message, state: FSMContext):
    user_id = message.from_user.id
    last_entry = get_last_entry(user_id)

    if not last_entry:
        await message.answer("Последней записи нет.", reply_markup=main_menu_keyboard())
        return

    await state.update_data(
        workItemId=last_entry["workItemId"],
        service=last_entry["service"],
        old_comment=last_entry["comment"],
        use_template=True,
    )
    await state.set_state(EntryForm.hours)
    await message.answer(
        f"Повтор последней записи:\n"
        f"Задача: {last_entry['workItemId']}\n"
        f"Вид работы: {last_entry['service']}\n"
        f"Выберите количество часов:",
        reply_markup=hours_keyboard()
    )


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    ensure_user_meta(user_id, message.from_user.full_name)

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    employee_name = meta_data[str(user_id)].get("full_name", "")
    await message.answer(
        f"Привет, {employee_name}!\n"
        "Я бот для ввода трудозатрат.",
        reply_markup=main_menu_keyboard()
    )


@dp.message(AuthForm.full_name)
async def process_auth_full_name(message: Message, state: FSMContext):
    full_name = message.text.strip()

    if full_name.lower() not in employees_data:
        await message.answer(
            "Такое ФИО не найдено в списке.\n"
            "Проверь написание и введи ФИО полностью еще раз."
        )
        return

    await state.update_data(full_name=employees_data[full_name.lower()]["full_name"])
    await state.set_state(AuthForm.secret_key)
    await message.answer("Теперь введите ваш индивидуальный ключ.")


@dp.message(AuthForm.secret_key)
async def process_auth_key(message: Message, state: FSMContext):
    data = await state.get_data()
    full_name = data.get("full_name", "")
    employee_key = message.text.strip().upper()

    verified_employee = verify_employee(full_name, employee_key)
    if not verified_employee:
        await message.answer("ФИО и ключ не совпали.\nПопробуйте снова: /start")
        await state.clear()
        return

    user_id = message.from_user.id
    ensure_user_meta(user_id, message.from_user.full_name)

    meta_data[str(user_id)]["is_verified"] = True
    meta_data[str(user_id)]["full_name"] = verified_employee["full_name"]
    meta_data[str(user_id)]["employee_key"] = verified_employee["key"]
    save_meta()

    await state.clear()
    await message.answer(
        f"Идентификация пройдена.\nЗдравствуйте, {verified_employee['full_name']}!",
        reply_markup=main_menu_keyboard()
    )


@dp.message(Command("today"))
async def today_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    ensure_user_meta(user_id, message.from_user.full_name)

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    await state.clear()
    await start_entry_flow(message, state, today_str())


@dp.message(Command("status"))
async def status_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    total = get_total_hours(user_id)
    remaining = max(0, NORM_HOURS_PER_DAY - total)
    entries = get_today_entries(user_id)

    if not entries:
        await message.answer("Записей за сегодня пока нет.", reply_markup=main_menu_keyboard())
        return

    await message.answer(
        f"Статус за сегодня:\n"
        f"Внесено: {total} ч.\n"
        f"Осталось: {remaining} ч.\n"
        f"Количество записей: {len(entries)}",
        reply_markup=main_menu_keyboard()
    )


@dp.message(Command("remindcheck"))
async def remindcheck_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    total = get_total_hours(user_id)

    if total < NORM_HOURS_PER_DAY:
        await message.answer(
            f"Сейчас внесено: {total} ч. из {NORM_HOURS_PER_DAY}.\n"
            f"Осталось: {NORM_HOURS_PER_DAY - total} ч.",
            reply_markup=main_menu_keyboard()
        )
    elif total == NORM_HOURS_PER_DAY:
        await message.answer("Сегодня внесено ровно 8 часов. Всё заполнено.", reply_markup=main_menu_keyboard())
    else:
        await message.answer(
            f"Сегодня внесено {total} ч.\nНорма превышена на {total - NORM_HOURS_PER_DAY} ч.",
            reply_markup=main_menu_keyboard()
        )


@dp.message(Command("finish"))
async def finish_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    total = get_total_hours(user_id)

    if total == 0:
        await message.answer("Нет записей для завершения дня.", reply_markup=main_menu_keyboard())
        return
    if total < NORM_HOURS_PER_DAY:
        await message.answer(
            f"День заполнен не полностью.\n"
            f"Сейчас внесено: {total} ч.\n"
            f"Осталось внести: {NORM_HOURS_PER_DAY - total} ч.",
            reply_markup=main_menu_keyboard()
        )
        return
    if total > NORM_HOURS_PER_DAY:
        await message.answer(
            f"Превышена норма.\n"
            f"Сейчас внесено: {total} ч.\n"
            f"Нужно скорректировать записи.",
            reply_markup=main_menu_keyboard()
        )
        return

    await message.answer("День заполнен полностью: 8 часов.", reply_markup=main_menu_keyboard())


@dp.message(Command("clear"))
async def clear_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    today = today_str()
    daily_entries[user_id] = [entry for entry in daily_entries[user_id] if entry.get("date") != today]
    save_entries()
    await message.answer("Все записи за сегодня очищены.", reply_markup=main_menu_keyboard())


@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Текущий ввод отменен.", reply_markup=main_menu_keyboard())


@dp.message(F.text == "Сегодня")
async def today_button_handler(message: Message, state: FSMContext):
    await today_handler(message, state)


@dp.message(F.text == "Вчера")
async def yesterday_button_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return
    await state.clear()
    await start_entry_flow(message, state, yesterday_str())


@dp.message(F.text == "Статус")
async def status_button_handler(message: Message, state: FSMContext):
    await status_handler(message, state)


@dp.message(F.text == "Мои записи")
async def my_entries_button_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    entries = get_today_entries(user_id)
    await message.answer(compact_entries_text(entries, "Мои записи за сегодня"), reply_markup=main_menu_keyboard())


@dp.message(F.text == "Завершить день")
async def finish_button_handler(message: Message, state: FSMContext):
    await finish_handler(message, state)


@dp.message(F.text == "Проверить часы")
async def remindcheck_button_handler(message: Message, state: FSMContext):
    await remindcheck_handler(message, state)


@dp.message(F.text == "Очистить сегодня")
async def clear_button_handler(message: Message, state: FSMContext):
    await clear_handler(message, state)


@dp.message(F.text == "Отмена")
async def cancel_button_handler(message: Message, state: FSMContext):
    await cancel_handler(message, state)


@dp.message(F.text == "Повторить последнюю")
async def repeat_last_button_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    await state.clear()
    await state.update_data(date=today_str())
    await use_last_entry_template(message, state)


@dp.message(F.text == "Удалить последнюю")
async def delete_last_button_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    last_entry = get_last_entry(user_id)
    if not last_entry:
        await message.answer("Последней записи нет.", reply_markup=main_menu_keyboard())
        return

    daily_entries[user_id].pop()
    save_entries()
    await message.answer("Последняя запись удалена.", reply_markup=main_menu_keyboard())


@dp.message(F.text == "Изменить последнюю")
async def edit_last_button_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    last_entry = get_last_entry(user_id)
    if not last_entry:
        await message.answer("Последней записи нет.", reply_markup=main_menu_keyboard())
        return

    await state.clear()
    await state.set_state(EditLastForm.choose_field)
    await state.update_data(edit_entry=last_entry.copy())

    await message.answer(
        "Последняя запись:\n\n"
        f"{format_entry_card(last_entry)}\n\n"
        "Выберите, что изменить:",
        reply_markup=edit_last_keyboard()
    )


@dp.message(EntryForm.choose_date)
async def process_choose_date(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    if text == "Сегодня":
        await start_entry_flow(message, state, today_str())
        return

    if text == "Вчера":
        await start_entry_flow(message, state, yesterday_str())
        return

    await message.answer("Выберите дату кнопками.", reply_markup=date_keyboard())


@dp.message(EntryForm.choose_mode)
async def process_choose_mode(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    if text == "Новая запись":
        await begin_new_entry(message, state)
        return

    if text == "Последние задачи":
        user_id = message.from_user.id
        templates = get_last_three_templates(user_id)

        if not templates:
            await message.answer("Последних задач нет. Переходим к новой записи.")
            await begin_new_entry(message, state)
            return

        msg = "Выберите одну из последних задач или введите 0 для новой:\n\n"
        for i, template in enumerate(templates, start=1):
            msg += (
                f"{i}. {template['workItemId']} — {template['service']}\n"
                f"   {template['comment']}\n\n"
            )

        await state.update_data(recent_templates=templates)
        await state.set_state(EntryForm.choose_recent)
        await message.answer(msg + "Отправь 1, 2, 3 или 0.", reply_markup=main_menu_keyboard())
        return

    if text == "Повторить последнюю":
        await use_last_entry_template(message, state)
        return

    await message.answer("Выберите один из вариантов.", reply_markup=entry_mode_keyboard())


@dp.message(EntryForm.choose_recent)
async def process_choose_recent(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    templates = data.get("recent_templates", [])

    if text == "0":
        await begin_new_entry(message, state)
        return

    if text not in ("1", "2", "3"):
        await message.answer("Отправь 1, 2, 3 или 0.", reply_markup=main_menu_keyboard())
        return

    idx = int(text) - 1
    if idx >= len(templates):
        await message.answer("Такого варианта нет.", reply_markup=main_menu_keyboard())
        return

    template = templates[idx]
    await state.update_data(
        workItemId=template["workItemId"],
        service=template["service"],
        old_comment=template["comment"],
        use_template=True,
    )
    await state.set_state(EntryForm.hours)
    await message.answer(
        f"Выбрана задача {template['workItemId']} ({template['service']}).\n"
        f"Выберите количество часов:",
        reply_markup=hours_keyboard()
    )


@dp.message(EntryForm.work_item_id)
async def process_work_item(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await cancel_handler(message, state)
        return

    await state.update_data(workItemId=text, use_template=False)
    await state.set_state(EntryForm.service)
    await message.answer("Выберите вид работы:", reply_markup=service_keyboard())


@dp.message(EntryForm.service)
async def process_service(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    if text == "Другое":
        await state.set_state(EntryForm.custom_service)
        await message.answer("Введите свой вариант вида работы:", reply_markup=main_menu_keyboard())
        return

    if text not in COMMON_SERVICES:
        await message.answer("Выберите вид работы кнопками.", reply_markup=service_keyboard())
        return

    await state.update_data(service=text)
    await state.set_state(EntryForm.hours)
    await message.answer("Выберите количество часов:", reply_markup=hours_keyboard())


@dp.message(EntryForm.custom_service)
async def process_custom_service(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await cancel_handler(message, state)
        return

    await state.update_data(service=text)
    await state.set_state(EntryForm.hours)
    await message.answer("Выберите количество часов:", reply_markup=hours_keyboard())


@dp.message(EntryForm.hours)
async def process_hours(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    allowed_hours = {"1", "2", "3", "4", "5", "6", "7", "8"}
    if text not in allowed_hours:
        await message.answer("Нужно выбрать одно из значений от 1 до 8 кнопками.", reply_markup=hours_keyboard())
        return

    hours = float(text)
    await state.update_data(hours=hours)

    data = await state.get_data()
    if data.get("use_template"):
        old_comment = data.get("old_comment", "")
        await state.set_state(EntryForm.comment)
        await message.answer(
            "Введи новый комментарий или отправь точку '.' чтобы оставить прежний:\n"
            f"Текущий комментарий: {old_comment}",
            reply_markup=main_menu_keyboard()
        )
    else:
        await state.set_state(EntryForm.comment)
        await message.answer("Введите комментарий по выполненной работе:", reply_markup=main_menu_keyboard())


@dp.message(EntryForm.comment)
async def process_comment(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_user_verified(user_id):
        await ask_for_auth(message, state)
        return

    data = await state.get_data()
    comment_text = message.text.strip()

    if data.get("use_template") and comment_text == ".":
        comment_text = data.get("old_comment", "")

    await state.update_data(comment=comment_text)
    final_data = await state.get_data()

    await state.set_state(EntryForm.confirm)
    await message.answer(build_confirm_text(final_data), reply_markup=confirm_keyboard())


@dp.message(EntryForm.confirm)
async def process_confirm(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    if text == "Изменить комментарий":
        await state.set_state(EntryForm.comment)
        await message.answer("Введите новый комментарий:", reply_markup=main_menu_keyboard())
        return

    if text != "Сохранить":
        await message.answer("Выберите действие кнопками.", reply_markup=confirm_keyboard())
        return

    user_id = message.from_user.id
    data = await state.get_data()

    entry = {
        "date": data["date"],
        "full_name": meta_data[str(user_id)]["full_name"],
        "employee_key": meta_data[str(user_id)]["employee_key"],
        "telegram_user_id": str(user_id),
        "workItemId": data["workItemId"],
        "service": data["service"],
        "hours": data["hours"],
        "comment": data["comment"],
    }

    daily_entries[user_id].append(entry)
    save_entries()

    total = get_total_hours(user_id, data["date"])
    remaining = NORM_HOURS_PER_DAY - total

    await state.clear()

    if data["date"] == today_str():
        if remaining > 0:
            await message.answer(
                "Запись сохранена.\n\n"
                f"{format_entry_card(entry)}\n\n"
                f"Итого за сегодня: {total} ч.\n"
                f"Осталось: {remaining} ч.",
                reply_markup=main_menu_keyboard()
            )
        elif remaining == 0:
            await message.answer(
                "Запись сохранена.\n"
                "День заполнен полностью: 8 часов.",
                reply_markup=main_menu_keyboard()
            )
        else:
            await message.answer(
                f"Запись сохранена.\n"
                f"Внесено: {total} ч.\n"
                f"Превышение: {abs(remaining)} ч.",
                reply_markup=main_menu_keyboard()
            )
    else:
        await message.answer(
            "Запись за выбранную дату сохранена.\n\n"
            f"{format_entry_card(entry)}",
            reply_markup=main_menu_keyboard()
        )


@dp.message(EditLastForm.choose_field)
async def process_edit_field(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    entry = data.get("edit_entry")

    if not entry:
        await state.clear()
        await message.answer("Не удалось найти запись для редактирования.", reply_markup=main_menu_keyboard())
        return

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    if text == "Задача":
        await state.set_state(EditLastForm.work_item_id)
        await message.answer("Введите новый WorkItemID:", reply_markup=main_menu_keyboard())
        return

    if text == "Вид работы":
        await state.set_state(EditLastForm.service)
        await message.answer("Выберите вид работы:", reply_markup=service_keyboard())
        return

    if text == "Часы":
        await state.set_state(EditLastForm.hours)
        await message.answer("Выберите количество часов:", reply_markup=hours_keyboard())
        return

    if text == "Комментарий":
        await state.set_state(EditLastForm.comment)
        await message.answer("Введите новый комментарий:", reply_markup=main_menu_keyboard())
        return

    if text == "Сохранить":
        await state.set_state(EditLastForm.confirm)
        await message.answer(
            "Проверьте измененную запись:\n\n" + format_entry_card(entry),
            reply_markup=confirm_keyboard()
        )
        return

    await message.answer("Выберите действие кнопками.", reply_markup=edit_last_keyboard())


@dp.message(EditLastForm.work_item_id)
async def edit_last_work_item(message: Message, state: FSMContext):
    data = await state.get_data()
    entry = data["edit_entry"]
    entry["workItemId"] = message.text.strip()
    await state.update_data(edit_entry=entry)
    await state.set_state(EditLastForm.choose_field)
    await message.answer("Поле обновлено.", reply_markup=edit_last_keyboard())


@dp.message(EditLastForm.service)
async def edit_last_service(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Другое":
        await state.set_state(EditLastForm.custom_service)
        await message.answer("Введите свой вариант вида работы:", reply_markup=main_menu_keyboard())
        return

    if text not in COMMON_SERVICES:
        await message.answer("Выберите вид работы кнопками.", reply_markup=service_keyboard())
        return

    data = await state.get_data()
    entry = data["edit_entry"]
    entry["service"] = text
    await state.update_data(edit_entry=entry)
    await state.set_state(EditLastForm.choose_field)
    await message.answer("Поле обновлено.", reply_markup=edit_last_keyboard())


@dp.message(EditLastForm.custom_service)
async def edit_last_custom_service(message: Message, state: FSMContext):
    data = await state.get_data()
    entry = data["edit_entry"]
    entry["service"] = message.text.strip()
    await state.update_data(edit_entry=entry)
    await state.set_state(EditLastForm.choose_field)
    await message.answer("Поле обновлено.", reply_markup=edit_last_keyboard())


@dp.message(EditLastForm.hours)
async def edit_last_hours(message: Message, state: FSMContext):
    text = message.text.strip()
    allowed_hours = {"1", "2", "3", "4", "5", "6", "7", "8"}

    if text not in allowed_hours:
        await message.answer("Нужно выбрать одно из значений от 1 до 8 кнопками.", reply_markup=hours_keyboard())
        return

    data = await state.get_data()
    entry = data["edit_entry"]
    entry["hours"] = float(text)
    await state.update_data(edit_entry=entry)
    await state.set_state(EditLastForm.choose_field)
    await message.answer("Поле обновлено.", reply_markup=edit_last_keyboard())


@dp.message(EditLastForm.comment)
async def edit_last_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    entry = data["edit_entry"]
    entry["comment"] = message.text.strip()
    await state.update_data(edit_entry=entry)
    await state.set_state(EditLastForm.choose_field)
    await message.answer("Поле обновлено.", reply_markup=edit_last_keyboard())


@dp.message(EditLastForm.confirm)
async def edit_last_confirm(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "Отмена":
        await cancel_handler(message, state)
        return

    if text == "Изменить комментарий":
        await state.set_state(EditLastForm.comment)
        await message.answer("Введите новый комментарий:", reply_markup=main_menu_keyboard())
        return

    if text != "Сохранить":
        await message.answer("Выберите действие кнопками.", reply_markup=confirm_keyboard())
        return

    user_id = message.from_user.id
    data = await state.get_data()
    edited_entry = data["edit_entry"]

    if not daily_entries[user_id]:
        await state.clear()
        await message.answer("Записей для сохранения изменений не найдено.", reply_markup=main_menu_keyboard())
        return

    daily_entries[user_id][-1] = edited_entry
    save_entries()

    await state.clear()
    await message.answer(
        "Последняя запись изменена.\n\n" + format_entry_card(edited_entry),
        reply_markup=main_menu_keyboard()
    )


async def main():
    print("Бот запускается...")
    asyncio.create_task(send_daily_reminders())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())