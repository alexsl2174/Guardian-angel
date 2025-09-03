import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import random
import datetime
import os
import asyncio
import sys
import traceback
from typing import List, Dict, Any, Union, Optional
import re

# Import shared utility functions and global configurations
import cogs.utils as utils

# Define the path to the data directory, now local to this cog's file.
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
REWARDS_FILE = os.path.join(DATA_DIR, 'rewards.json')
BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")
ADVENTURE_AI_RESTRICTIONS_FILE = os.path.join(DATA_DIR, 'adventure_ai_restrictions.txt')
ANAGRAM_GAME_STATE_FILE = os.path.join(DATA_DIR, 'anagram_game_state.json')
ANAGRAM_WORDS_FILE = os.path.join(DATA_DIR, 'anagram_words.json')
BUMP_BATTLE_STATE_FILE = os.path.join(DATA_DIR, 'bump_battle_state.json')
SORRY_JAR_FILE = os.path.join(DATA_DIR, 'swear_jar.json')
BOOSTER_REWARDS_FILE = os.path.join(DATA_DIR, "booster_rewards.json")

# Helper functions for data persistence, now located in this file.
def _load_data(file_path: str, default_value: Any = None) -> Any:
    """Loads data from a JSON file, returning a default value if the file is not found or is corrupted."""
    if not os.path.exists(file_path):
        return default_value if default_value is not None else {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error in {file_path}: {e}. Returning default value.")
        return default_value if default_value is not None else {}
    except Exception as e:
        print(f"Error loading data from {file_path}: {e}. Returning default value.")
        return default_value if default_value is not None else {}

def _save_data(data: Any, file_path: str):
    """Saves data to a JSON file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")

# This class defines the interactive View with buttons.
class BumpBattleView(discord.ui.View):
    def __init__(self, win_embed: discord.Embed, leaderboard_embed: discord.Embed, timeout: Optional[float] = 180.0):
        super().__init__(timeout=timeout)
        self.win_embed = win_embed
        self.leaderboard_embed = leaderboard_embed
        self.current_page = 0  # 0 for win embed, 1 for leaderboard embed

    # Left arrow button to go back to the win announcement
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, disabled=True)
    async def left_arrow(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        button.disabled = True
        self.children[1].disabled = False  # Enable right arrow
        await interaction.response.edit_message(embed=self.win_embed, view=self)

    # Right arrow button to switch to the leaderboard
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def right_arrow(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        button.disabled = True
        self.children[0].disabled = False  # Enable left arrow
        await interaction.response.edit_message(embed=self.leaderboard_embed, view=self)

# New class for the replay button
class AnagramReplayView(discord.ui.View):
    def __init__(self, cog: 'Economy'):
        super().__init__(timeout=300) # Timeout after 5 minutes
        self.cog = cog

    @discord.ui.button(label="Replay", style=discord.ButtonStyle.green, emoji="🔁")
    async def replay_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Starting a new anagram game!", ephemeral=True)
        button.disabled = True
        await interaction.message.edit(view=self)
        anagram_channel_id = self.cog.anagram_game_state.get('channel_id')
        if anagram_channel_id:
            await self.cog._start_new_anagram_game_instance(anagram_channel_id)


async def is_moderator(interaction: discord.Interaction) -> bool:
    """Checks if the user has a Staff role."""
    staff_roles = utils.ROLE_IDS.get("Staff")
    if not staff_roles:
        return False
    
    # Ensure staff_roles is a list to handle both single ID and list of IDs
    if not isinstance(staff_roles, list):
        staff_roles = [staff_roles]

    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in staff_roles)


class Economy(commands.Cog):
    """A cog for the bot's core economy commands and leaderboards."""

    def __init__(self, bot):
        self.bot = bot
        self.main_guild_id = utils.MAIN_GUILD_ID
        self.anagram_game_state = _load_data(ANAGRAM_GAME_STATE_FILE, {})
        self.anagram_words = _load_data(ANAGRAM_WORDS_FILE, {}).get("words", [])
        self.bump_battle_state = _load_data(BUMP_BATTLE_STATE_FILE, {})
        
        # Hard-coded channel and role IDs
        self.bump_battle_channel_id = utils.bot_config.get("BUMP_BATTLE_CHANNEL_ID")
        self.vote_channel_id = utils.bot_config.get("VOTE_CHANNEL_ID")
        self.announcements_channel_id = utils.bot_config.get("ANNOUNCEMENTS_CHANNEL_ID")
        self.bump_channel_id = utils.bot_config.get("BUMP_CHANNEL_ID") 
        
        # Define cooldown times in seconds
        self.BUMP_COOLDOWN = 120
        self.POINT_COOLDOWN = 120
        self.VOTE_COOLDOWN = 360
        self.disboard_cooldown_seconds = 2 * 60 * 60 # 2 hours
        
    @commands.Cog.listener()
    async def on_ready(self):
        # This listener is called when the cog is loaded and the bot is ready.
        # It ensures that the anagram game task starts after the bot is connected.
        self.anagram_game_task.start()
        print("Anagram game task started.")
    
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        # Handle the bumppoint cooldown error specifically
        if isinstance(error, commands.CommandOnCooldown) and interaction.command.name == "bumppoint":
            slap_gif_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'slap.gif')
            
            # Use try-except to handle potential file not found errors
            try:
                file = discord.File(slap_gif_path, filename='slap.gif')
            except FileNotFoundError:
                print(f"Error: slap.gif not found at {slap_gif_path}")
                file = None
            
            embed = discord.Embed(
                title="Don't get too excited!",
                description=f"You can only use this command once per Disboard/Discodus bump. Please wait another {int(error.retry_after)} seconds before trying again.",
                color=discord.Color.red()
            )
            
            if file:
                embed.set_image(url="attachment://slap.gif")
                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Fallback for other command errors
        print(f"Ignoring exception in command {interaction.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


    # --- Anagram Game Command and Loop ---
    @app_commands.command(name="start_anagram_game", description="Starts a new Anagram game immediately.")
    async def start_anagram_game(self, interaction: discord.Interaction):
        """Starts a new anagram game immediately."""
        anagram_channel_id = self.anagram_game_state.get('channel_id')
        if not anagram_channel_id:
            await interaction.response.send_message("The anagram channel is not set. Please use an admin command to set it first.", ephemeral=True)
            return

        if self.anagram_game_state.get('current_word'):
            await interaction.response.send_message("An anagram game is already in progress.", ephemeral=True)
            return

        await interaction.response.send_message("Starting a new anagram game now!", ephemeral=True)
        # Manually trigger the task to start a game now
        await self.anagram_game_task()

    @app_commands.command(name="reset_anagram", description="[Moderator Only] Resets the current anagram game state.")
    @app_commands.check(is_moderator)
    async def reset_anagram(self, interaction: discord.Interaction):
        """Resets the current anagram game state."""
        await interaction.response.defer(ephemeral=True)

        # Clear the game state
        if self.anagram_game_state.get('current_word'):
            self.anagram_game_state['current_word'] = None
            _save_data(self.anagram_game_state, ANAGRAM_GAME_STATE_FILE)
            self.anagram_game_task.restart()
            await interaction.followup.send("The anagram game has been reset and a new one will begin shortly.", ephemeral=True)
        else:
            await interaction.followup.send("There is no anagram game currently in progress to reset.", ephemeral=True)

    async def _start_new_anagram_game_instance(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Anagram task failed: Channel with ID {channel_id} not found.")
            return

        # Use the AI to generate a new word
        word = await utils.generate_anagram_word_with_gemini()
        if not word:
            # Fallback to the hardcoded list if AI fails
            if not self.anagram_words:
                await channel.send("Sorry, I couldn't generate a new anagram word right now. The word list is empty.")
                return
            word = random.choice(self.anagram_words)
            await channel.send("The AI failed to generate a new word, falling back to a pre-defined list.")

        shuffled_word = "".join(random.sample(word, len(word)))

        self.anagram_game_state['current_word'] = word
        self.anagram_game_state['shuffled_word'] = shuffled_word
        self.anagram_game_state['channel_id'] = channel_id
        _save_data(self.anagram_game_state, ANAGRAM_GAME_STATE_FILE)

        embed = discord.Embed(
            title="Game = Anagram",
            description=f"Guess the word: **{shuffled_word}** in 4 minutes",
            color=discord.Color.purple()
        )
        await channel.send(embed=embed)


    @tasks.loop(hours=1)
    async def anagram_game_task(self):
        """This task runs every hour to start a new anagram game."""
        anagram_channel_id = utils.bot_config.get('ANAGRAM_CHANNEL_ID')
        if not anagram_channel_id:
            return

        self.anagram_game_state = _load_data(ANAGRAM_GAME_STATE_FILE, {})
        if self.anagram_game_state.get('current_word'):
            print("Anagram task skipped: A game is already in progress.")
            return
        
        await self._start_new_anagram_game_instance(anagram_channel_id)

        await asyncio.sleep(240)

        current_anagram_state = _load_data(ANAGRAM_GAME_STATE_FILE, {})
        if current_anagram_state.get('current_word'):
            channel = self.bot.get_channel(current_anagram_state.get('channel_id'))
            if channel:
                # Send a message with the replay button after the game ends
                embed = discord.Embed(
                    title="Time's up!",
                    description=f"The correct answer was **{current_anagram_state['current_word']}**.",
                    color=discord.Color.red()
                )
                await channel.send(embed=embed, view=AnagramReplayView(self))
            current_anagram_state['current_word'] = None
            _save_data(current_anagram_state, ANAGRAM_GAME_STATE_FILE)


    # --- Economy Commands ---
    @app_commands.command(name="balance", description="Checks your or another member's coin balance.")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        """Displays the coin balance of a member."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        member = member or interaction.user
        wallet_balance = utils.get_user_money(member.id)
        bank_balance = utils.get_user_bank_money(member.id)
        
        embed = discord.Embed(
            title=f"Balance for {member.display_name}",
            description=f"**Wallet:** `{wallet_balance}` <a:starcoin:1280590254935380038>\n**Bank:** `{bank_balance}` <a:starcoin:1280590254935380038>",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else member.default_avatar.url)

        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="deposit", description="Deposits money from your wallet to your bank.")
    @app_commands.describe(amount="The amount of money to deposit. Use 'all' to deposit everything.")
    async def deposit(self, interaction: discord.Interaction, amount: str):
        """Deposits a specified amount of money from the user's wallet to their bank."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = interaction.user.id
        wallet_balance = utils.get_user_money(user_id)

        if amount.lower() == 'all':
            deposit_amount = wallet_balance
        else:
            try:
                deposit_amount = int(amount)
            except ValueError:
                await interaction.response.send_message("You must deposit a positive number or 'all'.", ephemeral=True)
                return

        if deposit_amount <= 0:
            await interaction.response.send_message("You must deposit a positive amount.", ephemeral=True)
            return
        if deposit_amount > wallet_balance:
            await interaction.response.send_message(f"You don't have that much money in your wallet! You only have {wallet_balance} <a:starcoin:1280590254935380038>.", ephemeral=True)
            return

        utils.transfer_money(user_id, deposit_amount, 'wallet', 'bank')
        await interaction.response.send_message(f"Successfully deposited {deposit_amount} <a:starcoin:1280590254935380038> into your bank. Your new wallet balance is {utils.get_user_money(user_id)} <a:starcoin:1280590254935380038>.", ephemeral=True)

    @app_commands.command(name="withdraw", description="Withdraws money from your bank to your wallet.")
    @app_commands.describe(amount="The amount of money to withdraw. Use 'all' to withdraw everything.")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        """Withdraws a specified amount of money from the user's bank to their wallet."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = interaction.user.id
        bank_balance = utils.get_user_bank_money(user_id)

        if amount.lower() == 'all':
            withdraw_amount = bank_balance
        else:
            try:
                withdraw_amount = int(amount)
            except ValueError:
                await interaction.response.send_message("You must withdraw a positive number or 'all'.", ephemeral=True)
                return

        if withdraw_amount <= 0:
            await interaction.response.send_message("You must withdraw a positive amount.", ephemeral=True)
            return
        if withdraw_amount > bank_balance:
            await interaction.response.send_message(f"You don't have that much money in your bank! You only have {bank_balance} <a:starcoin:1280590254935380038>.", ephemeral=True)
            return

        utils.transfer_money(user_id, withdraw_amount, 'bank', 'wallet')
        await interaction.response.send_message(f"Successfully withdrew {withdraw_amount} <a:starcoin:1280590254935380038> from your bank. Your new bank balance is {utils.get_user_bank_money(user_id)} <a:starcoin:1280590254935380038>.", ephemeral=True)

    @app_commands.command(name="coinflip", description="Flip a coin and bet money.")
    @app_commands.describe(side="Heads or Tails", bet_amount="The amount of money to bet.")
    @app_commands.choices(side=[
        app_commands.Choice(name="Heads", value="head"),
        app_commands.Choice(name="Tails", value="tail")
    ])
    async def coinflip(self, interaction: discord.Interaction, side: app_commands.Choice[str], bet_amount: int):
        """Flips a coin and pays out if the user guesses correctly."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = interaction.user.id
        current_money = utils.get_user_money(user_id)

        if bet_amount <= 0:
            await interaction.response.send_message("You must bet a positive amount.", ephemeral=True)
            return
        if bet_amount > current_money:
            await interaction.response.send_message(f"You can't bet more than your balance! You have {current_money} <a:starcoin:1280590254935380038>.", ephemeral=True)
            return

        coin_sides = ["head", "tail"]
        flip_result = random.choice(coin_sides)

        embed = discord.Embed(title=f"Coin Flip Bet")
        embed.add_field(name="Your Choice", value=side.name, inline=False)
        embed.add_field(name="You Bet", value=f"<a:starcoin:1280590254935380038> {bet_amount}", inline=False)
        embed.add_field(name="The Coin Flipped to", value=flip_result.capitalize(), inline=False)
        embed.set_footer(text=f"Requested By: {interaction.user.display_name}")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1243305449608974436/1355277240115659084/886186258324410378-ezgif.com-rotatew.gif")

        if side.value == flip_result:
            winnings = bet_amount
            utils.update_user_money(user_id, winnings)
            embed.add_field(name="Result", value=f"🎉 You won! You earned {winnings} <a:starcoin:1280590254935380038>.", inline=False)
            embed.color = discord.Color.green()
        else:
            losses = bet_amount
            utils.update_user_money(user_id, -losses)
            embed.add_field(name="Result", value=f"💔 You lost! You lost {losses} <a:starcoin:1280590254935380038>.", inline=False)
            embed.color = discord.Color.red()
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Collect your daily reward!")
    @app_commands.checks.cooldown(1, 24*60*60)
    async def daily(self, interaction: discord.Interaction):
        """Allows a user to claim their daily coin reward."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = interaction.user.id
        
        reward_min = 200
        reward_max = 500
        reward = random.randint(reward_min, reward_max)
        
        utils.update_user_money(user_id, reward)
        
        daily_phrases = [
            "received a lifetime supply of imaginary friends.",
            "found a hidden treasure map to a fictional treasure.",
            "won a coupon for a free unicorn ride in a parallel universe.",
            "discovered a jar of infinite pickles.",
            "earned a certificate for being the world's best imaginary chef.",
            "obtained a voucher for a free trip to the land of make-believe.",
            "acquired a magical remote control that can pause reality.",
            "gained access to a secret club where all the members are invisible.",
            "received a pet rock that grants three wishes (rock wishes not guaranteed).",
            "unlocked a portal to a dimension filled with laughter and fun."
        ]
        daily_phrase = random.choice(daily_phrases)

        embed = discord.Embed(
            description=f"You {daily_phrase}\n\nYou got **{reward}** <a:starcoin:1280590254935380038> for your daily reward!",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Next Daily:")
        next_available_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=24*60*60)
        embed.timestamp = next_available_time

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="crime", description="Attempt a crime for money!")
    @app_commands.checks.cooldown(1, 2*60*60)
    async def crime(self, interaction: discord.Interaction):
        """Attempts a crime, with a chance of winning or losing money."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = interaction.user.id
        current_money = utils.get_user_money(user_id)
        
        min_amount = 10
        if current_money < min_amount:
            await interaction.response.send_message(f"You need to have at least {min_amount} <a:starcoin:1280590254935380038> to start a crime.", ephemeral=True)
            return
        
        # Defining amount here ensures it is available in both branches.
        amount = random.randint(min_amount, current_money)
        outcome = random.choices(['free', 'caught'], weights=[80, 20], k=1)[0]
        
        embed = discord.Embed(title="Crime")
        
        crime_phrases = [
            "successfully robbed a bank and escaped with the loot!",
            "hacked into a high-security system and made off with valuable data.",
            "pulled off a daring heist, stealing priceless artwork from a museum.",
            "conducted a clever con, swindling a wealthy tycoon out of a small fortune.",
            "engaged in a black market operation, selling rare and illicit goods.",
            "carried out a smooth diamond heist, leaving investigators baffled.",
            "orchestrated an elaborate smuggling operation, smuggling contraband across borders.",
            "executed a precision jewelry store robbery, leaving no trace behind.",
            "performed a daring midnight break-in, stealing classified documents.",
            "successfully infiltrated a high-profile event, lifting wallets from unsuspecting guests."
        ]
        bad_crime_phrases = [
            "got caught red-handed and ended up in handcuffs.",
            "tripped the alarm during a bank robbery attempt and had to flee empty-handed.",
            "accidentally triggered a security system, alerting authorities to the break-in.",
            "made a critical mistake that led to being apprehended by an alert security guard.",
            "failed to crack the safe and left behind frustrated and empty-handed.",
            "got tangled in laser security and set off alarms, attracting attention.",
            "attempted a high-tech hack but triggered a system lockdown, leaving empty pockets.",
            "fell into a trap set by an undercover police officer, resulting in immediate arrest.",
            "mistakenly grabbed a decoy bag of money, leaving the real loot behind.",
            "tried to pickpocket an undercover officer and ended up being caught in the act."
        ]

        if outcome == 'free':
            utils.update_user_money(user_id, amount)
            # Use AI to generate a phrase, with a fallback to the hardcoded list
            phrase = await utils.generate_crime_phrase_with_gemini(is_success=True) or random.choice(crime_phrases)
            embed.description = f"You {phrase}. You earned **{amount}** <a:starcoin:1280590254935380038>!"
            embed.color = discord.Color.green()
        else:
            utils.update_user_money(user_id, -amount)
            # Use AI to generate a phrase, with a fallback to the hardcoded list
            phrase = await utils.generate_crime_phrase_with_gemini(is_success=False) or random.choice(bad_crime_phrases)
            embed.description = f"You {phrase}. You lost **{amount}** <a:starcoin:1280590254935380038>!"
            embed.color = discord.Color.red()
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rob", description="Attempt to rob another user!")
    @app_commands.describe(target="The member you want to rob.")
    @app_commands.checks.cooldown(1, 12*60*60)
    async def rob(self, interaction: discord.Interaction, target: discord.Member):
        """Attempts to rob another user for a portion of their coins."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
            
        user_id = interaction.user.id
        target_id = target.id

        if user_id == target_id:
            await interaction.response.send_message("You cannot rob yourself!", ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message("You cannot rob a bot!", ephemeral=True)
            return

        robber_money = utils.get_user_money(user_id)
        target_money = utils.get_user_bank_money(target_id)

        if target_money < 2000:
            await interaction.response.send_message(f"That user doesn't have enough money in their bank to rob! They need at least 2000 <a:starcoin:1280590254935380038>.", ephemeral=True)
            return
        if robber_money < 3000:
            await interaction.response.send_message(f"You need at least 3000 <a:starcoin:1280590254935380038> to rob someone!", ephemeral=True)
            return

        outcome = random.choices(['free', 'caught'], weights=[80, 20], k=1)[0]

        embed = discord.Embed(title="Robbery Attempt")
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        if outcome == 'free':
            amount = random.randint(1, target_money)
            utils.transfer_money(target_id, amount, 'bank', 'wallet')
            utils.update_user_money(user_id, amount)
            
            embed.description = f"{interaction.user.mention} robbed {target.mention} and successfully got **{amount}** <a:starcoin:1280590254935380038>!"
            embed.color = discord.Color.green()
        else:
            losses = random.randint(1, robber_money)
            utils.update_user_money(user_id, -losses)
            embed.description = "👮 You got Caught! You gained nothing."
            embed.color = discord.Color.red()
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="work", description="Work for some money!")
    @app_commands.checks.cooldown(1, 24*60*60)
    async def work(self, interaction: discord.Interaction):
        """Allows a user to work for a random amount of money, with a chance of failure."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = interaction.user.id
        
        reward = random.randint(200, 3000)
        outcome = random.choice([1, 2])
        
        embed = discord.Embed(title="Work Outcome")
        
        good_work_phrases = [
            "worked as a chef in a bustling restaurant kitchen",
            "delivered pizzas with lightning-fast speed",
            "worked as a barista, crafting perfect cups of coffee",
            "assisted customers as a friendly retail associate",
            "managed inventory as a diligent warehouse worker",
            "answered customer calls with a smile as a call center representative",
            "worked as a diligent office assistant, keeping things organized",
            "provided friendly service as a cashier at the local grocery store",
            "worked as a skilled mechanic, fixing cars with expertise",
            "showed creativity as a graphic designer, crafting stunning visuals"
        ]
        bad_work_phrases = [
            "spilled coffee on the boss's new suit and were fired on the spot",
            "delivered a pizza to the wrong house, and the customer refused to pay",
            "dropped a tray of drinks on a celebrity, and now you owe them a new outfit",
            "accidentally broke a priceless vase in the retail store and had to pay for it",
            "caused a warehouse-wide system crash and lost your job",
            "told a customer their call was a waste of time and got an earful from your manager",
            "lost an important file and had to pay for its replacement",
            "gave a customer too much change and had to pay the difference out of pocket",
            "messed up a simple oil change, and the car blew a tire",
            "accidentally used a rival company's logo on a new project and were fined"
        ]

        if outcome == 1:
            utils.update_user_money(user_id, reward)
            # Use AI to generate a phrase, with a fallback to the hardcoded list
            phrase = await utils.generate_work_phrase_with_gemini(is_success=True) or random.choice(good_work_phrases)
            embed.description = f"You {phrase}. You earned **{reward}** <a:starcoin:1280590254935380038>!"
            embed.color = discord.Color.green()
        else:
            utils.update_user_money(user_id, -reward)
            # Use AI to generate a phrase, with a fallback to the hardcoded list
            phrase = await utils.generate_work_phrase_with_gemini(is_success=False) or random.choice(bad_work_phrases)
            embed.description = f"You {phrase}. You lost **{reward}** <a:starcoin:1280590254935380038>!"
            embed.color = discord.Color.red()
        
        await interaction.response.send_message(embed=embed)
    
    # --- New Unified Leaderboard Command ---
    @app_commands.command(name="leaderboard", description="Shows the top users for a specific game or metric.")
    @app_commands.describe(
        board="The leaderboard you want to view."
    )
    @app_commands.choices(board=[
        app_commands.Choice(name="Coins", value="coins"),
        app_commands.Choice(name="Bug Book", value="bugbook"),
        app_commands.Choice(name="Swear Tally", value="swears"),
        app_commands.Choice(name="Bumps", value="bumps"),
        app_commands.Choice(name="Sorry Tally", value="sorry"),
        app_commands.Choice(name="Hangry Games", value="hangry")
    ])
    async def leaderboard(self, interaction: discord.Interaction, board: str):
        """Displays the top users by a selected metric."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
        
        await interaction.response.defer()

        guild = interaction.guild
        
        if board == "coins":
            embed = discord.Embed(title=f"{guild.name}'s Leaderboard (Top Coins)", color=discord.Color.gold())
            balances = _load_data(BALANCES_FILE)
            leaderboard_entries = []
            for user_id_str, money in balances.items():
                if isinstance(money, dict):
                    total_money = money.get("wallet", 0) + money.get("bank", 0)
                else:
                    total_money = money
                
                if total_money > 0:
                    member = guild.get_member(int(user_id_str))
                    if member:
                        leaderboard_entries.append((member.display_name, total_money))
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)
            
            description = "\n".join([f"{i+1}. **{name}** - {money} <a:starcoin:1280590254935380038>" for i, (name, money) in enumerate(leaderboard_entries[:10])])
            embed.description = description if description else "Leaderboard is currently empty!"
            await interaction.followup.send(embed=embed)
            
        elif board == "bugbook":
            embed = discord.Embed(title=f"{guild.name}'s Leaderboard (Bug Collectors)", color=discord.Color.gold())
            bug_collection = utils.load_bug_collection()
            leaderboard_entries = []
            for user_id_str, user_data in bug_collection.items():
                member = guild.get_member(int(user_id_str))
                if member:
                    unique_bugs = len(user_data.get('caught', []))
                    leaderboard_entries.append((member.display_name, unique_bugs))
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)

            description = "\n".join([f"{i+1}. **{name}** - {count} unique bugs" for i, (name, count) in enumerate(leaderboard_entries[:10])])
            embed.description = description if description else "Bug Book is currently empty!"
            await interaction.followup.send(embed=embed)

        elif board == "swears":
            embed = discord.Embed(title=f"{guild.name}'s Leaderboard (Swear Tally)", color=discord.Color.gold())
            swear_jar_data = _load_data(SORRY_JAR_FILE, {'words': [], 'tally': {}})
            tally = swear_jar_data.get('tally', {})
            leaderboard_entries = []
            for user_id_str, count in tally.items():
                member = guild.get_member(int(user_id_str))
                if member:
                    leaderboard_entries.append((member.display_name, count))
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)

            description = "\n".join([f"{i+1}. **{name}** - {count} swears" for i, (name, count) in enumerate(leaderboard_entries[:10])])
            embed.description = description if description else "The swear jar is empty!"
            await interaction.followup.send(embed=embed)
            
        elif board == "bumps":
            bump_battle_state = _load_data(BUMP_BATTLE_STATE_FILE, {})
            sub_users = bump_battle_state.get('sub', {}).get('users', {})
            dom_users = bump_battle_state.get('dom', {}).get('users', {})
            
            # Sub Team Leaderboard
            sub_leaderboard = []
            for user_id, count in sub_users.items():
                member = guild.get_member(int(user_id))
                if member:
                    sub_leaderboard.append((member.display_name, count))
            sub_leaderboard.sort(key=lambda x: x[1], reverse=True)
            
            sub_description = "\n".join([f"{i+1}. **{name}** - {count} <a:bluecoin:1280590252817387593>" for i, (name, count) in enumerate(sub_leaderboard[:10])])
            sub_embed = discord.Embed(
                title=f"Sub Team Leaderboard",
                description=sub_description if sub_description else "No one has bumped yet!",
                color=discord.Color.blue()
            )
            
            # Dom Team Leaderboard
            dom_leaderboard = []
            for user_id, count in dom_users.items():
                member = guild.get_member(int(user_id))
                if member:
                    dom_leaderboard.append((member.display_name, count))
            dom_leaderboard.sort(key=lambda x: x[1], reverse=True)
            
            dom_description = "\n".join([f"{i+1}. **{name}** - {count} <a:bluecoin:1280590252817387593>" for i, (name, count) in enumerate(dom_leaderboard[:10])])
            dom_embed = discord.Embed(
                title=f"Dom Team Leaderboard",
                description=dom_description if dom_description else "No one has bumped yet!",
                color=discord.Color.red()
            )
            
            await interaction.followup.send(embeds=[sub_embed, dom_embed])
            
        elif board == "sorry":
            # Change the title here
            embed = discord.Embed(title="Who is the most sorry server member?", color=discord.Color.gold())
            sorry_jar_data = _load_data(SORRY_JAR_FILE, {'words': [], 'tally': {}})
            leaderboard_entries = []
            for user_id_str, count in sorry_jar_data.items():
                # Skip the last apology timestamps
                if user_id_str.endswith('_last_apology') or user_id_str == 'words':
                    continue
                member = guild.get_member(int(user_id_str))
                if member:
                    leaderboard_entries.append((member.display_name, count))
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)

            description = "\n".join([f"{i+1}. **{name}** - {count} apologies" for i, (name, count) in enumerate(leaderboard_entries[:10])])
            embed.description = description if description else "The sorry jar is empty!"
            
            # Add the image from the assets folder
            file = discord.File(os.path.join(os.path.dirname(__file__), '..', 'assets', 'sorryjar.png'), filename="sorryjar.png")
            embed.set_thumbnail(url="attachment://sorryjar.png")
            
            await interaction.followup.send(embed=embed, file=file)

        elif board == "hangry":
            # You will need to add a similar `load_hangry_games_teams_state` to your `cogs/utils.py`
            # or copy the one provided in the previous response.
            hangry_games_state = utils.load_hangry_games_teams_state()
            
            embeds = []
            
            # Create a combined leaderboard for the Hangry Games
            sub_points = hangry_games_state.get('sub', {}).get('points', 0)
            dom_points = hangry_games_state.get('dom', {}).get('points', 0)

            dom_embed = discord.Embed(
                title="Insufferable Doms 🍕",
                description=f"Current points: **{dom_points}**",
                color=discord.Color.red()
            )
            embeds.append(dom_embed)
            
            sub_embed = discord.Embed(
                title="Fantastic Brats 🍔",
                description=f"Current points: **{sub_points}**",
                color=discord.Color.blue()
            )
            embeds.append(sub_embed)

            await interaction.followup.send(embeds=embeds)

        else:
            embed = discord.Embed(description="Invalid leaderboard type specified.", color=discord.Color.red())
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="sorryjar", description="Shows your current sorry tally with a picture.")
    async def sorryjar(self, interaction: discord.Interaction):
        """Displays the user's current sorry jar tally with a picture."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        
        user_id_str = str(interaction.user.id)
        sorry_jar_data = _load_data(SORRY_JAR_FILE, {'words': [], 'tally': {}})
        
        tally = sorry_jar_data.get(user_id_str, 0)

        embed = discord.Embed(
            title=f"The Sorry Jar for {interaction.user.display_name}",
            description=f"You have said 'sorry' **{tally}** times.",
            color=discord.Color.blue()
        )
        
        # Load the image from the assets folder
        file = discord.File(os.path.join(os.path.dirname(__file__), '..', 'assets', 'sorryjar.png'), filename="sorryjar.png")
        embed.set_image(url="attachment://sorryjar.png")

        await interaction.followup.send(embed=embed, file=file)
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # Anagram game logic
        anagram_state = _load_data(ANAGRAM_GAME_STATE_FILE, {})
        if message.channel.id == anagram_state.get('channel_id'):
            print(f"DEBUG: Message in anagram channel from {message.author.name}. Content: '{message.content}'.")
            correct_word = anagram_state.get('current_word')
            if correct_word and message.content.lower() == correct_word.lower():
                user_id = str(message.author.id)
                utils.update_user_money(user_id, 250)
                
                # New embed format
                embed = discord.Embed(
                    title="Time's up!",
                    description=f"🎉 {message.author.mention} is correct! The word was **{correct_word}** and they have been awarded 250 <a:starcoin:1280590254935380038>!",
                    color=discord.Color.green()
                )
                
                await message.channel.send(embed=embed, view=AnagramReplayView(self))
                
                anagram_state['current_word'] = None
                _save_data(anagram_state, ANAGRAM_GAME_STATE_FILE)
                
                self.anagram_game_task.restart()
                print(f"DEBUG: Anagram game won by {message.author.name}. Restarting task.")

        # Sorry Jar logic
        if re.search(r'\b(sorry)\b', message.content.lower()):
            sorry_jar_data = _load_data(SORRY_JAR_FILE, {'words': [], 'tally': {}})
            user_id_str = str(message.author.id)
            
            if user_id_str not in sorry_jar_data:
                sorry_jar_data[user_id_str] = 0
            
            sorry_jar_data[user_id_str] += 1
            _save_data(sorry_jar_data, SORRY_JAR_FILE)
            
            # Send the full embed response every time a message is sent.
            tally = sorry_jar_data.get(user_id_str, 0)
            
            embed = discord.Embed(
                title="✨ Sorry Jar ✨",
                description="Keeping track of the times you say Sorry.",
                color=discord.Color.purple()
            )
            
            file = discord.File(os.path.join(os.path.dirname(__file__), '..', 'assets', 'sorryjar.png'), filename="sorryjar.png")
            embed.set_image(url="attachment://sorryjar.png")

            await message.channel.send(embed=embed, file=file)
        
    # --- New Slash Commands for Bump Battle ---
    @app_commands.command(name="bumppoint", description="Awards a point for bumping the server!")
    @app_commands.describe(team="The team you want to give a point to.")
    @app_commands.choices(team=[
        app_commands.Choice(name="doms", value="dom"),
        app_commands.Choice(name="subs", value="sub")
    ])
    @app_commands.checks.cooldown(1, 7200, key=lambda i: (i.guild_id, i.user.id))
    async def bumppoint(self, interaction: discord.Interaction, team: app_commands.Choice[str]):
        """Awards a point for bumping a server with a slash command."""
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        team_name = team.value
        
        bump_battle_state = utils.load_bump_battle_state()
        
        if team_name == 'dom':
            bump_battle_state['dom']['points'] += 1
            if user_id not in bump_battle_state['dom']['users']:
                bump_battle_state['dom']['users'][user_id] = 0
            bump_battle_state['dom']['users'][user_id] += 1
            
            gif_path = os.path.join(os.getcwd(), 'assets', 'bumpbattle_domme.gif')
            file = discord.File(gif_path, filename='bumpbattle_domme.gif')
            embed = discord.Embed(title="1 Point For The Doms!", color=discord.Color.green())
            embed.set_image(url="attachment://bumpbattle_domme.gif")
            await interaction.followup.send(content=f"Thank you for bumping the server. I have given you one <a:bluecoin:1280590252817387593> for the Doms, you now have {bump_battle_state['dom']['points']}!", embed=embed, file=file)
        else:
            bump_battle_state['sub']['points'] += 1
            if user_id not in bump_battle_state['sub']['users']:
                bump_battle_state['sub']['users'][user_id] = 0
            bump_battle_state['sub']['users'][user_id] += 1

            gif_path = os.path.join(os.getcwd(), 'assets', 'bumpbattle_sub.gif')
            file = discord.File(gif_path, filename='bumpbattle_sub.gif')
            embed = discord.Embed(title="1 Point For The Subs!", color=discord.Color.green())
            embed.set_image(url="attachment://bumpbattle_sub.gif")
            await interaction.followup.send(content=f"Thank you for bumping the server. I have given you one <a:bluecoin:1280590252817387593> for the Subs, you now have {bump_battle_state['sub']['points']}!", embed=embed, file=file)
        
        utils.save_bump_battle_state(bump_battle_state)
        
        if bump_battle_state[team_name]['points'] >= 100:
            await self.end_bump_battle(interaction.guild, team_name, bump_battle_state)
            
    async def end_bump_battle(self, guild: discord.Guild, winner: str, state: Dict[str, Any]):
        """A helper function to announce the end of a bump battle and distribute rewards."""
        announcements_channel = guild.get_channel(self.announcements_channel_id)
        announcement_role = guild.get_role(utils.ANNOUNCEMENTS_ROLE_ID)
        
        if not announcements_channel:
            print("Announcements channel not found. Cannot announce bump battle winner.")
            return
        
        if winner == 'sub':
            embed_title = "Sub Win!"
            embed_description = f"Safe to say the subs won the Bump Battle with {state['sub']['points']} points!"
            
            # Correctly reference the local GIF file for Sub win
            gif_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'bumpbattle_sub.gif')
            file = discord.File(gif_path, filename='bumpbattle_sub.gif')
            embed_image_url = "attachment://bumpbattle_sub.gif"

        else:
            embed_title = "Dom Win!"
            embed_description = f"Safe to say the doms won the Bump Battle with {state['dom']['points']} points!"

            # Correctly reference the local GIF file for Dom win
            gif_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'bumpbattle_domme.gif')
            file = discord.File(gif_path, filename='bumpbattle_domme.gif')
            embed_image_url = "attachment://bumpbattle_domme.gif"
        
        win_embed = discord.Embed(
            title=embed_title,
            description=embed_description,
            color=discord.Color.green()
        )
        win_embed.set_image(url=embed_image_url)
        win_embed.set_footer(text="All players have been credited with coins! 🙂")

        # Build the leaderboard embed
        leaderboard_embed = discord.Embed(
            title="Final Bump Battle Leaderboard",
            description="The top contributors who helped their team win:",
            color=discord.Color.gold()
        )

        # Combine all participants into a list to credit them and build the leaderboard
        all_participants = []
        for user_id, points in state['sub']['users'].items():
            all_participants.append({'id': user_id, 'points': points, 'team': 'Subs'})
        for user_id, points in state['dom']['users'].items():
            all_participants.append({'id': user_id, 'points': points, 'team': 'Doms'})
        
        all_participants.sort(key=lambda x: x['points'], reverse=True)
        
        leaderboard_string = ""
        for i, participant in enumerate(all_participants):
            member = guild.get_member(int(participant['id']))
            if member:
                leaderboard_string += f"{i+1}. {member.mention} - {participant['points']} <a:bluecoin:1280590252817387593> ({participant['team']})\n"
        
        if leaderboard_string:
            leaderboard_embed.add_field(name="Top Contributors", value=leaderboard_string, inline=False)
        else:
            leaderboard_embed.add_field(name="Top Contributors", value="No one participated in this round.", inline=False)
            
        content = f"{announcement_role.mention}" if announcement_role else ""
        
        # Create a View with buttons to switch between the embeds
        view = BumpBattleView(win_embed, leaderboard_embed)

        await announcements_channel.send(content=content, embed=win_embed, view=view, file=file)

        for user_id, points in state[winner]['users'].items():
            coins_to_add = points * 10
            utils.update_user_money(int(user_id), coins_to_add)
            print(f"Credited user {user_id} with {coins_to_add} coins for {points} points.")

        state['sub']['points'] = 0
        state['sub']['users'] = {}
        state['dom']['points'] = 0
        state['dom']['users'] = {}
        _save_data(state, BUMP_BATTLE_STATE_FILE)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Server boost reward check
        if before.guild.id != self.main_guild_id:
            return

        if not before.premium_since and after.premium_since:
            booster_channel = self.bot.get_channel(utils.BOOSTER_REWARD_CHANNEL_ID)
            if booster_channel:
                user_id_str = str(after.id)
                booster_rewards = _load_data(BOOSTER_REWARDS_FILE, {})
                if user_id_str not in booster_rewards:
                    utils.update_user_money(after.id, 5000)
                    booster_rewards[user_id_str] = datetime.datetime.now().isoformat()
                    _save_data(booster_rewards, BOOSTER_REWARDS_FILE)
                    await booster_channel.send(f"🎉 Thank you, {after.mention}, for boosting the server! You have been awarded **5000** <a:starcoin:1280590254935380038> for your generosity!")

async def setup(bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Economy(bot))
    print("Economy Cog Loaded!")
