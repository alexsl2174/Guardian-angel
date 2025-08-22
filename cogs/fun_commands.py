# fun_commands.py
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
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
from collections import Counter

class CatSelectView(View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

        cat_select = Select(
            placeholder="Choose a cat photo source...",
            options=[
                discord.SelectOption(label="Random", value="random", description="Get a random cat from the web."),
                discord.SelectOption(label="Server", value="server", description="Get a random cat from the server's collection.")
            ]
        )
        cat_select.callback = self.cat_select_callback
        self.add_item(cat_select)

    async def cat_select_callback(self, interaction: discord.Interaction):
        selected_value = interaction.data['values'][0]
        await interaction.response.defer()

        if selected_value == "random":
            await self.cog._send_random_cat_image(interaction)
        elif selected_value == "server":
            await self.cog._send_server_cat_image(interaction)
        
        # Disable the view after a choice has been made
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)


class FunAndGames(commands.Cog):
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

        # Make a Sentence attributes
        self.make_a_sentence_state = utils.bot_config
        self.current_sentence = self.make_a_sentence_state.get('current_sentence', [])
        
        # Cat-related attributes
        self.cat_channel_id = utils.bot_config.get("CAT_CHANNEL_ID")
        self.daily_cat_cooldown = utils.bot_config.get("DAILY_CAT_COOLDOWN_HOURS", 24)
        self.active_cat_catch = False
        
        self.qotd_channel_id = 829519391168923689
        self.qotd_role_id = 829519296409370654


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
    
    def cog_unload(self):
        self.hourly_qotd.cancel()
        if self.daily_cat_post_task.is_running():
            self.daily_cat_post_task.cancel()
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.hourly_qotd.is_running():
            print("Starting hourly QOTD task...")
            self.hourly_qotd.start()
        
        if not self.daily_cat_post_task.is_running():
            print("Starting daily cat post task...")
            self.daily_cat_post_task.start()
            
    @tasks.loop(hours=1)
    async def daily_cat_post_task(self):
        if not self.cat_channel_id:
            return print("CAT_CHANNEL_ID is not set in bot_config.json. Skipping daily cat post.")

        channel = self.bot.get_channel(self.cat_channel_id)
        if not channel:
            return print(f"Error: Cat channel with ID {self.cat_channel_id} not found.")

        self.active_cat_catch = True
        
        image_url = await self._get_image_url("cat")
        
        if image_url:
            embed = discord.Embed(
                title="A wild cat has appeared! 🐱",
                description="The first person to type 'cat' will catch it!",
                color=discord.Color.dark_purple()
            )
            embed.set_image(url=image_url)
            await channel.send(embed=embed)
            
            await asyncio.sleep(600)
            if self.active_cat_catch:
                self.active_cat_catch = False
                await channel.send("The cat was too fast and got away! 💨")

    @app_commands.command(name="sendcat", description="Sends your cat's photo to be used for the server's cat collection.")
    @app_commands.describe(photo="The photo of your cat.", name="A name for your cat (optional).")
    async def send_cat(self, interaction: discord.Interaction, photo: discord.Attachment, name: Optional[str] = "Unnamed"):
        if not photo.content_type.startswith('image/'):
            return await interaction.response.send_message("That doesn't look like an image!", ephemeral=True)
            
        file_extension = photo.filename.split('.')[-1]
        
        try:
            cat_assets_dir = os.path.join(utils.ASSETS_DIR, "cats")
            if not os.path.exists(cat_assets_dir):
                os.makedirs(cat_assets_dir)
            
            filename = f"cat_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}.{file_extension}"
            file_path = os.path.join(cat_assets_dir, filename)
            
            await photo.save(file_path)
            
            cat_data = utils.load_data(os.path.join(cat_assets_dir, "cats.json"), [])
            cat_data.append({
                "name": name,
                "filename": filename,
                "contributor_id": interaction.user.id,
                "upload_date": datetime.datetime.now().isoformat()
            })
            utils.save_data(cat_data, os.path.join(cat_assets_dir, "cats.json"))
            
            await interaction.response.send_message("Thank you! Your cat has been added to the server collection. You get a bonus of 500 🪙!", ephemeral=True)
            utils.update_user_money(interaction.user.id, 500)
            
        except Exception as e:
            print(f"Error saving cat image: {e}")
            await interaction.response.send_message("An error occurred while saving your cat's photo. Please try again later.", ephemeral=True)
            
    @app_commands.command(name="cat", description="Gets a random cat photo.")
    async def cat(self, interaction: discord.Interaction):
        await interaction.response.send_message("Please select a cat photo source:", view=CatSelectView(self), ephemeral=True)
            
    async def _send_random_cat_image(self, interaction: discord.Interaction):
        image_url = await self._get_image_url("cat")
        if image_url:
            embed = discord.Embed(title="A random cat from the web!", color=discord.Color.dark_purple())
            embed.set_image(url=image_url)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Failed to fetch a random cat image. Try again later.")

    async def _send_server_cat_image(self, interaction: discord.Interaction):
        cat_assets_dir = os.path.join(utils.ASSETS_DIR, "cats")
        cat_data = utils.load_data(os.path.join(cat_assets_dir, "cats.json"), [])
        
        if not cat_data:
            return await interaction.followup.send("The server's cat collection is empty! Use `/sendcat` to add some.")
        
        random_cat = random.choice(cat_data)
        file_path = os.path.join(cat_assets_dir, random_cat['filename'])
        
        if not os.path.exists(file_path):
            return await interaction.followup.send("The selected cat image was not found on the server.")
                
        file = discord.File(file_path, filename=random_cat['filename'])
        embed = discord.Embed(title=f"A server cat named {random_cat['name']}!", color=discord.Color.dark_purple())
        embed.set_image(url=f"attachment://{random_cat['filename']}")
        
        await interaction.followup.send(file=file, embed=embed)
            
    async def _get_image_url(self, image_type: str) -> Optional[str]:
        if not self.FLUXPOINT_API_KEY:
            return None
        
        api_url = f"{self.FLUXPOINT_API_BASE_URL}sfw/img/{image_type}"
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
            print(f"ERROR: An unexpected error occurred while fetching the image: {e}")
            return None
    
    # This is the missing function
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

    # This is the function that sends the QOTD, it has been updated.
    @tasks.loop(hours=24)
    async def hourly_qotd(self):        
        qotd_channel_id = self.qotd_channel_id
        qotd_role_id = self.qotd_role_id
        
        if qotd_channel_id:
            channel = self.bot.get_channel(qotd_channel_id)
            if channel:
                print(f"Attempting to send QOTD to channel ID {qotd_channel_id}")
                try:
                    # Get a random question from a hardcoded list
                    qotd_questions = [
                        "If you could have any superpower, what would it be?",
                        "What is your favorite book and why?",
                        "What's the best concert you've ever been to?",
                        "What's a small thing that makes you happy?",
                        "If you could travel anywhere in the world, where would you go?"
                    ]
                    qotd_text = random.choice(qotd_questions)
                    
                    role_mention = ""
                    if qotd_role_id:
                        role = channel.guild.get_role(qotd_role_id)
                        if role:
                            role_mention = role.mention

                    embed = discord.Embed(
                        title="❓ Question of the Day",
                        description=qotd_text,
                        color=discord.Color.blue()
                    )
                    await channel.send(content=role_mention, embed=embed)
                    print(f"Successfully sent QOTD to channel ID {qotd_channel_id}")
                except Exception as e:
                    print(f"Error sending QOTD in scheduled task: {e}")
            else:
                print(f"ERROR: QOTD channel with ID {qotd_channel_id} not found.")
        else:
            print("ERROR: QOTD_CHANNEL_ID not set in bot_config.json.")

    @app_commands.command(name="qotd", description="Gets a new Question of the Day from AI.")
    async def qotd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        prompt = "Generate a new, creative, and unique question of the day. The question should be a single sentence and not controversial."
        try:
            qotd_text = await utils.generate_text_with_gemini_with_history(
                chat_history=[{"role": "user", "parts": [{"text": prompt}]}]
            )
            
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Cat-catching logic
        if self.active_cat_catch and message.channel.id == self.cat_channel_id and message.content.lower() == 'cat':
            self.active_cat_catch = False
            
            user_inventory = utils.load_inventory(message.author.id)
            has_caught_cat = user_inventory.get('items', {}).get('caught cat', 0) > 0
            
            fish_amount = random.randint(5, 20)
            utils.update_user_money(message.author.id, fish_amount)
            
            if not has_caught_cat:
                utils.add_item_to_inventory(message.author.id, "Caught Cat", {"name": "Caught Cat", "type": "special", "description": "A special item proving you caught a cat."})
                await message.channel.send(f"🎉 **{message.author.display_name}** caught the cat and has added it to their profile! They were also rewarded with {fish_amount} fish! 🎣")
            else:
                await message.channel.send(f"🎉 **{message.author.display_name}** caught the cat again and was rewarded with {fish_amount} fish! 🎣")
            
            return
        
        # Make a sentence logic
        print(f"Received message in channel: {message.channel.id} from user: {message.author.id}")
        
        make_a_sentence_channel_id = utils.bot_config.get('make_a_sentence_channel_id')
        sinner_chat_channel_id = utils.bot_config.get('SINNER_CHAT_CHANNEL_ID', utils.TEST_CHANNEL_ID)
        
        print(f"Configured make_a_sentence_channel_id: {make_a_sentence_channel_id}")

        if make_a_sentence_channel_id is None or message.author.bot or message.channel.id != make_a_sentence_channel_id:
            print("Message ignored: not in the correct channel or from a bot.")
            return

        content = message.content.strip()
        words = content.split()
        
        if len(words) != 1:
            print("Multiple words detected. Deleting message.")
            try:
                await message.delete()
                await message.channel.send("Please type only one word at a time!", delete_after=5)
            except discord.Forbidden:
                print("Could not delete message. Bot lacks permissions.")
            return

        word = words[0]
        self.current_sentence.append(word)
        print(f"Current sentence state: {self.current_sentence}")
        
        if word.endswith(('.', '!', '?')) or len(word) == 1 and word in '.,!?':
            finished_sentence = " ".join(self.current_sentence)
            print(f"Sentence finished with punctuation. Full sentence: '{finished_sentence}'")
            
            # This is the updated section
            try:
                finished_channel = await self.bot.fetch_channel(sinner_chat_channel_id)
                print(f"Successfully fetched finished channel: {finished_channel.name}")
            except discord.NotFound:
                finished_channel = None
                print(f"Error: Sinner Chat channel with ID {sinner_chat_channel_id} not found.")

            if finished_channel:
                embed = discord.Embed(
                    title="Make A Sentence",
                    description=finished_sentence,
                    color=discord.Color.blue()
                )
                await finished_channel.send(embed=embed)
                print("Successfully sent message with title to finished channel.")
            else:
                await message.channel.send(f"**Finished sentence:** {finished_sentence}")
                print("Could not find finished channel. Posting to current channel instead.")
                
            self.current_sentence = []
        
        utils.bot_config['current_sentence'] = self.current_sentence
        utils.save_data(utils.bot_config, utils.BOT_CONFIG_FILE)
        print("Updated sentence state saved to bot_config.json.")
        
        await message.add_reaction("✅")

async def setup(bot):
    await bot.add_cog(FunAndGames(bot))
