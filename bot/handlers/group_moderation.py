"""Join/leave xabarlarini o'chirish — text moderatsiya middleware da."""
from aiogram import Router, F, Bot
from aiogram.types import Message
from database import queries

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@router.message(F.new_chat_members)
async def delete_join_message(message: Message):
    group = await queries.get_group(message.chat.id)
    if group and group["delete_join_leave"]:
        try:
            await message.delete()
        except Exception:
            pass


@router.message(F.left_chat_member)
async def delete_leave_message(message: Message):
    group = await queries.get_group(message.chat.id)
    if group and group["delete_join_leave"]:
        try:
            await message.delete()
        except Exception:
            pass
