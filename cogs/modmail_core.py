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
        self.anon_ticket_counter_file = os.path.join(utils.DATA_DIR, "anon_ticket_counter.json")
        self.active_tickets = utils.load_data(self.active_tickets_file, {})
        self.anon_ticket_counter = utils.load_data(self.anon_ticket_counter_file, 0)

    def save_active_tickets(self):
        utils.save_data(self.active_tickets, self.active_tickets_file)

    def save_anon_ticket_counter(self):
        utils.save_data(self.anon_ticket_counter, self.anon_ticket_counter_file)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild is None:
            user_id = str(message.author.id)
            active_ticket_data = self.active_tickets.get(user_id)

            is_anonymous_start = message.content.startswith("/anon")
            message_content = message.content

            # Check for existing anonymous ticket before processing
            if is_anonymous_start and active_ticket_data and active_ticket_data.get('is_anon'):
                await message.author.send("You already have an active anonymous ticket. Please close it before opening another one.")
                return

            if is_anonymous_start:
                message_content = message.content.replace("/anon", "", 1).strip()
                if not message_content:
                    await message.author.send("You must include a message after `/anon` to create an anonymous ticket.")
                    return

            if active_ticket_data is None:
                print("DEBUG: New ticket requested from user. Starting creation process...")
                guild = self.bot.get_guild(utils.MAIN_GUILD_ID)
                if guild is None:
                    print(f"DEBUG: Guild not found for ID {utils.MAIN_GUILD_ID}. Aborting.")
                    await message.author.send("ModMail system is unavailable. Please contact staff another way.")
                    return

                modmail_channel_id = utils.CHANNEL_IDS.get("modmail_channel_id")
                modmail_channel = guild.get_channel(modmail_channel_id)

                if modmail_channel is None:
                    print(f"DEBUG: ModMail channel not found for ID {modmail_channel_id}. Aborting.")
                    await message.author.send("ModMail system is unavailable. Please contact staff another way.")
                    return
                
                if is_anonymous_start:
                    self.anon_ticket_counter += 1
                    thread_name = f'anonymous-ticket-{self.anon_ticket_counter}'
                    self.save_anon_ticket_counter()
                else:
                    thread_name = f'ticket-{message.author.name}'.replace(" ", "-").lower()[:100]
                
                try:
                    thread = await modmail_channel.create_thread(name=thread_name, type=discord.ChannelType.private_thread)
                    print(f"DEBUG: Thread creation API call successful. Created thread with ID: {thread.id}")
                except discord.Forbidden:
                    print("DEBUG: Thread creation failed due to permissions.")
                    return
                except Exception as e:
                    print(f"DEBUG: Thread creation failed with an unexpected error: {e}")
                    return

                notification_channel = guild.get_channel(utils.CHANNEL_IDS.get("modmail_notification_channel_id"))
                thread_link = thread.jump_url
                
                notification_embed = discord.Embed(
                    title="New ModMail Ticket",
                    description=f"A new ticket has been opened by {'an **Anonymous** user.' if is_anonymous_start else message.author.mention}",
                    color=discord.Color.blue()
                )
                notification_embed.add_field(name="Link to Thread", value=f"[Go to Ticket]({thread_link})", inline=False)
                
                staff_role_ids = utils.ROLE_IDS.get("Staff", [])
                
                if notification_channel and staff_role_ids:
                    await notification_channel.send(f"<@&{staff_role_ids[0]}>", embed=notification_embed)

                await message.author.send("Thank you for contacting staff! A new ticket has been opened for you.")
                
                embed = discord.Embed(
                    title=f"New {'Anonymous' if is_anonymous_start else ''} ModMail Ticket from {'Anonymous User' if is_anonymous_start else message.author}",
                    description=f"**Initial Message:**\n{message_content}",
                    color=discord.Color.blue()
                )
                
                if staff_role_ids:
                    await thread.send(f"<@&{staff_role_ids[0]}>", embed=embed)
                else:
                    await thread.send(embed=embed)

                self.active_tickets[user_id] = {"thread_id": thread.id, "is_anon": is_anonymous_start}
                self.save_active_tickets()

            # If an active ticket exists, relay the message to the thread
            else:
                if isinstance(active_ticket_data, dict):
                    thread_id = active_ticket_data.get("thread_id")
                    is_anonymous = active_ticket_data.get("is_anon", False)
                else:
                    thread_id = active_ticket_data
                    is_anonymous = False

                try:
                    thread = await self.bot.fetch_channel(thread_id)
                    if thread:
                        embed = discord.Embed(
                            description=message.content,
                            color=discord.Color.blue()
                        )
                        if is_anonymous:
                            embed.set_author(name="Anonymous User replied", icon_url=self.bot.user.avatar.url)
                        else:
                            embed.set_author(name=f"{message.author.name} replied", icon_url=message.author.display_avatar.url)

                        await thread.send(embed=embed)
                except discord.NotFound:
                    del self.active_tickets[user_id]
                    self.save_active_tickets()
                    await message.author.send("Your ticket has been closed or deleted. Please start a new one if you need to contact staff again.")
                except Exception as e:
                    print(f"Error relaying message to ticket thread: {e}")


    @app_commands.command(name="reply", description="Reply to the user in a ModMail thread.")
    @app_commands.describe(content="The message to send to the user.")
    @app_commands.guild_only()
    async def reply_slash(self, interaction: discord.Interaction, content: str):
        valid_thread_ids = [ticket.get('thread_id') for ticket in self.active_tickets.values() if isinstance(ticket, dict)]
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and interaction.channel.id in valid_thread_ids:
            user_id = next((uid for uid, tid in self.active_tickets.items() if isinstance(tid, dict) and tid.get('thread_id') == interaction.channel.id), None)

            if user_id:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    
                    user_embed = discord.Embed(
                        description=content,
                        color=discord.Color.blue()
                    )
                    user_embed.set_author(name="Staff Reply", icon_url=self.bot.user.avatar.url)

                    await user.send(embed=user_embed)
                    
                    staff_reply_embed = discord.Embed(
                        description=content,
                        color=discord.Color.blue()
                    )
                    staff_reply_embed.set_author(name=f"Reply from {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
                    await interaction.response.send_message(embed=staff_reply_embed)

                except discord.Forbidden:
                    await interaction.response.send_message("I cannot send a DM to this user. Their DMs may be disabled.", ephemeral=True)
                except discord.NotFound:
                    await interaction.response.send_message("Could not find the user for this ticket.", ephemeral=True)
                except Exception as e:
                    print(f"An unexpected error occurred in /reply: {e}")
                    await interaction.response.send_message("An unexpected error occurred while executing this command.", ephemeral=True)
            else:
                await interaction.response.send_message("This command can only be used in a ModMail thread.", ephemeral=True)
        else:
            await interaction.response.send_message("This command can only be used in a ModMail thread.", ephemeral=True)

    @app_commands.command(name="close", description="Close the current ModMail ticket.")
    @app_commands.guild_only()
    async def close_slash(self, interaction: discord.Interaction):
        valid_thread_ids = [ticket.get('thread_id') for ticket in self.active_tickets.values() if isinstance(ticket, dict)]
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and interaction.channel.id in valid_thread_ids:
            user_id_from_thread = next((uid for uid, tid in self.active_tickets.items() if isinstance(tid, dict) and tid.get('thread_id') == interaction.channel.id), None)
            
            if user_id_from_thread:
                try:
                    user = await self.bot.fetch_user(int(user_id_from_thread))
                    if user:
                        await user.send("Your ModMail ticket has been closed by staff.")
                except:
                    pass
                
                del self.active_tickets[user_id_from_thread]
                self.save_active_tickets()
                
                notification_channel = interaction.guild.get_channel(utils.CHANNEL_IDS.get("modmail_notification_channel_id"))
                if notification_channel:
                    await notification_channel.send(f"Ticket for <@{user_id_from_thread}> has been closed by {interaction.user.mention}.")
                
                await interaction.response.send_message("Closing this ticket in 5 seconds...")
                await asyncio.sleep(5)
                await interaction.channel.edit(archived=True)
            else:
                await interaction.response.send_message("This is not a valid ModMail thread.", ephemeral=True)
        else:
            await interaction.response.send_message("This is not a valid ModMail thread.", ephemeral=True)

    @app_commands.command(name="reveal", description="Reveals the identity of the user who opened this anonymous ticket.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    async def reveal_slash(self, interaction: discord.Interaction):
        valid_thread_ids = [ticket.get('thread_id') for ticket in self.active_tickets.values() if isinstance(ticket, dict)]
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and interaction.channel.id in valid_thread_ids:
            active_ticket_data = next((tid for tid in self.active_tickets.values() if isinstance(tid, dict) and tid.get('thread_id') == interaction.channel.id), None)
            
            if active_ticket_data and active_ticket_data.get('is_anon'):
                user_id = next((uid for uid, tid in self.active_tickets.items() if isinstance(tid, dict) and tid.get('thread_id') == interaction.channel.id), None)
                if user_id:
                    user = await self.bot.fetch_user(int(user_id))
                    if user:
                        await interaction.response.send_message(f"This thread was opened by {user.mention}.", ephemeral=False)
                    else:
                        await interaction.response.send_message("Could not find the user for this ticket.", ephemeral=True)
                else:
                    await interaction.response.send_message("The user for this ticket could not be found in the bot's records.", ephemeral=True)
            else:
                await interaction.response.send_message("This is not an anonymous ticket.", ephemeral=True)
        else:
            await interaction.response.send_message("This command can only be used in a ModMail thread.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModmailCore(bot))
