"""
MIT License

Copyright (c) 2018-Present NeuroAssassin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import time
from collections import defaultdict
from copy import deepcopy as dc

import discord
from discord import TextChannel, Thread
from redbot.core import Config, commands
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_list


class Deleter(commands.Cog):
    """Set channels (TextChannels or Threads) for their messages to be auto-deleted after a specified amount of time.

    WARNING: This cog has potential API abuse AND SHOULD BE USED CAREFULLY!  
    If you see any issues arise due to this, please report to Neuro Assassin or bot owner ASAP!
    """

    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.conf = Config.get_conf(self, identifier=473541068378341376)
        default_channel = {"wait": 0, "messages": {}}
        self.conf.register_channel(**default_channel)
        self.task = self.bot.loop.create_task(self.background_task())

    def cog_unload(self):
        self.task.cancel()

    async def red_delete_data_for_user(self, **kwargs):
        """This cog does not store user data"""
        return

    async def background_task(self):
        await self.bot.wait_until_ready()
        while True:
            async with self.lock:
                cs = await self.conf.all_channels()
                async for channel_id, data in AsyncIter(cs.items()):
                    if int(data["wait"]) == 0:
                        continue
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel or not isinstance(channel, (TextChannel, Thread)):
                        continue
                    old = dc(data)
                    ms = dc(data["messages"])
                    async for message_id, wait in AsyncIter(ms.items()):
                        if int(wait) <= time.time():
                            dontdelete = False
                            try:
                                message = await channel.fetch_message(int(message_id))
                                if not message.pinned:
                                    await message.delete()
                            except (discord.NotFound, discord.Forbidden):
                                pass
                            except discord.HTTPException:
                                dontdelete = True
                            if not dontdelete:
                                del data["messages"][str(message_id)]
                    if old != data:
                        await self.conf.channel(channel).messages.set(data["messages"])
            await asyncio.sleep(10)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots
        if message.author.bot:
            return

        channel = message.channel
        if not isinstance(channel, (TextChannel, Thread)):
            return

        async with self.lock:
            c = await self.conf.channel(channel).all()
            if int(c["wait"]) == 0:
                return
            c["messages"][str(message.id)] = time.time() + int(c["wait"])
            await self.conf.channel(channel).messages.set(c["messages"])

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def deleter(self, ctx):
        """Group command for commands dealing with auto-timed deletion.

        To see what channels are currently being tracked, use this command with no subcommands passed.
        """
        async with self.lock:
            channels = await self.conf.all_channels()
        sending = ""
        for c_id, data in channels.items():
            channel = self.bot.get_channel(int(c_id))
            if channel is None:
                continue
            if channel.guild.id == ctx.guild.id and int(data["wait"]) != 0:
                sending += f"{channel.mention}: {data['wait']} seconds\n"
        if sending:
            await ctx.send(sending)
        else:
            await ctx.send(
                f"No channels are currently being tracked.  Add one by using `{ctx.prefix}deleter channel`."
            )

    @deleter.command()
    async def channel(self, ctx, channel: discord.abc.GuildChannel, wait):
        """Set the amount of time after a message sent in the specified channel (TextChannel or Thread) is supposed to be deleted.

        There may be about an approximate 10 second difference between the wait and the actual time the message is deleted, due to rate limiting and cooldowns.

        Wait times must be greater than or equal to 5 seconds, or 0 to disable auto-timed deletion.  If you would like to use time specifications other than seconds, suffix the wait argument with one below:

        s => seconds (ex. 5s => 5 seconds)
        m => minutes (ex. 5m => 5 minutes)
        h => hours   (ex. 5h => 5 hours)
        d => days    (ex. 5d => 5 days)
        w => weeks   (ex. 5w => 5 weeks)
        """
        # Only allow TextChannels or Threads
        if not isinstance(channel, (TextChannel, Thread)):
            return await ctx.send("You can only set auto-delete for text channels or threads.")

        if wait != "0":
            ttype = None
            wait_lower = wait.lower()
            wt = wait_lower[:-1]
            og = wait_lower[:-1]
            if not wt.isdigit():
                return await ctx.send(
                    "Invalid amount of time. There is a non-number in your `wait` argument, not including the time type."
                )
            wt = int(wt)
            if wait_lower.endswith("s"):
                ttype = "second"
            elif wait_lower.endswith("m"):
                ttype = "minute"
                wt *= 60
            elif wait_lower.endswith("h"):
                ttype = "hour"
                wt *= 3600
            elif wait_lower.endswith("d"):
                ttype = "day"
                wt *= 86400
            elif wait_lower.endswith("w"):
                ttype = "week"
                wt *= 604800
            if not ttype:
                return await ctx.send("Invalid time unit. Please use s, m, h, d, or w.")
        else:
            wt = 0

        if wt < 5 and wt != 0:
            return await ctx.send("Wait times must be greater than or equal to 5 seconds.")
        if not channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.send("I do not have permission to delete messages in that channel.")
        if not channel.permissions_for(ctx.author).manage_messages:
            return await ctx.send("You do not have permission to delete messages in that channel.")

        await self.conf.channel(channel).wait.set(str(wt))
        if wt:
            await ctx.send(
                f"Messages in {channel.mention} will now be deleted after {og} {ttype}{'s' if og != '1' else ''}."
            )
        else:
            await ctx.send("Messages will not be auto-deleted after a specific amount of time.")

    @deleter.command()
    async def remove(self, ctx, channel: discord.abc.GuildChannel, *messages: str):
        """Remove messages in the specified channel from the auto-timed deletion.

        Helpful for announcements that you want to stay in the channel.
        The messages to be removed must be the IDs of the messages you wish to remove.
        """
        if not isinstance(channel, (TextChannel, Thread)):
            return await ctx.send("You can only remove messages from text channels or threads.")

        failed = []
        success = []
        msgs = await self.conf.channel(channel).messages()
        for m in messages:
            if m not in msgs:
                failed.append(m)
                continue
            del msgs[m]
            success.append(m)

        if not failed:
            failed = [None]
        if not success:
            success = [None]

        await self.conf.channel(channel).messages.set(msgs)
        await ctx.send(
            f"Messages successfully removed: {humanize_list(success)}\nMessages that failed to be removed: {humanize_list(failed)}"
        )

    @deleter.command()
    async def wipe(self, ctx, channel: discord.abc.GuildChannel = None):
        """Removes all messages in the specified channel from the auto-timed deleter.

        Leave blank to do it for the current channel.
        """
        if channel is None:
            channel = ctx.channel
        if not isinstance(channel, (TextChannel, Thread)):
            return await ctx.send("You can only wipe messages from text channels or threads.")
        await self.conf.channel(channel).messages.set({})
        await ctx.tick()
