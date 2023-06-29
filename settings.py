class GuildSettings:
    entry_channel: int
    entry_message: int
    prepare_tickets_category: int
    tickets_category: int

    def __init__(self, data=None):
        if data is not None:
            self.entry_channel = data.get("entry_channel")
            self.entry_message = data.get("entry_message")
            self.prepare_tickets_category = data.get("prepare_tickets_category")
            self.tickets_category = data.get("tickets_category")

    def to_data(self):
        return {
            "entry_channel": self.entry_channel,
            "entry_message": self.entry_message,
            "prepare_tickets_category": self.prepare_tickets_category,
            "tickets_category": self.tickets_category
        }


def starter_settings() -> GuildSettings:
    return GuildSettings(data={})
