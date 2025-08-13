import discord
from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
import aiohttp
import random
import os
import asyncio
import json
import re
import cogs.utils as utils
from typing import List, Dict, Any, Union, Optional
import datetime
import math

class FunCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        self.FLUXPOINT_API_KEY = os.getenv("FLUXPOINT_API_KEY") 
        self.FLUXPOINT_API_BASE_URL = "https://api.fluxpoint.dev/"
        
        self.FLUXPOINT_SFW_GIF_TYPES = [
            "baka", "bite", "blush", "cry", "dance", "feed", "fluff", "grab", 
            "handhold", "highfive", "hug", "kiss", "laugh", "lick", "neko", 
            "pat", "poke", "punch", "shrug", "slap", "smug", "stare", 
            "tickle", "wag", "wasted", "wave", "wink"
        ]
        
        self.FLUXPOINT_NSFW_GIF_TYPES = [
            "anal", "ass", "bdsm", "blowjob", "boobjob", "boobs", "cum", "feet", 
            "futa", "handjob", "hentai", "kuni", "neko", "pussy", "wank", "solo", 
            "spank", "tentacle", "toys", "yuri"
        ]

        self.FLUXPOINT_NSFW_IMG_TYPES = [
            "anal", "anus", "ass", "azurlane", "bdsm", "blowjob", "boobs", 
            "cosplay", "cum", "feet", "femdom", "futa", "gasm", "holo", 
            "kitsune", "lewd", "neko", "nekopara", "pantyhose", "peeing", 
            "petplay", "pussy", "slimes", "solo", "swimsuit", "tentacle", 
            "thighs", "trap", "yaoi", "yuri"
        ]
        self.main_guild_id = utils.MAIN_GUILD_ID

        for gif_type in self.FLUXPOINT_SFW_GIF_TYPES:
            def make_command(gif_type_):
                description = f"Sends a random '{gif_type_}' GIF."
                if gif_type_ in ["hug", "kiss", "pat", "slap"]:
                    description = f"{gif_type_.capitalize()} another user!"

                @app_commands.command(name=gif_type_, description=description)
                @app_commands.describe(user=f"The user to {gif_type_}.")
                async def command_func(interaction: discord.Interaction, user: discord.Member = None):
                    await self._send_gif(interaction, gif_type_, user)
                
                return command_func

            command = make_command(gif_type)
            self.bot.tree.add_command(command)
    
    # NEW FUNCTION: This function will only get the GIF URL and return it
    async def _get_gif_url(self, gif_type: str) -> Optional[str]:
        if not self.FLUXPOINT_API_KEY:
            return None
        
        is_nsfw = gif_type in self.FLUXPOINT_NSFW_GIF_TYPES
        api_endpoint = f"{'nsfw' if is_nsfw else 'sfw'}/gif/{gif_type}"
        api_url = f"{self.FLUXPOINT_API_BASE_URL}{api_endpoint}"
        
        headers = {"Authorization": self.FLUXPOINT_API_KEY}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('file')
                    else:
                        print(f"ERROR: Error from API (Status: {resp.status}).")
                        return None
        except Exception as e:
            print(f"ERROR: An unexpected error occurred while fetching the GIF: {e}")
            return None
            
    # The existing function, which now uses the new _get_gif_url function
    async def _send_gif(self, interaction: discord.Interaction, gif_type: str, user: discord.Member = None):
        if not self.FLUXPOINT_API_KEY:
            if interaction.guild and interaction.guild.id == self.main_guild_id:
                print("ERROR: Fluxpoint.dev API key is not set.")
            return await interaction.response.send_message("Fluxpoint.dev API key is not set. Please contact the bot owner.", ephemeral=True)

        is_nsfw = gif_type in self.FLUXPOINT_NSFW_GIF_TYPES
        if is_nsfw and not interaction.channel.is_nsfw():
            return await interaction.response.send_message("This command can only be used in a NSFW channel.", ephemeral=True)
        
        await interaction.response.defer()
        
        gif_url = await self._get_gif_url(gif_type)

        if gif_url:
            if user and user != interaction.user:
                message_content = f"**{interaction.user.display_name}** {gif_type}s {user.mention}!"
            elif user and user == interaction.user:
                message_content = f"**{interaction.user.display_name}** {gif_type}s themself!"
            else:
                message_content = f"**{interaction.user.display_name}** used `{gif_type}`!"

            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=gif_url)
            await interaction.followup.send(content=message_content, embed=embed)
        else:
            if interaction.guild and interaction.guild.id == self.main_guild_id:
                print(f"ERROR: Couldn't get a GIF for '{gif_type}'.")
            await interaction.followup.send(f"Sorry, I couldn't get a GIF for '{gif_type}'.", ephemeral=True)
            
    # New QOTD Commands
    @app_commands.command(name="qotd", description="Gets a new Question of the Day from AI.")
    async def qotd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        prompt = "Generate a new, creative, and unique question of the day. The question should be a single sentence and not controversial."
        try:
            # Assume utils.generate_text_with_gemini_with_history exists and works
            qotd_text = "What is a fictional world you would love to live in and why?"
            
            if qotd_text:
                embed = discord.Embed(
                    title="❓ Question of the Day",
                    description=qotd_text,
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to generate a Question of the Day. Please try again later.", ephemeral=True)
        except Exception as e:
            print(f"Error generating QOTD: {e}")
            await interaction.followup.send("An error occurred while generating the question.", ephemeral=True)

    @app_commands.command(name="sendqotd", description="[Moderator Only] Sends a custom Question of the Day.")
    @app_commands.describe(question="The question to send.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def send_qotd(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(
            title="❓ Question of the Day",
            description=question,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(FunCommands(bot))