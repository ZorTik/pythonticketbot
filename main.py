import os

import discord
from discord import Interaction

from client import TicketBot
from source import JsonDataSource

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.members = True

client = TicketBot(intents=intents, data_source=JsonDataSource("data.json"))
commands = discord.app_commands.CommandTree(client)
client.commands = commands


@client.commands.command(name="ticketsetup", description="Ticket bot setup command")
async def setup_command(interaction: Interaction):
    await client.handle_command_setup(interaction)


@client.commands.command(name="ticketadmin", description="Ticket bot (ticket) admin command")
async def setup_command(interaction: Interaction):
    await client.handle_command_ticket_admin(interaction)


client.run(os.environ.get("BOT_TOKEN"))
