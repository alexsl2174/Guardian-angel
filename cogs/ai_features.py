# cogs/ai_features.py
# This cog handles the AI help functionality for the bot.
# It listens for messages that mention the bot and use the 'help-' prefix.

import discord
from discord.ext import commands
import re
import cogs.utils as utils # Assuming you have a utils.py file with necessary functions
from collections import deque
from typing import Deque, List, Dict, Any, Optional
import io
from discord import app_commands # FIX: Added the missing import for app_commands
import json # You'll need this for the API call payload
import asyncio # For the sleep function in aiohttp

class AIFeatures(commands.Cog):
    """A cog for handling AI-related chat features."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("AIFeatures cog loaded successfully.")
        
        # FIX: Get the main guild ID from utils to filter events.
        # This assumes utils.py defines MAIN_GUILD_ID.
        self.main_guild_id = utils.MAIN_GUILD_ID

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        
        # --- Check if the message is from the main guild. ---
        if message.guild and message.guild.id != self.main_guild_id:
            return

        is_for_ai_help_query = False
        user_input_for_ai = ""

        # 1. Check if bot is mentioned and the message starts with 'help-'
        if self.bot.user.mentioned_in(message):
            mention_pattern = re.compile(r'<@!?%s>' % self.bot.user.id)
            cleaned_content = mention_pattern.sub('', message.content).strip()

            if cleaned_content.lower().startswith('help-'):
                is_for_ai_help_query = True
                user_input_for_ai = cleaned_content[len('help-'):].strip()

        # Now, process AI interaction if triggered
        if is_for_ai_help_query:
            if not user_input_for_ai:
                await message.reply("Please ask a question after `help-`.")
                return

            print(f"Processing 'help' command. Query: '{user_input_for_ai}'")
            
            # --- USER: Here you need to define your knowledge base string. ---
            # This is the combined knowledge base content from our previous conversation.
            knowledge_base_content = """
            ---
            ## Admin Commands:
            - **emoji add**: "Adds a custom emoji to the server from a given image URL. It requires a staff member with manage_emojis permissions to use /emoji add with a name for the emoji and the image's URL. The bot fetches the image and creates a new emoji in the server."
            - **emoji steal**: "Adds an emoji from another server to the current one. A staff member with manage_emojis permissions uses /emoji steal with the emoji as a string (e.g., <:emoji_name:123456789>). The bot extracts the emoji ID, downloads the image or GIF, and adds it as a new custom emoji."
            - **emoji delete**: "Deletes a custom emoji from the server. A staff member with manage_emojis permissions uses /emoji delete with the emoji they want to remove. The bot verifies the emoji belongs to the server and then deletes it."
            - **currency add**: "Adds a specified amount of currency to a user's balance. A staff member uses /currency add with a member and a positive integer amount. The bot updates the user's balance and sends a confirmation."
            - **currency remove**: "Removes a specified amount of currency from a user's balance. A staff member uses /currency remove with a member and a positive integer amount. The bot deducts the currency from the user's balance and sends a confirmation."
            - **set_channel**: "Sets a specific channel ID dynamically for bot functions. An administrator uses /set_channel with a configuration key name and a channel. The bot saves the channel's ID to its dynamic configuration."
            - **unset_channel**: "Removes a specific channel ID from the bot's configuration. An administrator uses /unset_channel with the name of a configuration key, and the bot removes the corresponding channel ID from its dynamic configuration."
            - **set_role**: "Sets a specific role ID dynamically for bot functions. An administrator uses /set_role with a configuration key name and a role. The bot updates the role's ID in its dynamic configuration."
            - **revivepref**: "Sets the time interval for a periodic chat revival task and allows for immediate testing. An administrator uses /revivepref and can specify an interval in hours. They can also use the test_revive option to trigger the revival logic immediately."
            - **add_update_global_timed_role**: "Adds or updates a server-wide role with a specific expiration date. An administrator uses /add_update_global_timed_role and provides a role and an expiration date (year, month, day, hour, minute). The bot saves this information for a task to later manage the role's removal."
            - **verify**: "Manually verifies a member and assigns them the Verified Access and ID Verified roles. A staff member uses /verify on a member, and the bot assigns the roles, removes the Visitor role, and sends a welcome message to a designated channel."
            - **crossverify**: "Manually cross-verifies a member and assigns them the Cross Verified and ID Verified roles. A staff member uses /crossverify on a member, and the bot assigns the roles, removes the Visitor role, and sends a welcome message to a designated channel."

            ---
            ## Choose your own adventure:
            - **"choose_adventure"**: "Starts a new text-based adventure game. The user runs the /choose_adventure command and can provide an optional theme for the adventure. The bot creates a new private text channel for the game, assigns a special Adventure Player role to the user, and removes their other roles to ensure privacy. It then prompts the user for consent on optional game elements before starting the adventure. The bot saves the user's original roles to restore them when the game ends."
            - **"stopadv"**: "Ends the user's current text adventure game. The user initiates the command with /stopadv. The bot finds the user's game, sends a final message to the game channel, then cleans up the game state. This includes restoring the user's original roles, removing the Adventure Player role, and scheduling the game channel to be deleted after a 60-second delay."
            ---
            ## Tree Games:
            - **"tree"**: "Interacts with the server's Tree of Life. This command displays the tree's current size and status. The user can click buttons to either 'Water' the tree to make it grow or 'Catch a Bug' to get insects and XP. The 'Water' and 'Catch a Bug' buttons are disabled for 2 hours after a user performs an action."
            - **"equip_net"**: "Equips a bug net from the user's inventory. The user runs the command with the name of a net they own, which is then set as their equipped net. If the user doesn't own the specified net, the command will fail."
            - **"bugbook profile"**: "Views your or another user's bugbook profile. This command shows the number of unique insects caught, total insects caught, total bug-related XP, and the last insect the user caught."
            - **"bugbook list"**: "Lists the bugs a user has caught, either their own or another user's. The list is paginated, showing 10 unique bugs per page. The user can navigate through pages using buttons."
            - **"bugbook trade"**: "Proposes a trade of bugs with another user. The user specifies the target user, the bug they are offering, and the bug they want in return. The other user receives a trade proposal with 'Accept' and 'Decline' buttons that expires after three minutes."
            ---
            ## Counting Game:
            - **"countpref"**: "Sets the preferences for the server's counting game. An administrator with manage_guild permissions can use this command to configure various rules. Available options include enabling/disabling consecutive counting, deleting incorrect messages, giving a role to users who miscount, resetting the count to 1 on a miscount ('sudden death'), and choosing between incremental (+1) or decremental (-1) counting modes."
            ---
            ## Economy:
            - **"start_anagram_game"**: "Starts a new Anagram game immediately. This command is for moderators only. The bot selects a word, shuffles it, and posts it in the designated anagram channel. Users have 4 minutes to guess the word, and if no one guesses it in time, the game ends, and the word is revealed."
            - **"balance"**: "Checks your or another member's coin balance. This command displays the user's current coin total in an embed. If no user is specified, it shows the balance for the person who ran the command."
            - **"coinflip"**: "Flips a coin and allows a user to bet money on the outcome. The user chooses 'Heads' or 'Tails' and a bet amount. If they win, they get back their bet amount, and if they lose, the bet amount is deducted from their balance. The command sends an embed showing the result of the flip and the new balance."
            - **"daily"**: "Allows a user to collect a daily coin reward. The reward is a random amount between 200 and 500 coins. The command can only be used once every 24 hours. The response includes a fun phrase and a timestamp for when the next daily reward is available."
            - **"crime"**: "Attempts a crime for a chance to win or lose money. A user can use this command once every 2 hours. The outcome is a random chance of success or failure. If successful, the user earns a random amount of money; if they fail, they lose a random amount of money. The amount is a random integer between 10 and their current money. The command requires a minimum balance of 10 coins to be used."
            - **"rob"**: "Attempts to rob another user for a portion of their coins. This command has a 12-hour cooldown. The robbery is a random chance of success or failure. If successful, the user robs a random amount of money from the target. If it fails, the user gets caught and receives nothing. The target must have at least 2000 coins and the robber needs at least 3000 coins to attempt the robbery."
            - **"work"**: "Allows a user to work for money, with a chance of failure. This command can be used once every 24 hours. The user can earn or lose a random amount of money between 200 and 3000 coins. The outcome is based on a random choice of a good or bad work event, each with an AI-generated or pre-defined phrase."
            - **"modifybal"**: "An owner-only command to manually add or remove a specified amount of coins from a user's balance."
            - **"leaderboard"**: "Shows the top users for a specific game or metric. The user can choose to view the leaderboard for Coins, Bug Book (unique bugs caught), Swear Tally, or Bump Battle points. The command displays the top 10 users for the selected category."
            - **"on_message listener"**: "This is not a command, but a listener that handles two main game mechanics. First, it checks messages in the designated anagram channel for the correct answer. If a user guesses the word correctly, they win 250 coins and the game ends. Second, it listens for specific phrases ('sub point', 'dom point', etc.) in the bump battle and vote channels. When a user posts a trigger phrase, the bot awards a point to the corresponding team (Subs or Doms) and applies a cooldown to the user. When a team reaches 100 points, the bump battle ends, and an announcement is made with a leaderboard."
            ---
            ## Fun Commands:
            - **"gif commands"**: "A collection of commands that send a random GIF based on a specific theme or action. For each GIF type (e.g., baka, hug, kiss, pat), a command with the same name is created. The user can optionally specify another user to direct the action toward. Some of these commands are NSFW and can only be used in NSFW channels."
            - **"qotd"**: "Gets a new Question of the Day from an AI. The command generates a new, creative, and non-controversial question and displays it in an embed. If the AI fails to generate a question, the command will send an error message."
            - **"sendqotd"**: "Sends a custom Question of the Day. This command is for moderators only. An administrator can use this command with a custom question, which the bot will then post in an embed. This allows for manual control over the question."
            ---
            ## Hangry Games:
            - **"hangrygames"**: "Starts a new Hangry Games. The command creates a new game where users can volunteer to be 'tributes' by clicking a 'Join' button. Once enough people have joined (at least 2), an administrator can start the game with a 'Start' button. The game runs automatically, generating events where tributes eliminate each other until only one winner remains. The winner receives coins and an announcement with their game statistics."
            - **"end_hangrygames"**: "Forcefully ends the current Hangry Games. This command is for administrators only. It stops the game events, resets the game state, and cancels the ongoing game."
            - **"run_game_events"**: "This is a background task that drives the game's progression. It runs on a loop, generating random events based on the number of remaining players. Events can be duels between two tributes or a solo death. The bot generates an image and a text description for each event, and updates the game state by eliminating the losers. The task stops when there is a single winner or no tributes left."
            ---
            ## Shop and Inventory:
            - **"item info"**: "Gets more information about a specific item. The command displays a detailed embed about the item, including its name, description, price, and other relevant details like durability for nets or the role it grants when used."
            - **"item use"**: "Uses an item from the user's inventory. The command allows a user to consume an item from their inventory that grants a role. The item is removed from their inventory, and they are given the corresponding role."
            - **"item sell"**: "Sells an item from the user's inventory for half its original price. The command removes the item from the user's inventory and credits their account with 50% of the item's purchase price."
            - **"item inventory"**: "Views the items the user currently owns. The command shows a paginated list of all items and nets in the user's inventory, displaying quantities and durability for nets. It also shows the currently equipped net."
            - **"additem"**: "Adds a new item to the store. This is an administrative command that requires manage_guild permissions. An admin can specify the item's name, price, description, type, emoji, and optional details like an image filename, a purchase requirement, durability, and a role to be granted."
            - **"edititem"**: "Edits an existing item in the store. This is an administrative command for users with manage_guild permissions. An admin can change various attributes of an item, such as its name, price, description, or the role it grants."
            - **"removeitem"**: "Removes an item from the store. This is an administrative command. An admin can use this command to permanently delete an item from the shop's list."
            - **"shop"**: "Displays the items available for purchase in the store. The command presents a paginated list of items with details like name, price, and description. It includes a dropdown menu and navigation buttons to browse and select items."
            ---
            ## Games:
            - **"on_message listener"**: "This is a listener that handles the make_a_sentence game. When a message is sent in the designated channel, it checks if the message contains only a single word. If not, the message is deleted, and the user is told to type one word at a time. The listener then appends the word to the current sentence. If the word ends with punctuation like a period, exclamation mark, or question mark, the sentence is considered finished and is sent to a separate 'finished sentences' channel. The current sentence is then reset."
            - **"addswear"**: "Adds a word to the swear jar list. This command requires manage_guild permissions. The bot checks if the word already exists in the list and adds it if it doesn't, saving the updated list."
            - **"removeswear"**: "Removes a word from the swear jar list. This command requires manage_guild permissions. The bot checks if the word is in the list and removes it if found, saving the updated list."
            - **"swearlist"**: "Shows the current list of words in the swear jar. This command displays a list of all words currently configured in the swear jar."
            - **"checkswear"**: "Checks the current swear tally. This command displays a leaderboard of users and their total count of swear words based on the configured swear jar words."
            - **"on_message listener"**: "This listener handles the swear jar functionality. When a message is sent, it checks each word against the list of configured swear words. If a word matches, the bot increments the swear tally for the user who sent the message and sends a notification in the channel, showing the user's updated swear count."
            ---
            ## Pins:
            - **"pins"**: "Shows or manages your personal pinned messages. When used without any arguments, it displays a list of your pinned messages. Each pin includes the author and a preview of the content, with a clickable link to the original message. You can also use the remove argument with a comma-separated list of pin numbers to delete specific pins from your list. Users can pin a message by reacting to it with a special emoji."
            - **"add_pin_for_user"**: "Adds a message to another user's personal pin list. This is an administrative command that requires manage_messages permissions. An admin can provide a target user and a message link. The bot will then add that message to the target user's list of pinned messages, provided the user's list is not full and the message is not a duplicate."
            - **"on_raw_reaction_add listener"**: "This listener handles the core functionality of pinning messages. When a user reacts to a message with a specific 'pin' emoji, the bot will save a reference to that message in the user's personal pin list. If the user's pin list is full or the message is already pinned, the bot will remove the reaction and will not add the message to the list. The bot also removes the reaction after successfully pinning the message."
            ---
            """
            
            final_prompt = f"""
            You are Guardian Angel, an AI assistant. Your ONLY task is to answer user questions based on the provided Knowledge Base.

            **CRITICAL INSTRUCTIONS:**
            1.  Analyze the User's Question to understand the topic or command they are asking about. Use the provided Knowledge Base as your sole source of information.
            2.  **NEVER** explicitly state that your response is based on the provided Knowledge Base.
            3.  **IMPORTANT:** When the user asks about a technical term like "on_message listener," do not use that term in your response. Instead, describe the functionality of that feature in simple, user-friendly language.
            4.  **IMPORTANT:** If a command description mentions "manage_guild permissions," rephrase it to say "administrator" or "admin" in your answer.
            5.  Formulate a concise and clear summary of the functionality requested.
            6.  If the topic is a specific command, follow the summary with the detailed description for that command only.
            7.  If the topic is a command category, follow the summary with a list of all commands and their descriptions within that category.
            8.  Present the information you found as your answer. **You MUST format this answer using Discord Markdown, such as bullet points (`-`) and bold text (`**`).**
            9.  You MUST reply in the same language as the User's Question.
            10. If you cannot find any information related to the user's query, respond with a polite message indicating that you couldn't find the information and suggest they try asking about a specific command or category.
            
            ---
            KNOWLEDGE BASE: {knowledge_base_content}
            ---
            User's Question: {user_input_for_ai}
            Your Formatted Answer:
            """

            try:
                async with message.channel.typing():
                    # The 'target_language' argument was removed because it caused an error.
                    ai_response_text = await utils.generate_text_with_gemini_with_history(
                        chat_history=[{"role": "user", "parts": [{"text": final_prompt}]}]
                    )
                    if ai_response_text:
                        await message.reply(ai_response_text)
                    else:
                        await message.reply("My AI brain is a bit fuzzy right now, try again later.")
            except Exception as e:
                await message.reply("An error occurred while generating the help response.")
                print(f"Error generating help response: {e}")

            return
    
        await self.bot.process_commands(message)

# The setup function to load the cog.
async def setup(bot):
    await bot.add_cog(AIFeatures(bot))
    print("AIFeatures Cog Loaded!")
