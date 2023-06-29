from typing import Any

import discord


class Category:
    name: str
    lc_name: str

    def __init__(self, name: str, lc_name: str):
        self.name = name
        self.lc_name = lc_name


class Ticket:
    client: discord.Client
    channel_id: int

    def __init__(self, client: discord.Client, channel_id: int):
        self.client = client
        self.channel_id = channel_id


def ticket_from_data(client: discord.Client, data) -> Ticket:
    return Ticket(client=client, channel_id=data["channel_id"])


def ticket_to_data(ticket: Ticket) -> Any:
    data = {
        "channel_id": ticket.channel_id
    }
    return data


categories = [
    Category(name="General Category", lc_name="general")
]
