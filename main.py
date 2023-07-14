import os

import asyncio
import discord
from dotenv import load_dotenv

from client import TicketBot
from commands import init_commands
from setup import setups
from source import JsonDataSource


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
    init_commands(client)

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
    asyncio.run(main())
