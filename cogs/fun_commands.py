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
import google.generativeai as genai

# Define the path to your assets directory
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
QOTD_HISTORY_FILE = os.path.join(utils.DATA_DIR, "qotd_history.json")

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
        if hasattr(self, 'hourly_qotd') and self.hourly_qotd.is_running():
            self.hourly_qotd.cancel()
        if hasattr(self, 'daily_cat_post_task') and self.daily_cat_post_task.is_running():
            self.daily_cat_post_task.cancel()
        if hasattr(self, 'daily_qotd_post') and self.daily_qotd_post.is_running():
            self.daily_qotd_post.cancel()
    
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            guild_id = utils.bot_config.get("MAIN_GUILD_ID")
            guild = self.bot.get_guild(guild_id)
            if guild:
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
                print(f"Successfully synced application commands to guild {guild.name}")
            else:
                await self.bot.tree.sync()
                print("Successfully synced application commands globally.")
        except Exception as e:
            print(f"Failed to sync application commands: {e}")
            
        if not hasattr(self, 'daily_qotd_post') or not self.daily_qotd_post.is_running():
            print("Starting daily QOTD task...")
            self.daily_qotd_post.start()

        if not hasattr(self, 'daily_cat_post_task') or not self.daily_cat_post_task.is_running():
            print("Starting daily cat post task...")
            self.daily_cat_post_task.start()

    @tasks.loop(hours=24)
    async def daily_qotd_post(self):
        """Posts a new AI-generated Question of the Day and tags the QOTD role."""
        if not utils.QOTD_CHANNEL_ID or not utils.QOTD_ROLE_ID:
            print("QOTD channel or role ID is not set. Skipping daily QOTD post.")
            return

        channel = self.bot.get_channel(utils.QOTD_CHANNEL_ID)
        if not channel:
            print(f"Error: QOTD channel with ID {utils.QOTD_CHANNEL_ID} not found.")
            return

        # Use the internal method to generate and send the QOTD
        await self._generate_and_send_qotd(channel, utils.QOTD_ROLE_ID)

    @daily_qotd_post.before_loop
    async def before_daily_qotd_post(self):
        """Waits until the bot is ready before starting the QOTD loop."""
        await self.bot.wait_until_ready()
        print("Daily QOTD task is ready to start.")
        
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
            
            filename = f"cat_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9000)}.{file_extension}"
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

    @app_commands.command(name="boop", description="Boops a member without revealing who did it.")
    @app_commands.describe(member="The member to boop.")
    async def boop(self, interaction: discord.Interaction, member: discord.Member):
        
        boop_gifs = [f"boop{i}.gif" for i in range(1, 5)]
        
        random_gif = random.choice(boop_gifs)
        
        file_path = os.path.join(ASSETS_DIR, random_gif)

        if not os.path.exists(file_path):
            print(f"ERROR: Boop GIF file not found at {file_path}")
            return await interaction.response.send_message("Error: Boop GIF file not found.", ephemeral=True)

        file = discord.File(file_path, filename=random_gif)

        embed = discord.Embed(
            title="Boop!",
            description="You have been booped!",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://{random_gif}")

        await interaction.response.send_message(content=member.mention, embed=embed, file=file)

    @app_commands.command(name="addgif", description="[Staff Only] Creates a new GIF command from a set of URLs.")
    @app_commands.describe(
        name="The name of the new command.",
        url1="URL for the first GIF (mandatory).",
        url2="URL for the second GIF (mandatory).",
        url3="URL for the third GIF (optional).",
        url4="URL for the fourth GIF (optional)."
    )
    @commands.has_permissions(manage_guild=True)
    async def addgif(self, interaction: discord.Interaction, name: str, url1: str, url2: str, url3: Optional[str], url4: Optional[str]):
        await interaction.response.defer(ephemeral=True)
        
        if name in self.bot.tree.get_commands():
            return await interaction.followup.send(f"Error: A command with the name `/{name}` already exists.", ephemeral=True)

        urls = [url1, url2]
        if url3:
            urls.append(url3)
        if url4:
            urls.append(url4)
        
        command_dir = os.path.join(ASSETS_DIR, name)
        if not os.path.exists(command_dir):
            os.makedirs(command_dir)
        
        try:
            for i, url in enumerate(urls, 1):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            file_path = os.path.join(command_dir, f"{name}{i}.gif")
                            with open(file_path, 'wb') as f:
                                while True:
                                    chunk = await response.content.read(1024)
                                    if not chunk:
                                        break
                                    f.write(chunk)
                        else:
                            await interaction.followup.send(f"Failed to download GIF from {url}. Status: {response.status}", ephemeral=True)
                            return
            
            # Use a factory function to create the command
            def create_new_gif_command(command_name, asset_dir):
                @app_commands.command(name=command_name, description=f"Sends a random {command_name} GIF.")
                @app_commands.describe(member=f"The member to {command_name}.")
                async def new_gif_command_logic(interaction: discord.Interaction, member: discord.Member):
                    await interaction.response.defer()
                    gif_files = [f for f in os.listdir(asset_dir) if f.startswith(command_name) and f.endswith(".gif")]
                    if not gif_files:
                        return await interaction.followup.send(f"No GIFs found for the '{command_name}' command.", ephemeral=True)

                    random_gif = random.choice(gif_files)
                    file_path = os.path.join(asset_dir, random_gif)

                    file = discord.File(file_path, filename=random_gif)
                    embed = discord.Embed(
                        title=f"{command_name.capitalize()}!",
                        description=f"{member.mention} has been {command_name}d!",
                        color=discord.Color.blue()
                    )
                    embed.set_image(url=f"attachment://{random_gif}")
                    
                    await interaction.followup.send(content=member.mention, embed=embed, file=file)

                return new_gif_command_logic

            # Create the command and add it to the cog
            new_command_func = create_new_gif_command(name, command_dir)
            self.bot.tree.add_command(new_command_func)

            # Sync the new command to the guild
            guild_id = utils.bot_config.get("MAIN_GUILD_ID")
            guild = self.bot.get_guild(guild_id)
            if guild:
                await self.bot.tree.sync(guild=guild)
                print(f"DEBUG: Synced new command `/{name}` to guild {guild.name}.")
            else:
                await self.bot.tree.sync()
                print(f"DEBUG: Synced new command `/{name}` globally.")
            
            await interaction.followup.send(f"Successfully created the `/{name}` command!", ephemeral=True)

        except Exception as e:
            print(f"DEBUG: Error during command creation or syncing: {e}")
            await interaction.followup.send(f"An error occurred while creating the `/{name}` command. Error: {e}", ephemeral=True)

    # New command to manually send a QOTD
    @app_commands.command(name="sendqotd", description="[Staff Only] Posts a new AI-generated Question of the Day.")
    @commands.has_permissions(manage_guild=True)
    async def send_qotd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not utils.QOTD_CHANNEL_ID or not utils.QOTD_ROLE_ID:
            return await interaction.followup.send("QOTD channel or role ID is not set in bot configuration. Please use `/set_channel` and `/set_role` to configure them.", ephemeral=True)
            
        channel = self.bot.get_channel(utils.QOTD_CHANNEL_ID)
        if not channel:
            return await interaction.followup.send(f"Error: QOTD channel with ID {utils.QOTD_CHANNEL_ID} not found.", ephemeral=True)

        await self._generate_and_send_qotd(channel, utils.QOTD_ROLE_ID, interaction)

    async def _get_recent_qotds(self, limit: int = 10) -> List[str]:
        """Loads and returns the most recent QOTDs from a file."""
        data = utils.load_data(QOTD_HISTORY_FILE, {"history": []})
        return data["history"][-limit:]

    async def _add_recent_qotd(self, question: str):
        """Adds a new question to the QOTD history file."""
        data = utils.load_data(QOTD_HISTORY_FILE, {"history": []})
        data["history"].append(question)
        utils.save_data(data, QOTD_HISTORY_FILE)
        
    async def _generate_and_send_qotd(self, channel: discord.TextChannel, role_id: int, interaction: Optional[discord.Interaction] = None):
        """Internal helper to generate an AI question and send it."""
        if not utils.GEMINI_API_KEY:
            if interaction:
                return await interaction.followup.send("Gemini API key is not set. Cannot generate QOTD.", ephemeral=True)
            print("Gemini API key is not set. Cannot generate QOTD.")
            return

        try:
            recent_qotds = await self._get_recent_qotds()
            recent_text = "; ".join([f"'{q}'" for q in recent_qotds])

            prompt = (
                "Generate a brand-new, creative, and unique Question of the Day. "
                "Rules: "
                "- The question must be a single sentence. "
                "- It must NOT be about feelings, emotions, holidays, or traditions. "
                "- It must NOT repeat or rephrase any recent questions. "
                "- Do not reuse topics, themes, or wording from the recent questions provided. "
                "- The question should be about something interesting, fun, or thought-provoking "
                "(e.g., imagination, creativity, everyday life, science, 'what if' scenarios, etc.). "
                "- Ensure the question is entirely different in theme from the recent ones. "
                f"Here is a list of recently asked questions for context (avoid all of these themes): {recent_text}. "
                "Output only the new question in one sentence."
            )
            
            qotd_text = await utils.generate_text_with_gemini_with_history(
                chat_history=[{"role": "user", "parts": [{"text": prompt}]}]
            )

            if qotd_text:
                qotd_role = channel.guild.get_role(role_id)
                if not qotd_role:
                    if interaction:
                        return await interaction.followup.send(f"Error: QOTD role with ID {role_id} not found.", ephemeral=True)
                    print(f"Error: QOTD role with ID {role_id} not found.")
                    return
                
                embed = discord.Embed(
                    title="Question of the Day!",
                    description=f"**Question:** {qotd_text}",
                    color=discord.Color.gold()
                )

                await channel.send(f"{qotd_role.mention}", embed=embed)
                await self._add_recent_qotd(qotd_text)
                print("Successfully posted AI-generated QOTD.")
                if interaction:
                    await interaction.followup.send("QOTD has been posted successfully!", ephemeral=True)
            else:
                error_message = "I failed to generate a new Question of the Day. Please try again later."
                if interaction:
                    await interaction.followup.send(error_message, ephemeral=True)
                else:
                    await channel.send(error_message)
        except Exception as e:
            error_message = f"An unexpected error occurred during QOTD generation: {e}"
            if interaction:
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                print(error_message)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.active_cat_catch and message.channel.id == self.cat_channel_id and message.content.lower() == 'cat':
            self.active_cat_catch = False
            
            user_inventory = utils.load_inventory(message.author.id)
            has_caught_cat = user_inventory.get('items', {}).get('caught cat', 0) > 0
            
            fish_amount = random.randint(5, 20)
            utils.update_user_money(message.author.id, fish_amount)
            
            if not has_caught_cat:
                utils.add_item_to_inventory(message.author.id, "Caught Cat", {"name": "Caught Cat", "type": "special", "description": "A special item proving you caught a cat."})
                await message.channel.send(f"🎉 **{message.author.display_name}** caught the cat and has added it to their profile! They were also rewarded with {fish_amount} fish! ")
            else:
                await message.channel.send(f"🎉 **{message.author.display_name}** caught the cat again and was rewarded with {fish_amount} fish! 🎣")
            
            return
        
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