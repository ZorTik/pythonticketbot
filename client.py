from typing import Any, Dict

import discord
from discord import Guild

import source
from event import EventEmitter, EventTypes
from settings import GuildSettings, starter_settings
from source import DataSource
from ticket import Ticket, Category, ticket_from_data, ticket_to_data


class TicketBot(discord.Client):
    data_source: DataSource
    tickets: Dict[int, Dict[int, Ticket]]
    settings: Dict[int, GuildSettings]
    commands: discord.app_commands.CommandTree
    events: EventEmitter = EventEmitter(super)

    def __init__(self, *, intents: discord.Intents, data_source: DataSource, **options: Any):
        super().__init__(intents=intents, **options)
        self.data_source = data_source

    def create_ticket(self, guild: Guild, category: Category):
        """ TODO """
        self.save_tickets()

    def save_settings(self):
        data = {}
        for k in self.settings:
            data[k] = self.settings[k].to_data()

        self.data_source.save(source.DataTypes.settings, data)

    def save_tickets(self):
        data = {}
        for guild_id in self.tickets:
            data[guild_id] = {}
            for ticket_channel_id in self.tickets[guild_id]:
                data[guild_id][ticket_channel_id] = ticket_to_data(self.tickets[guild_id][ticket_channel_id])

    async def reload_guild(self, guild: discord.Guild):
        if guild.id not in self.settings.keys():
            self.settings[guild.id] = starter_settings()
        if guild.id not in self.tickets.keys():
            self.tickets[guild.id] = {}
        await self.unload_guild(guild)
        """ TODO: Build messages """

    async def unload_guild(self, guild: discord.Guild):
        settings = self.settings[guild.id]
        if settings.entry_channel and settings.entry_message is not None:
            entry_channel = await guild.fetch_channel(settings.entry_channel)
            entry_message = await entry_channel.fetch_message(settings.entry_message)
            await entry_message.delete()

    async def on_ready(self):
        self.tickets = {}
        self.settings = {}
        tickets_data = self.data_source.load(source.DataTypes.tickets) or {}
        settings_data = self.data_source.load(source.DataTypes.settings) or {}
        for guild_id in settings_data:
            self.settings[guild_id] = GuildSettings(settings_data[guild_id])
        for guild_id in tickets_data:
            self.tickets[guild_id] = {}
            for ticket_channel_id in tickets_data[guild_id]:
                self.tickets[guild_id][ticket_channel_id] = ticket_from_data(tickets_data[guild_id][ticket_channel_id])

        for guild in self.guilds:
            await self.reload_guild(guild)

        await self.commands.sync()

    async def on_guild_join(self, guild: discord.Guild):
        await self.commands.sync(guild=guild)
        await self.reload_guild(guild)
        print(f"Joined {guild.name}")

    async def handle_command_setup(self, interaction: discord.Interaction):
        response: discord.InteractionResponse = interaction.response
        embed = discord.Embed(
            colour=discord.Colour.gold(),
            title="Tickets Setup",
            description="Your guild tickets settings"
        )
        bot_self = self

        class CommandSetupView(discord.ui.View):
            def __init__(self):
                super().__init__()

            @discord.ui.button(label="Set Entry Channel", style=discord.ButtonStyle.gray)
            async def set_entry_channel_button(self, interaction: discord.Interaction, item):
                entry_channel = interaction.channel
                entry_message = await entry_channel.send()

                bot_self.settings[interaction.guild_id].entry_channel = entry_channel.id
                bot_self.settings[interaction.guild_id].entry_message = entry_message.id
                bot_self.save_settings()
                await bot_self.reload_guild(interaction.guild)
                await bot_self.events.call(EventTypes.setup_entry_channel_set, {
                    "interaction": interaction
                })

        await response.send_message(
            embed=embed,
            ephemeral=True,
            view=CommandSetupView()
        )

    async def handle_command_ticket_admin(self, interaction: discord.Interaction):
        """ TODO """
        pass

    @events.listener(event_name=EventTypes.setup_entry_channel_set)
    async def on_entry_channel_set(self, event):
        interaction = event["interaction"]
        await interaction.response.send_message(content="Channel set as entry channel!", ephemeral=True)
