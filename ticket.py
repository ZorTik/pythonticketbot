from typing import Any


class Category:
    name: str

    def __init__(self, name: str):
        self.name = name


class Ticket:
    channel_id: int

    def __init__(self, channel_id: int):
        self.channel_id = channel_id


def ticket_from_data(data) -> Ticket:
    return Ticket(channel_id=data["channel_id"])


def ticket_to_data(ticket: Ticket) -> Any:
    data = {
        "channel_id": ticket.channel_id
    }
    return data


categories = [
    Category(name="General Category")
]
