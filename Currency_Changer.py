import os
import time
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# Replace with your bot token
DISCORD_BOT_TOKEN = "your bot token here"  

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Simple in-memory cache
rates_cache = {}
CACHE_SECONDS = 3600  # 1 hour

async def get_rates(base: str):
    base = base.upper()

    now = time.time()
    if base in rates_cache:
        cached_time, cached_data = rates_cache[base]
        if now - cached_time < CACHE_SECONDS:
            return cached_data

    url = f"https://open.er-api.com/v6/latest/{base}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"API error: HTTP {response.status}")

            data = await response.json()

    if data.get("result") != "success":
        raise Exception("Could not fetch exchange rates.")

    rates_cache[base] = (now, data)
    return data

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user}")
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Sync failed: {e}")

@bot.tree.command(name="convert", description="Convert an amount from one currency to another")
@app_commands.describe(
    amount="Amount to convert",
    from_currency="Currency code to convert from, e.g. USD",
    to_currency="Currency code to convert to, e.g. EUR"
)
async def convert(
    interaction: discord.Interaction,
    amount: float,
    from_currency: str,
    to_currency: str
):
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if amount <= 0:
        await interaction.response.send_message(
            "Amount must be greater than 0.",
            ephemeral=True
        )
        return

    try:
        data = await get_rates(from_currency)
        rates = data.get("rates", {})

        if to_currency not in rates:
            await interaction.response.send_message(
                f"Unknown target currency: `{to_currency}`",
                ephemeral=True
            )
            return

        rate = rates[to_currency]
        converted = amount * rate

        last_update = data.get("time_last_update_utc", "Unknown")
        next_update = data.get("time_next_update_utc", "Unknown")

        message = (
            f"**{amount:.2f} {from_currency} = {converted:.2f} {to_currency}**\n"
            f"Rate: `1 {from_currency} = {rate:.6f} {to_currency}`\n"
            f"Last update: {last_update}\n"
            f"Next update: {next_update}\n"
            f"Rates by ExchangeRate-API"
        )

        await interaction.response.send_message(message)

    except Exception as e:
        await interaction.response.send_message(
            f"Error: {str(e)}",
            ephemeral=True
        )

bot.run(DISCORD_BOT_TOKEN)