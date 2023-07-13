from typing import Dict

from user import TicketUser


class GuildCache:
    users: Dict[int, TicketUser] = {}

    def save_user(self, user_id: int, user_inst: TicketUser):
        self.users[user_id] = user_inst

    def get_user(self, user_id: int):
        return self.users.get(user_id)
