from aiogram.fsm.state import State, StatesGroup


class AddWishStates(StatesGroup):
    title = State()
    deadline = State()
    visibility = State()
    confirm = State()


class EditWishStates(StatesGroup):
    new_title = State()
