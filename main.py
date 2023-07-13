import logging

import asyncio
import os
import sys

import discord
from discord import Interaction

from client import TicketBot
from setup import setups
from source import JsonDataSource
from dotenv import load_dotenv


async def main():
    load_dotenv()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.guild_messages = True
    intents.members = True
    intents.messages = True
    intents.message_content = True

    client = TicketBot(intents=intents, data_source=JsonDataSource("data.json"))
    commands = discord.app_commands.CommandTree(client)
    client.commands = commands

    @client.commands.command(name="ticketsetup", description="Ticket bot setup command")
    async def setup_command(interaction: Interaction):
        await client.handle_command_setup(interaction)

    @client.commands.command(name="ticketadmin", description="Ticket bot (ticket) admin command")
    async def setup_command(interaction: Interaction):
        await client.handle_command_ticket_admin(interaction)

    async def handle_exit():
        print("Cancelling setups...")
        [await setup.cancel() for setup in setups]

    try:
        await client.start(os.environ.get("BOT_TOKEN"))
    except KeyboardInterrupt:
        pass
    finally:
        await handle_exit()


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
