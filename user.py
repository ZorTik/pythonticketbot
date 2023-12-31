import discord

import source

permissions = {
    "admin_panel": {"name": "Use Admin Panel"},
    "user_panel": {"name": "Use User Panel"},
    "user_panel_groups": {"name": "Set user a group through panel"},
    "admin_setup": {"name": "Use Admin Setup"},
    "ticket_panel": {"name": "Use Ticket Admin"},
    "sync_commands": {"name": "Synchronize Commands"},
    "reload": {"name": "Reload bot on current guild"}
}

roles = {
    "default": {
        "name": "Default Role",
        "perms": []
    },
    "admin": {
        "name": "Tickets Admin",
        "perms": list(permissions.keys())  # All
    }
}


def user(d_source: source.DataSource, guild_id: int, user_id: int):
    data = d_source.load(source.DataTypes.user(guild_id, user_id))
    created = False
    if data is None:
        data = {
            "role_id": "default"
        }
        created = True
    user_inst = TicketUser(guild_id, user_id, data)
    if created:
        user_inst.save(d_source)

    return user_inst


class TicketUser:
    guild_id: int
    id: int
    role_id: str

    def __init__(self, guild_id: int, user_id: int, data):
        self.guild_id = guild_id
        self.id = user_id
        self.role_id = data.get("role_id")

    def save(self, d_source: source.DataSource):
        data = {
            "role_id": self.role_id
        }
        d_source.save(source.DataTypes.user(self.guild_id, self.id), data)

    def set_role(self, role_id):
        role = roles.get(role_id)
        if role is None:
            raise ValueError("Provided role does not exist!")
        self.role_id = role_id
        return role

    def get_role(self):
        return roles.get(self.role_id)

    async def handle_restricted_interaction(self,
                                            interaction: discord.Interaction,
                                            perms,
                                            handler):
        is_admin = interaction.user.guild_permissions.administrator
        if not is_admin and any(map(lambda p: p not in self.get_role().perms, perms)):
            await interaction.response.send_message(
                embed=discord.Embed(
                    color=discord.Color.red(),
                    title="Restricted Access!",
                    description="You don't have access to this content.",
                ),
                ephemeral=True
            )
            return

        await handler()
