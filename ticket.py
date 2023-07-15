from typing import Any, Dict

import discord
from discord import Embed

import event
import settings
import client
import random


class Category:
    name: str
    lc_name: str  # ID
    description: str
    long_desc: str

    def __init__(self,
                 name: str,
                 lc_name: str,
                 description: str,
                 long_desc: str):
        self.name = name
        self.lc_name = lc_name
        self.description = description
        self.long_desc = long_desc


class Ticket:
    client: Any  # TicketBot
    channel_id: int
    author_id: int
    category: Category
    title: str
    description: str
    is_open: bool
    persistent: Dict[str, Any]

    def __init__(
            self,
            client: Any,
            channel_id: int,
            author_id: int,
            category: Category,
            title: str,
            description: str,
            is_open: bool = True,
            persistent=None
    ):
        self.client = client
        self.channel_id = channel_id
        self.author_id = author_id
        self.category = category
        self.title = title
        self.description = description
        self.is_open = is_open
        self.persistent = persistent or {}

    async def fetch_channel(self) -> discord.TextChannel:
        return await self.client.fetch_channel(self.channel_id)

    async def fetch_author(self):
        return await self.client.fetch_user(self.author_id)

    async def send_welcome_message(self):
        channel = await self.fetch_channel()
        if self.is_open:
            status = "Open"
        else:
            status = "Closed"
        embed = Embed(
            title="A new ticket has appeared!",
            description="Please stay tuned, staff will be here for you soon",
        )
        embed.add_field(name="Category", value=self.category.name, inline=True)
        embed.add_field(name="Problem", value=self.title, inline=False)
        embed.add_field(name="Problem Description", value=self.description, inline=False)
        embed.add_field(name="Status", value=status, inline=True)
        if self.persistent.get("welcome_message_id") is not None:
            old_message = await channel.fetch_message(int(self.persistent.get("welcome_message_id")))
            await old_message.edit(embed=embed)
        else:
            new_message = await channel.send(embed=embed)
            self.persistent["welcome_message_id"] = str(new_message.id)

    async def reopen(self):
        await self.change_open_state(open_state=True)

    async def close(self):
        await self.change_open_state(open_state=False)

    async def change_open_state(self, open_state: bool):
        if self.is_open == open_state:
            return
        bot_client: client.TicketBot = self.client
        channel: discord.TextChannel = await self.fetch_channel()
        author: discord.Member = channel.guild.get_member(self.author_id)
        guild_settings: settings.GuildSettings = bot_client.get_guild_settings(channel.guild)
        if open_state:
            new_name = f"{self.category.lc_name}-{author.name}-{random.randint(0, 999)}"
            new_category_channel_id = guild_settings.tickets_category
            event_call = event.EventTypes.ticket_reopen
            overwrites = self.open_overwrites(overwrites=channel.overwrites_for(author))
        else:
            new_name = f"closed-{author.name}-{random.randint(0, 999)}"
            new_category_channel_id = guild_settings.closed_tickets_category
            event_call = event.EventTypes.ticket_close
            overwrites = await self.close_overwrites(author)
        await channel.set_permissions(target=author, overwrite=overwrites)
        await channel.edit(
            name=new_name,
            category=await bot_client.fetch_channel(new_category_channel_id)
        )
        self.client.save_tickets()
        await self.send_welcome_message()
        self.is_open = open_state
        await self.client.events.call(event_call, {"ticket": self, "channel": channel, "author": author})

    def open_overwrites(self, overwrites: discord.PermissionOverwrite) -> discord.PermissionOverwrite:
        overwrites.view_channel = True
        overwrites.send_messages = True
        return overwrites

    async def close_overwrites(self, member: discord.Member) -> discord.PermissionOverwrite:
        channel = await self.fetch_channel()
        return channel.overwrites_for(member.top_role)


def ticket_from_data(client: discord.Client, data) -> Ticket:
    categories_query = [c for c in categories if c.lc_name == data["category"]]
    category: Any
    if len(categories_query) > 0:
        category = categories_query.pop()
    else:
        category = None

    return Ticket(
        client=client,
        channel_id=data["channel_id"],
        author_id=data["author_id"],
        category=category,
        title=data["title"],
        description=data["description"],
        is_open=data.get("is_open") or True,
        persistent=data.get("persistent_data")
    )


def ticket_to_data(ticket: Ticket) -> Any:
    data = {
        "channel_id": ticket.channel_id,
        "author_id": ticket.author_id,
        "category": ticket.category.lc_name,
        "title": ticket.title,
        "description": ticket.description,
        "is_open": ticket.is_open,
        "persistent_data": ticket.persistent
    }
    return data


categories = [
    Category(name="General Category",
             lc_name="general",
             description="General Questions category",
             long_desc="Long Description about this category")
]
