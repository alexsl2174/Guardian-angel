# cogs/modmail_core.py

import discord
from discord.ext import commands
from discord import app_commands
import json
from . import utils
import asyncio
import os

class ModmailCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_tickets_file = os.path.join(utils.DATA_DIR, "active_tickets.json")
        self.active_tickets = utils.load_data(self.active_tickets_file, {})

    def save_active_tickets(self):
        utils.save_data(self.active_tickets, self.active_tickets_file)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild is None:
            user_id = str(message.author.id)
            thread_id = self.active_tickets.get(user_id)

            if thread_id is None:
                print("DEBUG: New ticket requested from user. Starting creation process...")
                guild = self.bot.get_guild(utils.MAIN_GUILD_ID)
                if guild is None:
                    print(f"DEBUG: Guild not found for ID {utils.MAIN_GUILD_ID}. Aborting.")
                    await message.author.send("ModMail system is unavailable. Please contact staff another way.")
                    return

                modmail_channel = guild.get_channel(utils.modmail_channel_id)

                if modmail_channel is None:
                    print(f"DEBUG: ModMail channel not found for ID {utils.modmail_channel_id}. Aborting.")
                    await message.author.send("ModMail system is unavailable. Please contact staff another way.")
                    return
                
                thread_name = f'ticket-{message.author.name}'.replace(" ", "-").lower()
                
                try:
                    thread = await modmail_channel.create_thread(name=thread_name, type=discord.ChannelType.private_thread)
                    print(f"DEBUG: Thread creation API call successful. Created thread with ID: {thread.id}")
                except discord.Forbidden:
                    print("DEBUG: Thread creation failed due to permissions.")
                    return
                except Exception as e:
                    print(f"DEBUG: Thread creation failed with an unexpected error: {e}")
                    return

                notification_channel = guild.get_channel(utils.modmail_notification_channel_id)
                if notification_channel:
                    mod_role_ids = utils.ROLE_IDS.get("Staff", [])
                    thread_link = thread.jump_url

                    notification_embed = discord.Embed(
                        title="New ModMail Ticket",
                        description=f"A new ticket has been opened by {message.author.mention}.",
                        color=discord.Color.blue()
                    )
                    notification_embed.add_field(name="Link to Thread", value=f"[Go to Ticket]({thread_link})", inline=False)
                    
                    if mod_role_ids:
                        for role_id in mod_role_ids:
                            await notification_channel.send(f"<@&{role_id}>", embed=notification_embed)
                    else:
                        await notification_channel.send(embed=notification_embed)

                await message.author.send("Thank you for contacting staff! A new ticket has been opened for you.")
                
                embed = discord.Embed(
                    title="New ModMail Ticket",
                    description=f"Ticket opened by {message.author.mention}\n\n**Initial Message:**\n{message.content}",
                    color=discord.Color.blue()
                )
                
                mod_role_ids = utils.ROLE_IDS.get("Staff", [])
                
                if mod_role_ids:
                    for role_id in mod_role_ids:
                        await thread.send(f"<@&{role_id}>", embed=embed)
                else:
                    await thread.send(embed=embed)

                self.active_tickets[user_id] = thread.id
                self.save_active_tickets()

            else:
                # FIX: Do not relay messages that are not commands
                # We will only relay messages that are explicitly sent with the /reply command
                pass


    @app_commands.command(name="reply", description="Reply to the user in a ModMail thread.")
    @app_commands.describe(content="The message to send to the user.")
    @app_commands.guild_only()
    async def reply_slash(self, interaction: discord.Interaction, content: str):
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and interaction.channel.id in self.active_tickets.values():
            user_id = next(uid for uid, tid in self.active_tickets.items() if tid == interaction.channel.id)
            try:
                user = await self.bot.fetch_user(user_id)
                print(f"DEBUG: Slash command 'reply' is attempting to send DM to user {user.name} ({user.id})...")
                embed = discord.Embed(
                    description=content,
                    color=discord.Color.blue()
                )
                embed.set_author(name="Staff Reply", icon_url=self.bot.user.avatar.url)

                await user.send(embed=embed)
                print(f"DEBUG: DM sent via slash command successfully to {user.name} ({user.id}).")
                
                # FIX: Send the content of the reply to the thread for all staff to see
                staff_reply_embed = discord.Embed(
                    description=content,
                    color=discord.Color.blue()
                )
                staff_reply_embed.set_author(name=f"Reply from {interaction.user.display_name}", icon_url=interaction.user.avatar.url)
                await interaction.response.send_message(embed=staff_reply_embed)

            except discord.Forbidden:
                print(f"DEBUG: Slash command 'reply' failed. User has DMs disabled or has blocked the bot.")
                await interaction.response.send_message("I cannot send a DM to this user. Their DMs may be disabled.", ephemeral=True)
            except discord.NotFound:
                print(f"DEBUG: Slash command 'reply' failed. User not found.")
                await interaction.response.send_message("Could not find the user for this ticket.", ephemeral=True)
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("This command can only be used in a ModMail thread.", ephemeral=True)

    @app_commands.command(name="close", description="Close the current ModMail ticket.")
    @app_commands.guild_only()
    async def close_slash(self, interaction: discord.Interaction):
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and interaction.channel.id in self.active_tickets.values():
            user_id = next(uid for uid, tid in self.active_tickets.items() if tid == interaction.channel.id)
            try:
                user = await self.bot.fetch_user(user_id)
                if user:
                    await user.send("Your ModMail ticket has been closed by staff.")
            except:
                pass
            
            del self.active_tickets[user_id]
            self.save_active_tickets()
            
            # FIX: Add a message to the main channel when a ticket is closed
            notification_channel = interaction.guild.get_channel(utils.modmail_notification_channel_id)
            if notification_channel:
                await notification_channel.send(f"Ticket for <@{user_id}> has been closed by {interaction.user.mention}.")
            
            await interaction.response.send_message("Closing this ticket in 5 seconds...")
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("This is not a valid ModMail thread.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModmailCore(bot))