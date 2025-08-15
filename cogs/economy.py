import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import random
import datetime
import os
import asyncio
from typing import List, Dict, Any, Union, Optional
import re

# Import shared utility functions and global configurations
import cogs.utils as utils

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
        self.anagram_game_state = utils.load_anagram_game_state()
        self.anagram_words = utils.load_anagram_words()
        self.bump_battle_state = utils.load_bump_battle_state()

        # Correctly load dynamic channel IDs from the bot_config dictionary
        self.bump_battle_channel_id = utils.bot_config.get("bump_battle_channel_id")
        self.vote_channel_id = utils.bot_config.get("vote_channel_id")
        self.announcements_channel_id = utils.bot_config.get("announcements_channel_id")

        # Define cooldown times in seconds
        self.BUMP_COOLDOWN = 120
        self.POINT_COOLDOWN = 120
        self.VOTE_COOLDOWN = 360
        
    @commands.Cog.listener()
    async def on_ready(self):
        # This listener is called when the cog is loaded and the bot is ready.
        # It ensures that the anagram game task starts after the bot is connected.
        self.anagram_game_task.start()
        print("Anagram game task started.")

    # --- Anagram Game Command and Loop ---
    @app_commands.command(name="start_anagram_game", description="Starts a new Anagram game immediately.")
    async def start_anagram_game(self, interaction: discord.Interaction):
        """Starts a new anagram game immediately."""
        anagram_channel_id = utils.bot_config.get('ANAGRAM_CHANNEL_ID')
        if not anagram_channel_id:
            await interaction.response.send_message("The anagram channel is not set. Please use an admin command to set it first.", ephemeral=True)
            return

        anagram_state = utils.load_anagram_game_state()
        if anagram_state.get('current_word'):
            await interaction.response.send_message("An anagram game is already in progress.", ephemeral=True)
            return

        await interaction.response.send_message("Starting a new anagram game now!", ephemeral=True)
        # Manually trigger the task to start a game now
        await self.anagram_game_task()

    @tasks.loop(hours=1)
    async def anagram_game_task(self):
        """This task runs every hour to start a new anagram game."""
        anagram_channel_id = utils.bot_config.get('ANAGRAM_CHANNEL_ID')
        if not anagram_channel_id:
            return

        channel = self.bot.get_channel(anagram_channel_id)
        if not channel:
            print(f"Anagram task failed: Channel with ID {anagram_channel_id} not found.")
            return

        anagram_state = utils.load_anagram_game_state()
        if anagram_state.get('current_word'):
            print("Anagram task skipped: A game is already in progress.")
            return

        # Use the AI to generate a new word
        word = await utils.generate_anagram_word_with_gemini()
        if not word:
            # Fallback to the hardcoded list if AI fails
            anagram_words = utils.load_anagram_words()
            if not anagram_words:
                await channel.send("Sorry, I couldn't generate a new anagram word right now. The word list is empty.")
                return
            word = random.choice(anagram_words)
            await channel.send("The AI failed to generate a new word, falling back to a pre-defined list.")

        shuffled_word = "".join(random.sample(word, len(word)))

        anagram_state['current_word'] = word
        anagram_state['shuffled_word'] = shuffled_word
        anagram_state['channel_id'] = anagram_channel_id
        utils.save_anagram_game_state(anagram_state)

        embed = discord.Embed(
            title="Game = Anagram",
            description=f"Guess the word: **{shuffled_word}** in 4 minutes",
            color=discord.Color.purple()
        )
        await channel.send(embed=embed)

        await asyncio.sleep(240)

        current_anagram_state = utils.load_anagram_game_state()
        if current_anagram_state.get('current_word') == word:
            await channel.send(f"Time's up! The correct answer was **{word}**.")
            current_anagram_state['current_word'] = None
            utils.save_anagram_game_state(current_anagram_state)

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
    
    @app_commands.command(name="checkin", description="Check in daily for role-based rewards.")
    @app_commands.checks.cooldown(1, 24*60*60)
    async def checkin(self, interaction: discord.Interaction):
        """Allows a user to check in daily and claim rewards based on their roles."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
            
        # Check if the command is being used in the correct channel
        if interaction.channel_id != utils.CHECKIN_CHANNEL_ID:
            await interaction.response.send_message("This command can only be used in the designated check-in channel.", ephemeral=True)
            return

        user_id = interaction.user.id
        member = interaction.user
        
        # Base reward for checking in
        base_reward = 25
        total_reward = base_reward
        reward_messages = [f"✅ Role income successfully collected!", f"1 - @ Timed 16hr ~ Daily Check In | {base_reward} (cash)"]

        # Get role IDs and check for them
        saint_role_id = utils.ROLE_IDS.get("Saint")
        sinner_role_id = utils.ROLE_IDS.get("sinner")
        booster_role_id = utils.ROLE_IDS.get("booster")
        
        # Check for specific roles
        if discord.utils.get(member.roles, id=saint_role_id):
            total_reward += 100
            reward_messages.append(f"2 - Saint | 100 coins")
        if discord.utils.get(member.roles, id=sinner_role_id):
            total_reward += 150
            reward_messages.append(f"3 - sinner | 150 coins")
        if discord.utils.get(member.roles, id=booster_role_id):
            total_reward += 300
            reward_messages.append(f"4 - Booster | 300 coins")
        
        # Check for daily timed roles from utils.py
        now = datetime.datetime.now(datetime.timezone.utc)
        weekday_name = now.strftime('%A').lower()
        role_name = f"{weekday_name}_role"
        role_id = utils.ROLE_IDS.get(role_name)
        
        if role_id and discord.utils.get(member.roles, id=role_id):
            total_reward += 250
            reward_messages.append(f"{len(reward_messages)} - {role_name.replace('_', ' ').title()} | 250 coins")

        if total_reward > base_reward:
            utils.update_user_money(user_id, total_reward)
            await interaction.response.send_message("\n".join(reward_messages), ephemeral=False)
        else:
            await interaction.response.send_message(f"✅ Role income successfully collected!\n1 - Timed 16hr ~ Daily Check In | {base_reward} (cash)", ephemeral=False)

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
        target_money = utils.get_user_money(target_id)

        if target_money < 2000:
            await interaction.response.send_message(f"That user doesn't have enough money to rob! They need at least 2000 <a:starcoin:1280590254935380038>.", ephemeral=True)
            return
        if robber_money < 3000:
            await interaction.response.send_message(f"You need at least 3000 <a:starcoin:1280590254935380038> to rob someone!", ephemeral=True)
            return

        outcome = random.choices(['free', 'caught'], weights=[80, 20], k=1)[0]

        embed = discord.Embed(title="Robbery Attempt")
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        if outcome == 'free':
            amount = random.randint(1, target_money)
            utils.update_user_money(target_id, -amount)
            utils.update_user_money(user_id, amount)
            
            embed.description = f"{interaction.user.mention} robbed {target.mention} and successfully got **{amount}** <a:starcoin:1280590254935380038>!"
            embed.color = discord.Color.green()
        else:
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

    @app_commands.command(name="modifybal", description="[Moderator Only] Adds/removes balance for a user.")
    @app_commands.check(is_moderator)
    @app_commands.describe(member="The member to modify the balance of.", amount="The amount to add or remove.")
    async def modify_balance(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        """A moderator command to manually adjust a user's balance."""
        user_id = member.id
        utils.update_user_money(user_id, amount)
        
        await interaction.response.send_message(f"Added {amount} <a:starcoin:1280590254935380038> to {member.mention}'s balance.", ephemeral=True)
    
    # --- New Unified Leaderboard Command ---
    @app_commands.command(name="leaderboard", description="Shows the top users for a specific game or metric.")
    @app_commands.describe(
        board="The leaderboard you want to view."
    )
    @app_commands.choices(board=[
        app_commands.Choice(name="Coins", value="coins"),
        app_commands.Choice(name="Bug Book", value="bugbook"),
        app_commands.Choice(name="Swear Tally", value="swears"),
        app_commands.Choice(name="Bumps", value="bumps")
    ])
    async def leaderboard(self, interaction: discord.Interaction, board: str):
        """Displays the top users by a selected metric."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
        
        await interaction.response.defer()

        guild = interaction.guild
        embed = discord.Embed(title=f"{guild.name}'s Leaderboard", color=discord.Color.gold())
        
        if board == "coins":
            balances = utils.load_data(utils.BALANCES_FILE)
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
            embed.title += " (Top Coins)"
            
        elif board == "bugbook":
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
            embed.title += " (Bug Collectors)"

        elif board == "swears":
            swear_jar_data = utils.load_swear_jar_data()
            tally = swear_jar_data.get('tally', {})
            leaderboard_entries = []
            for user_id_str, count in tally.items():
                member = guild.get_member(int(user_id_str))
                if member:
                    leaderboard_entries.append((member.display_name, count))
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)

            description = "\n".join([f"{i+1}. **{name}** - {count} swears" for i, (name, count) in enumerate(leaderboard_entries[:10])])
            embed.description = description if description else "The swear jar is empty!"
            embed.title += " (Swear Tally)"
            
        elif board == "bumps":
            bump_battle_state = utils.load_bump_battle_state()
            sub_users = bump_battle_state.get('sub', {}).get('users', {})
            dom_users = bump_battle_state.get('dom', {}).get('users', {})

            all_bump_users = {**sub_users, **dom_users}
            leaderboard_entries = []
            for user_id_str, count in all_bump_users.items():
                member = guild.get_member(int(user_id_str))
                if member:
                    leaderboard_entries.append((member.display_name, count))
            
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)
            description = "\n".join([f"{i+1}. **{name}** - {count} <a:bluecoin:1280590252817387593>" for i, (name, count) in enumerate(leaderboard_entries[:10])])
            embed.description = description if description else "No one has bumped yet!"
            embed.title += " (Bump Battle)"
        
        else:
            embed.description = "Invalid leaderboard type specified."

        await interaction.followup.send(embed=embed)


    # --- Listeners for other games ---
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listens for messages to handle anagram and bump battle games."""
        if message.author.bot or not message.guild:
            return
        
        # Check for daily message reward
        if message.channel.id == utils.DAILY_MESSAGE_REWARD_CHANNEL_ID:
            user_id_str = str(message.author.id)
            cooldowns = utils.load_daily_message_cooldowns()
            last_reward_date_str = cooldowns.get(user_id_str)
            today_str = datetime.date.today().isoformat()

            if last_reward_date_str != today_str:
                utils.update_user_money(message.author.id, 25)
                cooldowns[user_id_str] = today_str
                utils.save_daily_message_cooldowns(cooldowns)

        # Anagram game logic
        anagram_state = utils.load_anagram_game_state()
        if message.channel.id == anagram_state.get('channel_id'):
            correct_word = anagram_state.get('current_word')
            if correct_word and message.content.lower() == correct_word.lower():
                user_id = str(message.author.id)
                utils.update_user_money(user_id, 250)
                
                await message.channel.send(f"🎉 {message.author.mention} is correct! The word was **{correct_word}** and they have been awarded 250 <a:starcoin:1280590254935380038>!")
                
                anagram_state['current_word'] = None
                utils.save_anagram_game_state(anagram_state)
                
                self.anagram_game_task.restart()

        # Bump battle game logic
        if self.bump_battle_channel_id and message.channel.id == self.bump_battle_channel_id:
            user_id = str(message.author.id)
            now = datetime.datetime.now()
            vote_cooldowns = utils.load_vote_cooldowns()

            cooldown_type = None
            if "sub point" in message.content.lower() or "dom point" in message.content.lower():
                cooldown_type = "point"
            elif "sub bump" in message.content.lower() or "dom bump" in message.content.lower():
                cooldown_type = "bump"
            
            if cooldown_type:
                cooldown_seconds = self.POINT_COOLDOWN if cooldown_type == "point" else self.BUMP_COOLDOWN
                user_cooldowns = vote_cooldowns.get(user_id, {})
                last_time = user_cooldowns.get(cooldown_type)

                if last_time and now < datetime.datetime.fromisoformat(last_time) + datetime.timedelta(seconds=cooldown_seconds):
                    time_left = (datetime.datetime.fromisoformat(last_time) + datetime.timedelta(seconds=cooldown_seconds)) - now
                    minutes = time_left.seconds // 60
                    seconds = time_left.seconds % 60
                    
                    fun_cog = self.bot.get_cog("FunCommands")
                    if fun_cog:
                        slap_url = await fun_cog._get_gif_url("slap")
                        if slap_url:
                            embed = discord.Embed(
                                description=f"{message.author.mention} Stop trying to get a point, you will have to wait for **{minutes}m** and **{seconds}s**!",
                                color=discord.Color.red()
                            )
                            embed.set_image(url=slap_url)
                            await message.channel.send(embed=embed)
                        else:
                            await message.channel.send(f"{message.author.mention} Stop trying to get a point, you will have to wait for **{minutes}m** and **{seconds}s**!")
                    else:
                        await message.channel.send(f"{message.author.mention} Stop trying to get a point, you will have to wait for **{minutes}m** and **{seconds}s**!")
                    return
                
                # Update cooldown timestamp for the specific action
                user_cooldowns[cooldown_type] = now.isoformat()
                vote_cooldowns[user_id] = user_cooldowns
                utils.save_vote_cooldowns(vote_cooldowns)
            
            bump_battle_state = utils.load_bump_battle_state()
            if "sub point" in message.content.lower() or "sub bump" in message.content.lower():
                bump_battle_state['sub']['points'] += 1
                if user_id not in bump_battle_state['sub']['users']:
                    bump_battle_state['sub']['users'][user_id] = 0
                bump_battle_state['sub']['users'][user_id] += 1
                utils.save_bump_battle_state(bump_battle_state)
                
                # Send the unified point-awarded embed with GIF
                embed = discord.Embed(
                    title="1 Point For The Subs!",
                    description="Thank you for bumping the server. I have given you one <a:bluecoin:1280590252817387593> for the Subs.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"You now have {bump_battle_state['sub']['points']}!")
                embed.set_image(url="https://cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/724ace2b0a8d8f254c5767bdb490d96bfdd7c6dcc449b9f0e37c10e6f677eb8a.gif")
                await message.channel.send(embed=embed)
                
                if bump_battle_state['sub']['points'] >= 100:
                    await self.end_bump_battle(message.guild, 'sub', bump_battle_state)

            elif "dom point" in message.content.lower() or "dom bump" in message.content.lower():
                bump_battle_state['dom']['points'] += 1
                if user_id not in bump_battle_state['dom']['users']:
                    bump_battle_state['dom']['users'][user_id] = 0
                bump_battle_state['dom']['users'][user_id] += 1
                utils.save_bump_battle_state(bump_battle_state)

                # Send the unified point-awarded embed with GIF
                embed = discord.Embed(
                    title="1 Point For The Doms!",
                    description="Thank you for bumping the server. I have given you one <a:bluecoin:1280590252817387593> for the Doms.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"You now have {bump_battle_state['dom']['points']}!")
                embed.set_image(url="https://images-ext-1.discordapp.net/external/oZOXRK4-QMFQIY5hYxnTF9KrrYhhSQeE95fQegMuJIA/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/d2279e456e5b45c4f9f6aa23587480971bf2cb87129681d5bbbe5f90f390d4b.gif")
                await message.channel.send(embed=embed)

                if bump_battle_state['dom']['points'] >= 100:
                    await self.end_bump_battle(message.guild, 'dom', bump_battle_state)
        
        # Vote channel game logic
        if self.vote_channel_id and message.channel.id == self.vote_channel_id:
            user_id = str(message.author.id)
            now = datetime.datetime.now()
            vote_cooldowns = utils.load_vote_cooldowns()

            if "sub vote" in message.content.lower():
                user_cooldowns = vote_cooldowns.get(user_id, {})
                last_time = user_cooldowns.get("vote")

                if last_time and now < datetime.datetime.fromisoformat(last_time) + datetime.timedelta(seconds=self.VOTE_COOLDOWN):
                    time_left = (datetime.datetime.fromisoformat(last_time) + datetime.timedelta(seconds=self.VOTE_COOLDOWN)) - now
                    minutes = time_left.seconds // 60
                    seconds = time_left.seconds % 60
                    await message.channel.send(f"You have already voted! You can vote again in {minutes} minutes and {seconds} seconds.")
                else:
                    bump_battle_state = utils.load_bump_battle_state()
                    bump_battle_state['sub']['points'] += 1
                    if user_id not in bump_battle_state['sub']['users']:
                        bump_battle_state['sub']['users'][user_id] = 0
                    bump_battle_state['sub']['users'][user_id] += 1

                    if bump_battle_state['sub']['points'] >= 100:
                        await self.end_bump_battle(message.guild, 'sub', bump_battle_state)
                    else:
                        utils.save_bump_battle_state(bump_battle_state)
                        user_cooldowns["vote"] = now.isoformat()
                        vote_cooldowns[user_id] = user_cooldowns
                        utils.save_vote_cooldowns(vote_cooldowns)
                    
                    await message.channel.send(f"Thank you for voting for the Subs! You have been awarded 1 point.")
            elif "dom vote" in message.content.lower():
                user_cooldowns = vote_cooldowns.get(user_id, {})
                last_time = user_cooldowns.get("vote")

                if last_time and now < datetime.datetime.fromisoformat(last_time) + datetime.timedelta(seconds=self.VOTE_COOLDOWN):
                    time_left = (datetime.datetime.fromisoformat(last_time) + datetime.timedelta(seconds=self.VOTE_COOLDOWN)) - now
                    minutes = time_left.seconds // 60
                    seconds = time_left.seconds % 60
                    await message.channel.send(f"You have already voted! You can vote again in {minutes} minutes and {seconds} seconds.")
                else:
                    bump_battle_state = utils.load_bump_battle_state()
                    bump_battle_state['dom']['points'] += 1
                    if user_id not in bump_battle_state['dom']['users']:
                        bump_battle_state['dom']['users'][user_id] = 0
                    bump_battle_state['dom']['users'][user_id] += 1
                    
                    if bump_battle_state['dom']['points'] >= 100:
                        await self.end_bump_battle(message.guild, 'dom', bump_battle_state)
                    else:
                        utils.save_bump_battle_state(bump_battle_state)
                        user_cooldowns["vote"] = now.isoformat()
                        vote_cooldowns[user_id] = user_cooldowns
                        utils.save_vote_cooldowns(vote_cooldowns)
                    
                    await message.channel.send(f"Thank you for voting for the Doms! You have been awarded 1 point.")

    async def end_bump_battle(self, guild: discord.Guild, winner: str, state: Dict[str, Any]):
        """A helper function to announce the end of a bump battle and distribute rewards."""
        announcements_channel = guild.get_channel(self.announcements_channel_id)
        announcement_role = guild.get_role(utils.ANNOUNCEMENTS_ROLE_ID)
        
        if not announcements_channel:
            print("Announcements channel not found. Cannot announce bump battle winner.")
            return
        
        if winner == 'sub':
            embed_title = "Sub Win!"
            embed_description = f"Super Subs {state['sub']['points']} - Stinky Doms {state['dom']['points']}\nSafe to say the subs won the Bump Battle!"
            embed_image_url = "https://cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/724ace2b0a8d8f254c5767bdb490d96bfdd7c6dcc449b9f0e37c10e6f677eb8a.gif"
        else:
            embed_title = "Dom Win!"
            embed_description = f"Stinky Doms {state['dom']['points']} - Super Subs {state['sub']['points']}\nSafe to say the doms won the Bump Battle!"
            embed_image_url = "https://images-ext-1.discordapp.net/external/oZOXRK4-QMFQIY5hYxnTF9KrrYhhSQeE95fQegMuJIA/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/d2279e456e5b45c4f9f6aa23587480971bf2cb87129681d5bbbe5f90f390d4b.gif"

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

        await announcements_channel.send(content=content, embed=win_embed, view=view)

        for user_id, points in state[winner]['users'].items():
            coins_to_add = points * 10
            utils.update_user_money(int(user_id), coins_to_add)
            print(f"Credited user {user_id} with {coins_to_add} coins for {points} points.")

        state['sub']['points'] = 0
        state['sub']['users'] = {}
        state['dom']['points'] = 0
        state['dom']['users'] = {}
        utils.save_bump_battle_state(state)

async def setup(bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Economy(bot))
    print("Economy Cog Loaded!")