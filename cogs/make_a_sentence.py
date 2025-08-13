import discord
from discord.ext import commands
from discord import app_commands
import cogs.utils as utils
import asyncio
import os
import re

class MakeASentence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.main_guild_id = utils.MAIN_GUILD_ID

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Always get the latest channel IDs from the global config file
        make_a_sentence_channel_id = utils.bot_config.get('make_a_sentence_channel_id')

        # If the channel ID is not set, or if the message is from a bot,
        # or it's not the correct channel, stop processing.
        if make_a_sentence_channel_id is None or message.author.bot or message.channel.id != make_a_sentence_channel_id:
            return

        content = message.content.strip()
        words = content.split()
        
        if len(words) != 1:
            try:
                await message.delete()
                await message.channel.send("Please type only one word at a time!", delete_after=5)
            except discord.Forbidden:
                pass
            return

        # Get the latest sentence from the global config
        current_sentence = utils.bot_config.get('current_sentence', [])
        word = words[0]
        current_sentence.append(word)

        if word.endswith(('.', '!', '?')) or len(word) == 1 and word in '.,!?':
            finished_sentence = " ".join(current_sentence)
            # Use the latest finished sentences channel ID from the config
            finished_sentences_channel_id = utils.bot_config.get('finished_sentences_channel_id', utils.TEST_CHANNEL_ID)
            finished_channel = self.bot.get_channel(finished_sentences_channel_id)

            if finished_channel:
                await finished_channel.send(finished_sentence)
            else:
                await message.channel.send(f"**Finished sentence:** {finished_sentence}")
                
            current_sentence = []
        
        # Save the updated state directly to the global config object
        utils.bot_config['current_sentence'] = current_sentence
        utils.save_data(utils.bot_config, utils.BOT_CONFIG_FILE)
        
        await message.add_reaction("✅")

async def setup(bot):
    await bot.add_cog(MakeASentence(bot))