import discord
from discord import app_commands
from discord.ext import commands
import random
import datetime
import cogs.utils as utils
import asyncio
import os
from typing import Optional

class CountingGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Load the initial state from the saved file
        counting_state = utils.load_counting_game_state()
        self.bot.counting_channel_id = counting_state.get('counting_channel_id')
        self.bot.current_count = counting_state.get('current_count', 0)
        self.bot.last_counter_id = counting_state.get('last_counter_id')
        self.bot.guess_game_active = counting_state.get('guess_game_active', False)
        self.bot.guess_game_number = counting_state.get('guess_game_number', 0)
        self.bot.guess_attempts = counting_state.get('guess_attempts', 0)
        self.bot.lucky_number = counting_state.get('lucky_number', 0)
        self.bot.lucky_number_active = counting_state.get('lucky_number_active', False)
        print("DEBUG: Loaded counting game state:", counting_state)
        self.main_guild_id = utils.MAIN_GUILD_ID

    async def setup_game_state(self):
        # The state is already loaded in __init__
        # This function can now be used for any additional setup,
        # but the primary state is already in memory.
        pass

    @commands.Cog.listener()
    async def on_ready(self):
        # Since the state is loaded in __init__, we don't need to do a full resync here,
        # but we can call it to ensure the state is fully ready.
        await self.setup_game_state()


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild and message.guild.id != self.main_guild_id:
            return
            
        if message.author == self.bot.user or self.bot.counting_channel_id is None:
            return

        if message.channel.id == self.bot.counting_channel_id:
            preferences = utils.load_counting_preferences()
            consecutive_counting_enabled = preferences.get('consecutive_counting', False)
            role_on_miscount_enabled = preferences.get('role_on_miscount', True)
            delete_incorrect_enabled = preferences.get('delete_incorrect', False)
            sudden_death_enabled = preferences.get('sudden_death', True)
            mode = preferences.get('mode', 'incremental')

            try:
                msg_number = int(message.content)
            except ValueError:
                return

            # Check for lucky number first if it's active
            if self.bot.lucky_number_active and msg_number == self.bot.lucky_number:
                utils.update_user_money(message.author.id, 25)

                await message.channel.send(f"🍀 **LUCKY NUMBER!** {message.author.mention} hit the lucky number **{self.bot.lucky_number}** and earned a bonus of **25 coins**!")
                
                self.bot.lucky_number_active = False
                self.bot.lucky_number = 0
                
                # Update the count to the lucky number and continue
                self.bot.current_count = msg_number
                self.bot.last_counter_id = message.author.id

                utils.save_counting_game_state(
                    {
                        "counting_channel_id": self.bot.counting_channel_id,
                        "current_count": self.bot.current_count,
                        "last_counter_id": self.bot.last_counter_id,
                        "guess_game_active": self.bot.guess_game_active,
                        "guess_game_number": self.bot.guess_game_number,
                        "guess_attempts": self.bot.guess_attempts,
                        "lucky_number": self.bot.lucky_number,
                        "lucky_number_active": self.bot.lucky_number_active
                    }
                )
                await message.add_reaction('🍀')
                return

            if self.bot.guess_game_active:
                if msg_number == self.bot.guess_game_number:
                    utils.update_user_money(message.author.id, 50)
                    next_count_after_guess = self.bot.current_count + 1 if mode == 'incremental' else self.bot.current_count - 1
                    
                    await message.channel.send(f"🎉 **Congratulations {message.author.mention}!** You guessed **{self.bot.guess_game_number}** and won **50 coins**! Let's continue counting from **{next_count_after_guess}**!")
                    
                    self.bot.guess_game_active = False
                    # The count does not advance here; the next count should be the sequential one.
                    # self.bot.current_count remains the same
                    # self.bot.last_counter_id remains the same as the last person who counted
                    self.bot.guess_game_number = 0
                    self.bot.guess_attempts = 0
                    self.bot.lucky_number = 0
                    self.bot.lucky_number_active = False
                    utils.save_counting_game_state(
                        {
                            "counting_channel_id": self.bot.counting_channel_id,
                            "current_count": self.bot.current_count,
                            "last_counter_id": self.bot.last_counter_id,
                            "guess_game_active": self.bot.guess_game_active,
                            "guess_game_number": self.bot.guess_game_number,
                            "guess_attempts": self.bot.guess_attempts,
                            "lucky_number": self.bot.lucky_number,
                            "lucky_number_active": self.bot.lucky_number_active
                        }
                    )
                    await message.add_reaction('🎯')
                else:
                    self.bot.guess_attempts += 1
                    remaining_attempts = 3 - self.bot.guess_attempts

                    if remaining_attempts <= 0:
                        await message.channel.send(f"❌ **Sorry, {message.author.mention}**, you're out of chances! The number was **{self.bot.guess_game_number}**. The count is now reset to **1**.")
                        self.bot.current_count = 0
                        self.bot.last_counter_id = None
                        self.bot.guess_game_active = False
                        self.bot.guess_game_number = 0
                        self.bot.guess_attempts = 0
                        self.bot.lucky_number = 0
                        self.bot.lucky_number_active = False
                        utils.save_counting_game_state(
                            {
                                "counting_channel_id": self.bot.counting_channel_id,
                                "current_count": self.bot.current_count,
                                "last_counter_id": self.bot.last_counter_id,
                                "guess_game_active": self.bot.guess_game_active,
                                "guess_game_number": self.bot.guess_game_number,
                                "guess_attempts": self.bot.guess_attempts,
                                "lucky_number": self.bot.lucky_number,
                                "lucky_number_active": self.bot.lucky_number_active
                            }
                        )
                    else:
                        hint = "higher" if self.bot.guess_game_number > msg_number else "lower"
                        await message.channel.send(f"❌ **Incorrect guess, {message.author.mention}**! The number is **{hint}** than your guess. You have **{remaining_attempts}** chances left.")
                        utils.save_counting_game_state(
                            {
                                "counting_channel_id": self.bot.counting_channel_id,
                                "current_count": self.bot.current_count,
                                "last_counter_id": self.bot.last_counter_id,
                                "guess_game_active": self.bot.guess_game_active,
                                "guess_game_number": self.bot.guess_game_number,
                                "guess_attempts": self.bot.guess_attempts,
                                "lucky_number": self.bot.lucky_number,
                                "lucky_number_active": self.bot.lucky_number_active
                            }
                        )
                return

            next_count = self.bot.current_count + 1 if mode == 'incremental' else self.bot.current_count - 1

            if not consecutive_counting_enabled and message.author.id == self.bot.last_counter_id:
                try:
                    if delete_incorrect_enabled:
                        await message.delete()
                except discord.Forbidden:
                    pass
                
                utils.update_user_money(message.author.id, -10)
                current_balance = utils.get_user_money(message.author.id)
                await message.channel.send(f"🚫 **{message.author.mention}**, you can't count twice in a row! You lost 10 coins. Your new balance is {current_balance}.")
                return

            if msg_number != next_count:
                if role_on_miscount_enabled:
                    role_name = "I can't count"
                    role = discord.utils.get(message.guild.roles, name=role_name)
                    if not role:
                        try:
                            role = await message.guild.create_role(name=role_name, reason="Role for miscounting in the counting game.")
                            print(f"Created new role: {role_name}")
                        except discord.Forbidden:
                            print(f"Failed to create role '{role_name}'. Bot lacks permissions.")
                            role = None

                    if role and message.guild.me.top_role > role:
                        try:
                            await message.author.add_roles(role, reason="Miscounted in counting game.")
                            await message.channel.send(f"💔 **Oh no, {message.author.mention} ruined the count!** The correct number was **{next_count}**. You now have the '{role_name}' role for 60 seconds.")
                            self.bot.loop.create_task(self.remove_role_after_delay(message.author, role, 60))
                        except discord.Forbidden:
                            print(f"Failed to add role '{role_name}' to {message.author}. Bot lacks permissions or role hierarchy is wrong.")
                            await message.channel.send(f"💔 **Oh no, {message.author.mention} ruined the count!** The correct number was **{next_count}**.")
                    else:
                        await message.channel.send(f"💔 **Oh no, {message.author.mention} ruined the count!** The correct number was **{next_count}**.")
                else:
                    await message.channel.send(f"💔 **Oh no, {message.author.mention} ruined the count!** The correct number was **{next_count}**.")
                
                if sudden_death_enabled:
                    self.bot.current_count = 0
                
                self.bot.last_counter_id = None
                self.bot.guess_game_active = False
                self.bot.guess_game_number = 0
                self.bot.guess_attempts = 0
                self.bot.lucky_number = 0
                self.bot.lucky_number_active = False
                utils.save_counting_game_state(
                    {
                        "counting_channel_id": self.bot.counting_channel_id,
                        "current_count": self.bot.current_count,
                        "last_counter_id": self.bot.last_counter_id,
                        "guess_game_active": self.bot.guess_game_active,
                        "guess_game_number": self.bot.guess_game_number,
                        "guess_attempts": self.bot.guess_attempts,
                        "lucky_number": self.bot.lucky_number,
                        "lucky_number_active": self.bot.lucky_number_active
                    }
                )
                return
            
            user_counted_before = utils.check_if_user_counted(message.author.id)
            if not user_counted_before:
                utils.update_user_money(message.author.id, utils.FIRST_COUNT_REWARD)
                await utils.add_role_to_member(message.author, utils.FIRST_COUNT_ROLE)
                
                embed = discord.Embed(
                    title="🏆 Achievement Unlocked: First Count!",
                    description=f"Congratulations, {message.author.mention}! You've made your first count in the server's counting game. Many more to come!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Reward", value=f"<a:starcoin:1280590254935380038> {utils.FIRST_COUNT_REWARD} coins")
                embed.set_thumbnail(url=message.author.display_avatar.url)
                embed.set_footer(text="Keep counting!")
                await message.channel.send(embed=embed)
                
                utils.set_user_counted(message.author.id)

            self.bot.current_count = next_count
            self.bot.last_counter_id = message.author.id
            
            await message.add_reaction('✅')
            
            utils.update_user_money(message.author.id, 1)

            if not self.bot.lucky_number_active:
                if self.bot.current_count == 1:
                    self.bot.lucky_number = random.randint(1, 20)
                    self.bot.lucky_number_active = True
                    await message.channel.send(f"✨ A new lucky number has been chosen! The next person to count **{self.bot.lucky_number}** will win **25 coins**!")
                elif self.bot.current_count > 0 and self.bot.current_count % 20 == 0:
                    self.bot.lucky_number = random.randint(self.bot.current_count + 1, self.bot.current_count + 20)
                    self.bot.lucky_number_active = True
                    await message.channel.send(f"✨ A new lucky number has been chosen! The next person to count **{self.bot.lucky_number}** will win **25 coins**!")
            
            utils.save_counting_game_state(
                {
                    "counting_channel_id": self.bot.counting_channel_id,
                    "current_count": self.bot.current_count,
                    "last_counter_id": self.bot.last_counter_id,
                    "guess_game_active": self.bot.guess_game_active,
                    "guess_game_number": self.bot.guess_game_number,
                    "guess_attempts": self.bot.guess_attempts,
                    "lucky_number": self.bot.lucky_number,
                    "lucky_number_active": self.bot.lucky_number_active
                }
            )

            if not self.bot.guess_game_active and random.randint(1, 10) == 1:
                if self.bot.current_count >= 10:
                    self.bot.guess_game_active = True
                    lower_bound = max(1, self.bot.current_count - 10)
                    upper_bound = self.bot.current_count + 10
                    self.bot.guess_game_number = random.randint(lower_bound, upper_bound)
                    self.bot.guess_attempts = 0
                    
                    await message.channel.send(f"✨ **Time for a guessing game!** I've chosen a number between **{lower_bound}** and **{upper_bound}**. "
                                               f"The first person to guess it correctly wins **50 coins** and continues the count! You have 3 chances.")
                    
                    utils.save_counting_game_state(
                        {
                            "counting_channel_id": self.bot.counting_channel_id,
                            "current_count": self.bot.current_count,
                            "last_counter_id": self.bot.last_counter_id,
                            "guess_game_active": self.bot.guess_game_active,
                            "guess_game_number": self.bot.guess_game_number,
                            "guess_attempts": self.bot.guess_attempts,
                            "lucky_number": self.bot.lucky_number,
                            "lucky_number_active": self.bot.lucky_number_active
                        }
                    )
            return

    async def remove_role_after_delay(self, member: discord.Member, role: discord.Role, delay: int):
        await asyncio.sleep(delay)
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="'I can't count' role expired.")
                print(f"Removed '{role.name}' role from {member} after {delay} seconds.")
        except discord.Forbidden:
            print(f"Failed to remove role '{role.name}' from {member}. Bot lacks permissions.")
        except Exception as e:
            print(f"An unexpected error occurred while removing role from {member}: {e}")

    @app_commands.command(name="countpref", description="Set counting game preferences for the server.")
    @app_commands.describe(
        consecutive_counting="Allow a user to count twice in a row.",
        delete_incorrect="Delete messages that are an incorrect count.",
        role_on_miscount="Give the 'I can't count' role to users who miscount.",
        sudden_death="Reset the count to 1 on a miscount.",
        mode="Set the counting mode."
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Incremental (+1)", value="incremental"),
        app_commands.Choice(name="Decremental (-1)", value="decremental")
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def count_preferences(self, interaction: discord.Interaction,
                                consecutive_counting: Optional[bool] = None,
                                delete_incorrect: Optional[bool] = None,
                                role_on_miscount: Optional[bool] = None,
                                sudden_death: Optional[bool] = None,
                                mode: Optional[str] = None):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
            return

        preferences = utils.load_counting_preferences()
        
        updated_prefs = {}
        if consecutive_counting is not None:
            preferences['consecutive_counting'] = consecutive_counting
            updated_prefs['Consecutive Counting'] = 'Enabled' if consecutive_counting else 'Disabled'
        if delete_incorrect is not None:
            preferences['delete_incorrect'] = delete_incorrect
            updated_prefs['Delete Incorrect'] = 'Enabled' if delete_incorrect else 'Disabled'
        if role_on_miscount is not None:
            preferences['role_on_miscount'] = role_on_miscount
            updated_prefs['Role on Miscount'] = 'Enabled' if role_on_miscount else 'Disabled'
        if sudden_death is not None:
            preferences['sudden_death'] = sudden_death
            updated_prefs['Sudden Death'] = 'Enabled' if sudden_death else 'Disabled'
        if mode is not None:
            preferences['mode'] = mode
            updated_prefs['Mode'] = mode.capitalize()

        utils.save_counting_preferences(preferences)
        
        if updated_prefs:
            message = "Updated counting game preferences:\n" + "\n".join(
                [f"**{key}**: {value}" for key, value in updated_prefs.items()]
            )
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.send_message("No preferences were updated. Please specify at least one option.", ephemeral=True)

async def setup(bot):
    cog = CountingGame(bot)
    await bot.add_cog(cog)
