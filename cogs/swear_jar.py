import discord
from discord import app_commands
from discord.ext import commands
import cogs.utils as utils 
import re
import os
import json

class SwearJar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.main_guild_id = utils.MAIN_GUILD_ID
        
        # Ensure the data directory exists
        if not os.path.exists(utils.DATA_DIR):
            os.makedirs(utils.DATA_DIR)

        # Check and initialize the swear_jar.json file
        if not os.path.exists(utils.SWEAR_JAR_FILE) or os.stat(utils.SWEAR_JAR_FILE).st_size == 0:
            print("Swear jar file not found or is empty. Initializing...")
            initial_data = {'words': [], 'tally': {}}
            utils.save_swear_jar_data(initial_data)
        else:
            try:
                swear_jar_data = utils.load_swear_jar_data()
                if 'words' not in swear_jar_data or 'tally' not in swear_jar_data:
                    print("Swear jar file is corrupted. Re-initializing...")
                    initial_data = {'words': [], 'tally': {}}
                    utils.save_swear_jar_data(initial_data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error loading swear jar data: {e}. Re-initializing file.")
                initial_data = {'words': [], 'tally': {}}
                utils.save_swear_jar_data(initial_data)

    @app_commands.command(name="addswear", description="Adds a word to the swear jar list.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(word="The word to add to the swear jar.")
    async def addswear(self, interaction: discord.Interaction, word: str):
        swear_jar_data = utils.load_swear_jar_data()
        word_lower = word.lower()
        if word_lower in swear_jar_data['words']:
            await interaction.response.send_message(f"'{word}' is already in the swear jar list.", ephemeral=True)
            return
        
        swear_jar_data['words'].append(word_lower)
        utils.save_swear_jar_data(swear_jar_data)
        await interaction.response.send_message(f"Successfully added '{word}' to the swear jar list.", ephemeral=True)

    @app_commands.command(name="removeswear", description="Removes a word from the swear jar list.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(word="The word to remove from the swear jar.")
    async def removeswear(self, interaction: discord.Interaction, word: str):
        swear_jar_data = utils.load_swear_jar_data()
        word_lower = word.lower()
        if word_lower not in swear_jar_data['words']:
            await interaction.response.send_message(f"'{word}' is not in the swear jar list.", ephemeral=True)
            return
        
        swear_jar_data['words'].remove(word_lower)
        utils.save_swear_jar_data(swear_jar_data)
        await interaction.response.send_message(f"Successfully removed '{word}' from the swear jar list.", ephemeral=True)

    @app_commands.command(name="swearlist", description="Shows the current list of words in the swear jar.")
    async def swearlist(self, interaction: discord.Interaction):
        swear_jar_data = utils.load_swear_jar_data()
        swears = swear_jar_data.get('words', [])

        if not swears:
            await interaction.response.send_message("The swear jar list is currently empty.", ephemeral=True)
            return

        swear_list_text = "\n".join(f"- {word}" for word in sorted(swears))
        embed = discord.Embed(
            title="📜 Swear Jar List",
            description=f"**Current words in the swear jar:**\n{swear_list_text}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="checkswear", description="Checks the current swear tally.")
    async def check_swear(self, interaction: discord.Interaction):
        swear_jar_data = utils.load_swear_jar_data()
        tally = swear_jar_data.get('tally', {})

        if not tally:
            await interaction.response.send_message("The swear jar is empty! No one has sworn yet.", ephemeral=True)
            return
        
        sorted_tally = sorted(tally.items(), key=lambda item: item[1], reverse=True)
        
        description = "Here's the current swear tally:\n\n"
        for user_id, count in sorted_tally:
            user = self.bot.get_user(int(user_id))
            username = user.display_name if user else f"User ID: {user_id}"
            description += f"**{username}**: {count} swears\n"

        embed = discord.Embed(
            title="💰 Swear Jar Tally",
            description=description,
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        swear_jar_data = utils.load_swear_jar_data()
        swears = swear_jar_data.get('words', [])
        
        message_words = re.findall(r'\b\w+\b', message.content.lower())
        
        for word in message_words:
            if word in swears:
                user_id_str = str(message.author.id)
                swear_jar_data['tally'][user_id_str] = swear_jar_data['tally'].get(user_id_str, 0) + 1
                utils.save_swear_jar_data(swear_jar_data)

                await message.channel.send(f"<a:starcoin:1280590254935380038> **Swear Jar!** {message.author.mention} has sworn. That's {swear_jar_data['tally'][user_id_str]} swears so far!")
                return
                
async def setup(bot):
    await bot.add_cog(SwearJar(bot))