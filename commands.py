import discord
from discord import Embed, Interaction
from discord.ui import View

from event import EventTypes
from settings import GuildSettings
from setup import ChannelSetup, InputPart, Context


def init_commands(bot):
    command_group = discord.app_commands.Group(name="tickets", description="Ticket bot main commands")

    @command_group.command(name="setup", description="Ticket bot setup command")
    async def setup_command(interaction: Interaction):
        async def handle_restricted():
            response: discord.InteractionResponse = interaction.response
            embed = discord.Embed(
                colour=discord.Colour.gold(),
                title="Tickets Setup",
                description="Your guild tickets settings"
            )
            bot_self = bot

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
                            prepare_category = guild.get_channel(int(ctx.data["prepare_tickets_category_id"]))
                            tickets_category = guild.get_channel(int(ctx.data["tickets_category_id"]))
                            closed_tickets_category = guild.get_channel(int(ctx.data["closed_tickets_category_id"]))

                            if prepare_category is None or tickets_category is None or closed_tickets_category is None:
                                await interaction.user.send(content="Some provided channels are not on your guild!")
                                return

                            async def settings_modify_func(settings: GuildSettings):
                                settings.prepare_tickets_category = prepare_category.id
                                settings.tickets_category = tickets_category.id
                                settings.closed_tickets_category = closed_tickets_category.id

                            await bot_self.modify_settings(interaction.guild, settings_modify_func)
                            await interaction.user.send(content="Categories saved!")
                        else:
                            await interaction.user.send(content="Something went wrong!")

                    setup = ChannelSetup(channel=interaction.channel, user=interaction.user, on_done=handle_done)
                    setup.add_part(InputPart(
                        key="prepare_tickets_category_id",
                        embed=Embed(title="Prepare Category ID", description="Write preparing tickets category ID")
                    ))
                    setup.add_part(InputPart(
                        key="tickets_category_id",
                        embed=Embed(title="Tickets Category ID", description="Write tickets category ID")
                    ))
                    setup.add_part(InputPart(
                        key="closed_tickets_category_id",
                        embed=Embed(title="Closed Category ID", description="Write closed tickets category ID")
                    ))
                    await setup.run()
                    await interaction.response.send_message(content="Follow categories setup", ephemeral=True)

            await response.send_message(embed=embed, ephemeral=True, view=CommandSetupView())

        await bot.get_user(interaction.user).handle_restricted_interaction(
            interaction, ["admin_setup"], handle_restricted
        )

    @command_group.command(name="panel", description="Ticket bot (ticket) admin command")
    async def ticket_panel_command(interaction: Interaction):
        async def handle_restricted():
            ticket_instance = bot.get_ticket(interaction.channel)
            if ticket_instance is None:
                await interaction.response.send_message(content="You are not in a ticket!", ephemeral=True)
                return

            class TicketAdminView(View):
                def __init__(self):
                    super().__init__()

                @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.gray)
                async def close_ticket_button(self, interaction: discord.Interaction, item):
                    await ticket_instance.close()
                    await interaction.response.send_message(content="Ticket has been closed!", ephemeral=True)

            await interaction.response.send_message(embed=Embed(
                title="Ticket Admin",
                description="Choose what to do with this ticket!"
            ), view=TicketAdminView(), ephemeral=True)

        await bot.get_user(interaction.user).handle_restricted_interaction(
            interaction, ["ticket_panel"], handle_restricted
        )

    @command_group.command(name="admin", description="Ticket bot admin command")
    async def admin_command(interaction: Interaction):
        ticket_user = bot.get_user(interaction.user)

        async def handle_admin_panel():
            embed = discord.Embed(
                title="Tickets Admin",
                description="Welcome to ticket administration! Please select an option below",
            )
            # TODO: View
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await ticket_user.handle_restricted_interaction(interaction, ["admin_panel"], handle_admin_panel)

    @command_group.command(name="synccommands", description="Synchronizes all tickets commands in this guild")
    async def sync_commands_command(interaction: Interaction):
        user = bot.get_user(interaction.user)

        async def handle_sync_commands():
            await bot.sync_commands(interaction.guild)
            await interaction.response.send_message("Commands synchronized!", ephemeral=True)

        await user.handle_restricted_interaction(interaction, ["sync_commands"], handle_sync_commands)

    @command_group.command(name="reload", description="Reload ticket bot in this guild")
    async def reload_command(interaction: Interaction):
        user = bot.get_user(interaction.user)

        async def handle_reload():
            await bot.reload_guild(interaction.guild)
            await interaction.response.send_message("Bot reloaded on this guild!", ephemeral=True)

        await user.handle_restricted_interaction(interaction, ["reload"], handle_reload)

    user_command_group = discord.app_commands.Group(name="user", description="Ticket bot user commands")

    @user_command_group.command(name="panel", description="Ticket bot (user) admin command")
    async def user_panel_command(interaction: Interaction, user: discord.User):
        ticket_user = bot.get_user(interaction.user)

        async def handle_user_panel():
            embed = Embed(title=user.global_name, description="User Management Panel")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await ticket_user.handle_restricted_interaction(interaction, ["user_panel"], handle_user_panel)

    @user_command_group.command(name="setgroup", description="Set user a tickets group")
    async def user_group_set(interaction: Interaction, user: discord.User, group: str):
        ticket_user = bot.get_user(interaction.user)

        async def handle_user_panel_group():
            d_member = interaction.guild.get_member(user.id)

            if d_member is None:
                await interaction.response.send_message("Provided user is not a member on this server!", ephemeral=True)
                return
            ticket_d_user = bot.get_user(d_member)
            try:
                ticket_d_user.set_role(group)
            except ValueError:
                await interaction.response.send_message("Provided role does not exist!", ephemeral=True)

        await ticket_user.handle_restricted_interaction(interaction, ["user_panel_groups"], handle_user_panel_group)

    """ Build the command tree """
    command_group.add_command(user_command_group)
    bot.commands.add_command(command_group)


