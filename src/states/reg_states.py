from aiogram.fsm.state import State, StatesGroup


class RegStates(StatesGroup):
    name = State()
    confirm_partner = State()  # partner already listed us; just confirm
    partner = State()          # normal flow: forward a message
