from enum import Enum
from typing import Any, Dict, List


class EventTypes(Enum):
    setup_entry_channel_set = "setup_entry_channel_set"
    ticket_create = "ticket_create"
    ticket_close = "ticket_close"


class EventEmitter:
    holder: Any
    listeners: Dict[EventTypes, List[Any]]

    def __init__(self, holder):
        self.holder = holder
        self.listeners = {}

    def handler(self, event_name: EventTypes):
        def decorator_handler(func):
            if self.listeners.get(event_name) is None:
                self.listeners[event_name] = []
            self.listeners.get(event_name).append(func)

            return func

        return decorator_handler

    async def call(self, event_name: EventTypes, event: Any):
        listeners = self.listeners.get(event_name)
        if listeners is not None:
            [await listener(self.holder, event) for listener in listeners]
