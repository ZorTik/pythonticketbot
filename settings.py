class GuildSettings:
    entry_channel: int
    entry_message: int

    def __init__(self, data=None):
        if data is not None:
            self.entry_channel = data["entry_channel"]
            self.entry_message = data["entry_message"]

    def to_data(self):
        return {
            "entry_channel": self.entry_channel,
            "entry_message": self.entry_message
        }


def starter_settings() -> GuildSettings:
    return GuildSettings(data={
        "entry_channel": None,
        "entry_message": None
    })
