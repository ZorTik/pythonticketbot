import json
import random
from typing import Any, Dict

import discord
from asyncio import Future
from discord import Guild, Embed, NotFound
from discord.ui import View

import source
import ticket
from event import EventEmitter, EventTypes
from settings import GuildSettings, starter_settings
from setup import input_latches, option_latches, ChannelSetup, Context, OptionsPart, InputPart
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
            await guild.fetch_channels()
            prepare_category_channel = guild.get_channel(guild_settings.prepare_tickets_category)
            ticket_channel = await prepare_category_channel.create_text_channel(
                name=f"preparing-{user.name}-{random.randint(0, 999)}")

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
            setup.add_part(OptionsPart(
                key="category_id",
                options=list(map(lambda c: c.name, ticket.categories)),
                embed=Embed(
                    title="Ticket Category",
                    description="Please select your ticket category"
                )
            ))
            await setup.run()
            return setup_ticket_future

        category: Category = kwargs["category"]
        channel_name = f"{category.lc_name}-{user.name}-{random.randint(0, 999)}"
        channel_id = kwargs.get("channel_id") or -1
        channel: discord.TextChannel
        category_channel = await guild.fetch_channel(guild_settings.tickets_category)

        if channel_id == -1:
            channel = await category_channel.create_text_channel(name=channel_name)
        else:
            channel = await guild.fetch_channel(channel_id)
            channel = await channel.edit(name=channel_name, category=category_channel)

        channel_id = channel.id
        ticket_instance = Ticket(client=self, channel_id=channel_id)

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

    def get_ticket(self, channel: discord.TextChannel):
        guild_tickets = self.tickets.get(channel.guild.id) or {}
        return guild_tickets.get(channel.id)

    async def reload_guild(self, guild: discord.Guild):
        if guild.id not in self.settings.keys():
            self.settings[guild.id] = starter_settings()
        if guild.id not in self.tickets.keys():
            self.tickets[guild.id] = {}
        await self.unload_guild(guild)

        guild_settings = self.settings[guild.id]
        if guild_settings.entry_channel is not None:
            entry_channel = await guild.fetch_channel(guild_settings.entry_channel)
            entry_message_embed = Embed(
                title="Create Ticket",
                description="Click on button below to create new ticket channel!"
            )
            bot_self = self

            class EntryMessageView(View):
                def __init__(self):
                    super().__init__()

                @discord.ui.button(label="Create Ticket")
                async def handle_create_button_click(self, interaction: discord.Interaction, item):
                    try:
                        create_ticket_future = bot_self.create_ticket(guild=guild, user=interaction.user)
                        await interaction.response.send_message(
                            content="Ticket created, check tickets category!",
                            ephemeral=True
                        )
                        await create_ticket_future
                    except InvalidGuildStateError:
                        await interaction.response.send_message(content="This guild is not set up!", ephemeral=True)

            entry_message = await entry_channel.send(
                embed=entry_message_embed,
                view=EntryMessageView()
            )
            guild_settings.entry_message = entry_message.id

        self.save_settings()

    async def unload_guild(self, guild: discord.Guild):
        settings = self.settings[guild.id]
        if settings.entry_channel and settings.entry_message is not None:
            try:
                entry_channel = await guild.fetch_channel(settings.entry_channel)
                entry_message = await entry_channel.fetch_message(settings.entry_message)
                await entry_message.delete()
            except NotFound:
                return

    async def modify_settings(self, guild: Guild, modify_func):
        await self.unload_guild(guild)
        await modify_func(self.settings.get(guild.id))
        self.save_settings()
        await self.reload_guild(guild)

    def save_settings(self):
        data: Dict[int, Any] = {}
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
            self.settings[int(guild_id)] = GuildSettings(settings_data[guild_id])
            print(f"Loaded settings for guild {guild_id}")
        for guild_id in tickets_data:
            self.tickets[int(guild_id)] = {}
            for ticket_channel_id in tickets_data[guild_id]:
                ticket_instance = ticket_from_data(self, tickets_data[guild_id][ticket_channel_id])
                self.tickets[guild_id][int(ticket_channel_id)] = ticket_instance

        for guild in self.guilds:
            await self.reload_guild(guild)
            print(f"Loaded guild {guild.name}!")

        await self.commands.sync()

    async def on_guild_join(self, guild: discord.Guild):
        await self.commands.sync(guild=guild)
        await self.reload_guild(guild)
        print(f"Joined {guild.name}")

    async def on_message(self, message: discord.Message):
        """ Search for active setup input latches for messages """
        def input_latch_filter(ctx):
            return ctx.channel.id == message.channel.id and ctx.user.id == message.author.id
        input_latch_list = [latch_context for latch_context in input_latches if input_latch_filter(latch_context)]
        if len(input_latch_list) > 0:
            await input_latches[input_latch_list.pop()](message)

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            """ Search for button selection latches in setups """
            custom_id = interaction.data["custom_id"]
            option_latch_keys = [key for key in option_latches if custom_id in json.loads(key)]
            if len(option_latch_keys) > 0:
                await option_latches[option_latch_keys.pop()](custom_id)

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

                async def modify_settings_func(settings: GuildSettings):
                    settings.entry_channel = entry_channel.id
                    settings.entry_message = None  # Entry message will be created on reload

                await bot_self.modify_settings(interaction.guild, modify_settings_func)
                await bot_self.events.call(EventTypes.setup_entry_channel_set, {
                    "interaction": interaction
                })

            @discord.ui.button(label="Set Ticket Categories", style=discord.ButtonStyle.gray)
            async def set_ticket_categories_button(self, interaction: discord.Interaction, item):

                async def handle_done(status: int, ctx: Context):
                    guild = interaction.guild
                    if status == 0:
                        prepare_category_id = int(ctx.data["prepare_tickets_category_id"])
                        tickets_category_id = int(ctx.data["tickets_category_id"])

                        if guild.get_channel(prepare_category_id) is None or guild.get_channel(tickets_category_id) is None:
                            await interaction.user.send(content="Some provided channels are not on your guild!")
                            return

                        async def settings_modify_func(settings: GuildSettings):
                            settings.prepare_tickets_category = prepare_category_id
                            settings.tickets_category = tickets_category_id

                        await bot_self.modify_settings(interaction.guild, settings_modify_func)
                        await interaction.user.send(content="Categories saved!")
                    else:
                        await interaction.user.send(content="Something went wrong!")

                setup = ChannelSetup(channel=interaction.channel, user=interaction.user, on_done=handle_done)
                setup.add_part(InputPart(
                    key="prepare_tickets_category_id",
                    embed=Embed(title="Prepare Category ID", description="Write Prepare tickets category ID")
                ))
                setup.add_part(InputPart(
                    key="tickets_category_id",
                    embed=Embed(title="Tickets Category ID", description="Write tickets category ID")
                ))
                await setup.run()
                await interaction.response.send_message(content="Follow categories setup", ephemeral=True)

        await response.send_message(embed=embed, ephemeral=True, view=CommandSetupView())

    async def handle_command_ticket_admin(self, interaction: discord.Interaction):
        """ TODO """
        pass

    @events.listener(event_name=EventTypes.setup_entry_channel_set)
    async def on_entry_channel_set(self, event):
        interaction = event["interaction"]
        await interaction.response.send_message(content="Channel set as entry channel!", ephemeral=True)

    @events.listener(event_name=EventTypes.ticket_create)
    async def on_ticket_create(self, event):
        ticket_instance = event["ticket"]
        channel_instance = event["channel"]
        """ TODO: Create start message """
