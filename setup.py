import string
import random
from typing import Dict, Any, List

import discord


class Context:
    data: Dict[str, Any]
    channel: discord.TextChannel
    user: discord.User


class Part:
    async def run(self, ctx: Context, next_func, cancel_func):
        """ Run setup part in channel """
        pass


input_latches: Dict[Context, Any] = {}
option_latches: Dict[List[str], Any] = {}


class InputPart(Part):
    key: str
    message_args: Any

    def __init__(self, key: str, **message_args):
        self.key = key
        self.message_args = message_args

    async def run(self, ctx: Context, next_func, cancel_func):
        await ctx.channel.send(**self.message_args)

        async def move_next(message: discord.Message):
            del input_latches[ctx]
            ctx.data[self.key] = message.content
            await next_func()

        input_latches[ctx] = move_next


class OptionsPart(Part):
    key: str
    options: List[str]
    message_args: Any

    def __init__(self, key: str, options: List[str] = None, **kwargs):
        self.key = key
        self.options = options or []
        self.message_args = kwargs

    async def run(self, ctx: Context, next_func, cancel_func):
        options_view = discord.ui.View()
        button_maps: Dict[str, str] = {}
        for option in self.options:
            letters = string.ascii_lowercase
            custom_id = "".join(random.choice(letters) for _ in range(10))
            button_maps[custom_id] = option
            button = discord.ui.Button(style=discord.ButtonStyle.gray, label=option, )
            options_view.add_item(button)

        await ctx.channel.send(view=options_view, **self.message_args)

        option_latch_keys = [*button_maps.keys()]

        async def handle_button_click(button_custom_id: str):
            if button_custom_id in button_maps.keys():
                del option_latches[option_latch_keys]
                option_selected = button_maps[button_custom_id]
                ctx.data[self.key] = option_selected
                await next_func()

        option_latches[option_latch_keys] = handle_button_click


class ChannelSetup:
    context: Context
    parts: List[Part]
    index: int
    on_done_func: Any
    finished: bool

    def __init__(
            self,
            channel: discord.TextChannel,
            user: discord.User,
            on_done: Any,
            parts: List[Part] = None
    ):
        context = Context()
        context.channel = channel
        context.user = user
        context.data = {}
        self.context = context
        self.parts = parts or []
        self.index = -1
        self.on_done_func = on_done
        self.finished = False

    def add_part(self, part: Part):
        self.parts.append(part)

    async def run(self):
        if self.index > -1:
            raise Exception()

        async def next_func():
            if self.finished:
                return

            if self.index + 1 >= len(self.parts):
                await self.on_done_func(0, self.context)

            self.index += 1

            part = self.parts[self.index]
            await part.run(self.context, next_func, self.cancel)

        await next_func()

    async def cancel(self):
        if self.finished:
            return

        self.finished = True
        await self.on_done_func(1, self.context)
