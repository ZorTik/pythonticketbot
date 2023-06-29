import random
from typing import Any, Dict

import discord
from asyncio import Future
from discord import Guild, Embed
from discord.ui import View

import source
import ticket
from event import EventEmitter, EventTypes
from settings import GuildSettings, starter_settings
from setup import input_latches, option_latches, ChannelSetup, Context, OptionsPart
from source import DataSource
from ticket import Ticket, Category, ticket_from_data, ticket_to_data


class InvalidGuildStateError(Exception):
    def __init__(self):
        super().__init__()


class TicketBot(discord.Client):
    data_source: DataSource
    tickets: Dict[int, Dict[int, Ticket]]
    settings: Dict[int, GuildSettings]
    commands: discord.app_commands.CommandTree
    events: EventEmitter = EventEmitter(super)

    def __init__(self, *, intents: discord.Intents, data_source: DataSource, **options: Any):
        super().__init__(intents=intents, **options)
        self.data_source = data_source

    async def create_ticket(self, guild: Guild, user: discord.User, **kwargs) -> Future[Ticket]:
        """
        Created new ticket or starts ticket setup if insufficient details provided.

        Parameters
        guild: Guild instance
        user: Ticket author
        category: Category instance, or None if setup should be invoked

        Raises
        InvalidGuildStateError
            if the guild is not prepared.
        """
        guild_settings = self.settings.get(guild.id)
        if guild_settings is None or guild_settings.prepare_tickets_category is None or guild_settings.tickets_category is None:
            raise InvalidGuildStateError()

        if kwargs.get("category") is None:
            prepare_category_channel = await guild.fetch_channel(guild_settings.prepare_tickets_category)
            ticket_channel = await prepare_category_channel.create_text_channel(
                name=f"preparing-{user.global_name}-{random.randint(0, 999)}")

            setup_ticket_future: Future[Ticket] = Future()

            async def handle_setup_complete(status: int, ctx: Context):
                if status == 0:
                    """ Load setup results from context """
                    category_id = ctx.data["category_id"]
                    category_instance: Category = [c for c in ticket.categories if c.name == category_id].pop()

                    def when_complete(fut):
                        setup_ticket_future.set_result(fut.result())

                    (await self.create_ticket(guild, user, category=category_instance)).add_done_callback(when_complete)
                else:
                    await ticket_channel.delete(reason="Ticket setup finished with non-zero value.")
                    setup_ticket_future.cancel()

            setup = ChannelSetup(channel=ticket_channel, user=user, on_done=handle_setup_complete)
            """ Load setup parts and ids in context """
            setup.add_part(OptionsPart(key="category_id", options=list(map(lambda c: c.name, ticket.categories))))
            await setup.run()
            return setup_ticket_future

        category: Category = kwargs["category"]
        channel_name = f"{category.lc_name}-{user.global_name}-{random.randint(0, 999)}"
        channel_id = kwargs.get("channel_id") or -1
        channel: discord.TextChannel
        category_channel = await guild.fetch_channel(guild_settings.tickets_category)

        if channel_id == -1:
            channel = await category_channel.create_text_channel(name=channel_name)
        else:
            channel = await guild.fetch_channel(channel_id)
            channel = await channel.edit(name=channel_name, category=category_channel)

        channel_id = channel.id
        ticket_instance = Ticket(channel_id=channel_id)

        if self.tickets.get(guild.id) is None:
            self.tickets[guild.id] = {}

        self.tickets[guild.id][channel_id] = ticket_instance
        await self.events.call(EventTypes.ticket_create, {
            "ticket": ticket_instance,
            "channel": channel
        })

        self.save_tickets()
        future = Future()
        future.set_result(ticket_instance)
        return future

    async def reload_guild(self, guild: discord.Guild):
        if guild.id not in self.settings.keys():
            self.settings[guild.id] = starter_settings()
        if guild.id not in self.tickets.keys():
            self.tickets[guild.id] = {}
        await self.unload_guild(guild)

        guild_settings = self.settings[guild.id]
        if guild_settings.entry_channel is not None:
            entry_channel = await guild.fetch_channel(guild_settings.entry_channel)
            entry_message_embed = Embed()
            bot_self = self

            class EntryMessageView(View):
                def __init__(self):
                    super().__init__()

                @discord.ui.button(label="Create Ticket")
                async def handle_create_button_click(self, interaction: discord.Interaction, item):
                    await bot_self.create_ticket(guild=guild, user=interaction.user)

            entry_message = await entry_channel.send(
                embed=entry_message_embed,
                view=EntryMessageView()
            )
            guild_settings.entry_message = entry_message.id

        self.save_settings()

    async def unload_guild(self, guild: discord.Guild):
        settings = self.settings[guild.id]
        if settings.entry_channel and settings.entry_message is not None:
            entry_channel = await guild.fetch_channel(settings.entry_channel)
            entry_message = await entry_channel.fetch_message(settings.entry_message)
            await entry_message.delete()

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
                ticket_instance = ticket_from_data(self, tickets_data[guild_id][ticket_channel_id])
                self.tickets[guild_id][ticket_channel_id] = ticket_instance

        for guild in self.guilds:
            await self.reload_guild(guild)

        await self.commands.sync()

    async def on_guild_join(self, guild: discord.Guild):
        await self.commands.sync(guild=guild)
        await self.reload_guild(guild)
        print(f"Joined {guild.name}")

    async def on_message(self, message: discord.Message):
        for latch_context in input_latches:
            """ Search for active setup input latches for messages """
            if latch_context.channel.id == message.channel.id and latch_context.user.id == message.author.id:
                await input_latches[latch_context](message)

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data["custom_id"]
            for option_latch_ids in option_latches:
                """ Search for button selection latches in setups """
                if custom_id in option_latch_ids:
                    await option_latches[option_latch_ids](custom_id)

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

        await response.send_message(embed=embed,ephemeral=True,view=CommandSetupView())

    async def handle_command_ticket_admin(self, interaction: discord.Interaction):
        """ TODO """
        pass

    @events.listener(event_name=EventTypes.setup_entry_channel_set)
    async def on_entry_channel_set(self, event):
        interaction = event["interaction"]
        await interaction.response.send_message(content="Channel set as entry channel!", ephemeral=True)
