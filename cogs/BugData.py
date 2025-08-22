import os
import cogs.utils as utils
import math

# File paths for data storage
BUG_COLLECTION_FILE = os.path.join("data", "bug_collection.json")
SHOP_ITEMS_FILE = os.path.join("data", "shop_items.json")

# A representation of your shop_items.json file, assuming it's a list of dictionaries.
# The `type` key is for distinguishing between items.
# The `value` is the sell price, and `cost` is the purchase price.
SHOP_ITEMS = [
    {"name": "Basic Net", "cost": 100, "type": "net", "durability": 10},
    {"name": "Regular Net", "cost": 250, "type": "net", "durability": 25},
    {"name": "Strong Net", "cost": 500, "type": "net", "durability": 50},
    {"name": "beehive", "cost": 1000, "type": "beehive"},
    {"name": "bees", "cost": 50, "type": "bees"},
    {"name": "honey", "value": 200, "type": "honey"}
]


# Insect list with stats, emojis, and shiny chance
INSECT_LIST = [
    {"name": "Hercules Beetle", "xp": 80, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1},
    {"name": "Monarch Butterfly", "xp": 60, "emoji": "🦋", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 3},
    {"name": "Ladybug", "xp": 40, "emoji": "🐞", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 5},
    {"name": "Dragonfly", "xp": 75, "emoji": "🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2},
    {"name": "Cicada", "xp": 35, "emoji": "🪰", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 4},
    {"name": "Honey Bee", "xp": 50, "emoji": "🐝", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 3},
    {"name": "Atlas Moth", "xp": 90, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1},
    {"name": "Firefly", "xp": 25, "emoji": "✨", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 5},
    {"name": "Grasshopper", "xp": 30, "emoji": "🦗", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 4},
    {"name": "Praying Mantis", "xp": 70, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2},
    {"name": "Scarab Beetle", "xp": 85, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1},
    {"name": "Orchid Mantis", "xp": 95, "emoji": "🌸", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.5},
    {"name": "Tarantula Hawk", "xp": 100, "emoji": "🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.25},
    {"name": "Goliath Beetle", "xp": 110, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.1},
    {"name": "Emperor Dragonfly", "xp": 120, "emoji": "🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.5},
    {"name": "Ant", "xp": 20, "emoji": "🐜", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 7},
    {"name": "Worm", "xp": 15, "emoji": "🪱", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 8},
    {"name": "Snail", "xp": 25, "emoji": "🐌", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 6},
    {"name": "Mosquito", "xp": 10, "emoji": "🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 10},
    {"name": "Centipede", "xp": 45, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 3},
    {"name": "Horned Beetle", "xp": 90, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1.5},
    {"name": "Blue Morpho Butterfly", "xp": 70, "emoji": "🦋", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2},
    {"name": "Stag Beetle", "xp": 65, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2.5},
    {"name": "Jewel Beetle", "xp": 88, "emoji": "💎", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.8},
    {"name": "Death's-Head Hawk Moth", "xp": 95, "emoji": "💀", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.75},
    {"name": "Giant Weta", "xp": 105, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.6},
    {"name": "Emperor Scorpion", "xp": 115, "emoji": "🦂", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.4},
    {"name": "Rhinoceros Beetle", "xp": 92, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1.2},
    {"name": "Walking Stick", "xp": 40, "emoji": "🪵", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 4.5},
    {"name": "Caterpillar", "xp": 15, "emoji": "🐛", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 8},
    {"name": "Black Widow Spider", "xp": 130, "emoji": "🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.2},
    {"name": "Centipede", "xp": 45, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 3},
    {"name": "Horned Beetle", "xp": 90, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1.5},
    {"name": "Blue Morpho Butterfly", "xp": 70, "emoji": "🦋", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2},
    {"name": "Stag Beetle", "xp": 65, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2.5},
    {"name": "Jewel Beetle", "xp": 88, "emoji": "💎", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.8},
    {"name": "Death's-Head Hawk Moth", "xp": 95, "emoji": "💀", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.75},
    {"name": "Giant Weta", "xp": 105, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.6},
    {"name": "Emperor Scorpion", "xp": 115, "emoji": "🦂", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.4},
    {"name": "Rhinoceros Beetle", "xp": 92, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1.2},
    {"name": "Walking Stick", "xp": 40, "emoji": "🪵", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 4.5},
    {"name": "Caterpillar", "xp": 15, "emoji": "🐛", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 8},
    {"name": "Black Widow Spider", "xp": 130, "emoji": "🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.2},
    {"name": "House Fly", "xp": 10, "emoji": "🪰", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 12},
    {"name": "Robber Fly", "xp": 30, "emoji": "🪰", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 5},
    {"name": "Damselfly", "xp": 55, "emoji": "🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 3.5},
    {"name": "Water Strider", "xp": 20, "emoji": "💧", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 6},
    {"name": "Dung Beetle", "xp": 40, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 4},
    {"name": "Weevil", "xp": 30, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 5},
    {"name": "Jumping Spider", "xp": 60, "emoji": "🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2},
    {"name": "Silverfish", "xp": 10, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 15},
    {"name": "Earwig", "xp": 12, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 12},
    {"name": "Pill Bug", "xp": 15, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 10},
    {"name": "Millipede", "xp": 25, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 6},
    {"name": "Centipede", "xp": 50, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 3},
    {"name": "Wasp", "xp": 75, "emoji": "🐝", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 2.5},
    {"name": "Hornet", "xp": 90, "emoji": "🐝", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 1.5},
    {"name": "Leaf-Cutter Ant", "xp": 40, "emoji": "🐜", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 4},
    {"name": "Termite", "xp": 30, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 5},
    {"name": "Giant Water Bug", "xp": 100, "emoji": "🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp", "shiny_chance": 0.5}
]

# Shiny insect list with special emojis and images
SHINY_INSECT_LIST = [
    {"name": "Shiny Hercules Beetle", "xp": 160, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Monarch Butterfly", "xp": 120, "emoji": "🌟🦋", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Ladybug", "xp": 80, "emoji": "🌟🐞", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Dragonfly", "xp": 150, "emoji": "🌟🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Cicada", "xp": 70, "emoji": "🌟🪰", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Honey Bee", "xp": 100, "emoji": "🌟🐝", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Atlas Moth", "xp": 180, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Firefly", "xp": 50, "emoji": "🌟✨", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Grasshopper", "xp": 60, "emoji": "🌟🦗", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Praying Mantis", "xp": 140, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Scarab Beetle", "xp": 170, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Orchid Mantis", "xp": 190, "emoji": "🌟🌸", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Tarantula Hawk", "xp": 200, "emoji": "🌟🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Goliath Beetle", "xp": 220, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Emperor Dragonfly", "xp": 240, "emoji": "🌟🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Ant", "xp": 40, "emoji": "🌟🐜", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Worm", "xp": 30, "emoji": "🌟🪱", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Snail", "xp": 50, "emoji": "🌟🐌", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Mosquito", "xp": 20, "emoji": "🌟🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Centipede", "xp": 90, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Horned Beetle", "xp": 180, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Blue Morpho Butterfly", "xp": 140, "emoji": "🌟🦋", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Stag Beetle", "xp": 130, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Jewel Beetle", "xp": 176, "emoji": "🌟💎", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Death's-Head Hawk Moth", "xp": 190, "emoji": "🌟💀", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Giant Weta", "xp": 210, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Emperor Scorpion", "xp": 230, "emoji": "🌟🦂", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Rhinoceros Beetle", "xp": 184, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Walking Stick", "xp": 80, "emoji": "🌟🪵", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Caterpillar", "xp": 30, "emoji": "🌟🐛", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Black Widow Spider", "xp": 260, "emoji": "🌟🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny House Fly", "xp": 20, "emoji": "🌟🪰", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Robber Fly", "xp": 60, "emoji": "🌟🪰", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Damselfly", "xp": 110, "emoji": "🌟🦟", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Water Strider", "xp": 40, "emoji": "🌟💧", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Dung Beetle", "xp": 80, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Weevil", "xp": 60, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Jumping Spider", "xp": 120, "emoji": "🌟🕷️", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Silverfish", "xp": 20, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Earwig", "xp": 24, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Pill Bug", "xp": 30, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Millipede", "xp": 50, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Centipede", "xp": 100, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Wasp", "xp": 150, "emoji": "🌟🐝", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Hornet", "xp": 180, "emoji": "🌟🐝", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Leaf-Cutter Ant", "xp": 80, "emoji": "🌟🐜", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Termite", "xp": 60, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"},
    {"name": "Shiny Giant Water Bug", "xp": 200, "emoji": "🌟🪲", "image_url": "https://media.discordapp.net/attachments/1157737246162681876/1266205737525330030/1715767252273.webp"}
]


def load_bug_collection():
    return utils.load_data(BUG_COLLECTION_FILE, {})

def save_bug_collection(data):
    utils.save_data(data, BUG_COLLECTION_FILE)

def load_shop_items():
    return utils.load_data(SHOP_ITEMS_FILE, [])

def calculate_level_from_xp(xp):
    return math.floor(0.1 * math.sqrt(xp))
