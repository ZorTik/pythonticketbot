import os

import asyncio
import discord
from discord import Interaction
from dotenv import load_dotenv

from client import TicketBot
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

    command_group = discord.app_commands.Group(name="tickets", description="Ticket bot main commands")

    @command_group.command(name="setup", description="Ticket bot setup command")
    async def setup_command(interaction: Interaction):
        await client.handle_command_setup(interaction)

    @command_group.command(name="panel", description="Ticket bot (ticket) admin command")
    async def ticket_panel_command(interaction: Interaction):
        await client.handle_command_ticket_panel(interaction)

    @command_group.command(name="admin", description="Ticket bot admin command")
    async def admin_command(interaction: Interaction):
        await client.handle_command_ticket_admin(interaction)

    @command_group.command(name="synccommands", description="Synchronizes all tickets commands in this guild")
    async def sync_commands_command(interaction: Interaction):
        user = client.get_user(interaction.user)

        async def handle_sync_commands():
            await client.sync_commands(interaction.guild)
            await interaction.response.send_message("Commands synchronized!", ephemeral=True)

        await user.handle_restricted_interaction(interaction, ["sync_commands"], handle_sync_commands)

    @command_group.command(name="reload", description="Reload ticket bot in this guild")
    async def reload_command(interaction: Interaction):
        user = client.get_user(interaction.user)

        async def handle_reload():
            await client.reload_guild(interaction.guild)
            await interaction.response.send_message("Bot reloaded on this guild!", ephemeral=True)

        await user.handle_restricted_interaction(interaction, ["reload"], handle_reload)

    user_command_group = discord.app_commands.Group(name="user", description="Ticket bot user commands")

    @user_command_group.command(name="panel", description="Ticket bot (user) admin command")
    async def user_panel_command(interaction: Interaction, user: discord.User):
        await client.handle_command_user(interaction, user)

    @user_command_group.command(name="setgroup", description="Set user a tickets group")
    async def user_group_set(interaction: Interaction, user: discord.User, group: str):
        await client.handle_command_user_group(interaction, user, group)

    """ Build the command tree """
    command_group.add_command(user_command_group)
    client.commands.add_command(command_group)

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
