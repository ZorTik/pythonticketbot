import json
import random
from asyncio import Future
from typing import Any, Dict, TYPE_CHECKING

import discord
from discord import Guild, Embed, NotFound, SelectOption
from discord.ui import View, Select

import source
import ticket
from cache import GuildCache
from errors import InvalidGuildStateError
from event import EventEmitter, EventTypes
from settings import GuildSettings, starter_settings
from setup import input_latches, option_latches, ChannelSetup, Context, OptionsPart, InputPart
from source import DataSource
from ticket import Ticket, Category, ticket_from_data, ticket_to_data
from user import user, TicketUser


class TicketBot(discord.Client):
    # Initialize emitter now to use down with the decorators
    events: EventEmitter = EventEmitter(super)

    if TYPE_CHECKING:
        data_source: DataSource
        tickets: Dict[int, Dict[int, Ticket]]
        settings: Dict[int, GuildSettings]
        caches: Dict[int, GuildCache]
        commands: discord.app_commands.CommandTree

    def __init__(self, *, intents: discord.Intents, data_source: DataSource, **options: Any):
        super().__init__(intents=intents, **options)
        self.data_source = data_source
        self.caches = {}

    async def create_ticket(self, guild: Guild, user: discord.User, **kwargs) -> Future[Ticket]:
        """
        Created new ticket or starts ticket setup if insufficient details provided.

        Parameters
        guild: Guild instance
        user: Ticket author
        category: Category instance (Optional)
        title: Ticket title (Optional)
        description: Ticket description (Optional)

        ** All optional arguments present = Setup phase skipped

        Raises
        InvalidGuildStateError
            if the guild is not prepared.
        """
        if not self.is_guild_prepared(guild):
            raise InvalidGuildStateError()
        guild_settings = self.settings.get(guild.id)

        setup_args = ["category", "title", "description"]
        if len([arg for arg in setup_args if kwargs.get(arg) is None]) > 0:
            """ Optional arguments are not fulfilled, starting setup """
            await guild.fetch_channels()
            prepare_category_channel = guild.get_channel(guild_settings.prepare_tickets_category)
            ticket_channel = await prepare_category_channel.create_text_channel(
                name=f"preparing-{user.name}-{random.randint(0, 999)}")
            ticket_channel_overwrites = ticket_channel.overwrites_for(user)
            await ticket_channel.set_permissions(guild.get_member(user.id), overwrite=ticket_channel_overwrites)
            if kwargs.get("category") is not None:
                category = list(filter(lambda c: c.lc_name == kwargs.get("category"), ticket.categories)).pop()
                await ticket_channel.send(embed=Embed(title=category.name, description=category.long_desc))

            setup_ticket_future: Future[Ticket] = Future()

            async def handle_setup_complete(status: int, ctx: Context):
                if status == 0:
                    """ Load setup results from context """
                    category_id = ctx.data["category"]
                    title = ctx.data["title"]
                    description = ctx.data["description"]
                    category_instance: Category = [c for c in ticket.categories if c.lc_name == category_id].pop()

                    def when_complete(fut):
                        setup_ticket_future.set_result(fut.result())

                    (await self.create_ticket(
                        guild=guild, user=user,
                        category=category_instance, title=title,
                        description=description, channel_id=ticket_channel.id
                    )).add_done_callback(when_complete)
                else:
                    await ticket_channel.delete(reason="Ticket setup finished with non-zero value.")
                    setup_ticket_future.cancel()

            setup = ChannelSetup(channel=ticket_channel, user=user, on_done=handle_setup_complete)
            """ Load setup parts and ids in context """
            ticket_setup_parts = {
                "category": OptionsPart(
                    key="category",
                    options=list(map(lambda c: c.name, ticket.categories)),
                    embed=Embed(
                        title="Ticket Category",
                        description="Please select your ticket category"
                    )
                ),
                "title": InputPart(
                    key="title",
                    embed=Embed(title="Problem Title", description="Write down your problem title, please")
                ),
                "description": InputPart(
                    key="description",
                    embed=Embed(title="Problem Description", description="Now explain your problem in detail")
                )
            }
            for arg in setup_args:
                if kwargs.get(arg) is None:
                    setup.add_part(ticket_setup_parts.get(arg))
                else:
                    setup.context.data[arg] = kwargs.get(arg)
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
        ticket_instance = Ticket(
            client=self, channel_id=channel_id,
            author_id=user.id, category=category,
            title=kwargs.get("title"), description=kwargs.get("description")
        )

        overwrites = ticket_instance.open_overwrites(overwrites=channel.overwrites_for(user))
        await channel.set_permissions(target=guild.get_member(user.id), overwrite=overwrites)

        if self.tickets.get(guild.id) is None:
            self.tickets[guild.id] = {}

        self.tickets[guild.id][channel_id] = ticket_instance
        self.save_tickets()

        await ticket_instance.send_welcome_message()
        await self.events.call(EventTypes.ticket_create, {
            "ticket": ticket_instance,
            "channel": channel
        })

        future = Future()
        future.set_result(ticket_instance)
        return future

    def get_ticket(self, channel: discord.TextChannel):
        guild_tickets = self.tickets.get(channel.guild.id) or {}
        return guild_tickets.get(channel.id)

    def get_user(self, member: discord.Member) -> TicketUser:
        cache = self.get_guild_caches(member.guild)
        user_id = member.id
        user_inst = cache.get_user(user_id)
        if user_inst is None:
            user_inst = user(self.data_source, member.guild.id, user_id)
            cache.save_user(user_id, user_inst)
        return user_inst

    def get_guild_settings(self, guild: Guild):
        return self.settings.get(guild.id)

    def get_guild_caches(self, guild: Guild):
        return self.caches.get(guild.id)

    def is_guild_prepared(self, guild: Guild) -> bool:
        guild_settings = self.settings.get(guild.id)
        guild_caches = self.caches.get(guild.id)
        return guild_caches is not None and guild_settings is not None and guild_settings.is_prepared()

    def init_guild(self, guild: discord.Guild):
        if guild.id not in self.settings.keys():
            self.settings[guild.id] = starter_settings()
        if guild.id not in self.tickets.keys():
            self.tickets[guild.id] = {}
        self.caches[guild.id] = GuildCache()

    async def reload_guild(self, guild: discord.Guild):
        self.init_guild(guild)

        await self.unload_guild(guild)

        guild_settings = self.settings[guild.id]
        if guild_settings.entry_channel is not None:
            entry_channel = await guild.fetch_channel(guild_settings.entry_channel)
            entry_message_embed = Embed(
                title="Create Ticket",
                description="Click on button below to create new ticket channel!"
            )
            bot_self = self
            entry_message: discord.Message

            class EntryMessageView(View):
                def __init__(self):
                    super().__init__()

                @discord.ui.select(cls=Select, placeholder="Select Category", options=list(map(
                    lambda category: SelectOption(
                        label=category.name, value=category.lc_name, description=category.description
                    ),
                    ticket.categories
                )))
                async def handle_select_category(self, interaction: discord.Interaction, select: Select):
                    await entry_message.edit()
                    if bot_self.is_guild_prepared(interaction.guild):
                        create_ticket_future = bot_self.create_ticket(
                            guild=guild, user=interaction.user, category=select.values[0])
                        await interaction.response.send_message(
                            content="Ticket created, check tickets category!",
                            ephemeral=True
                        )
                        await create_ticket_future
                    else:
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

    async def sync_commands(self, guild):
        self.commands.copy_global_to(guild=guild)
        await self.commands.sync(guild=guild)

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
        for guild_id in tickets_data:
            self.tickets[int(guild_id)] = {}
            for ticket_channel_id in tickets_data[guild_id]:
                ticket_instance = ticket_from_data(self, tickets_data[guild_id][ticket_channel_id])
                self.tickets[guild_id][int(ticket_channel_id)] = ticket_instance
        [self.init_guild(guild) for guild in self.guilds]
        print(f"Loaded {len(self.tickets)} guilds!")

    async def on_guild_join(self, guild: discord.Guild):
        await self.sync_commands(guild)
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

    @events.handler(event_name=EventTypes.setup_entry_channel_set)
    async def on_entry_channel_set(self, event):
        interaction = event["interaction"]
        await interaction.response.send_message(content="Channel set as entry channel!", ephemeral=True)

    @events.handler(event_name=EventTypes.ticket_close)
    async def on_ticket_close(self, event):
        channel_instance: discord.TextChannel = event["channel"]
        await channel_instance.send(embed=Embed(
            title="Ticket Closed",
            description="Ticket state has been changed to closed!"
        ))
