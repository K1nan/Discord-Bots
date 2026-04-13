import asyncio
from typing import Dict, List

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks


DISCORD_BOT_TOKEN = "add your bot token from discord developer portal "

COINS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "BNB": "binancecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
}

CHECK_INTERVAL_SECONDS = 60

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Example alert structure:
# {
#   "user_id": 123,
#   "channel_id": 456,
#   "symbol": "BTC",
#   "target_price": 50000.0,
#   "direction": "above"
# }
alerts: List[Dict] = []


# =========================
# HELPERS
# =========================
async def fetch_coin_price(symbol: str) -> float:
    symbol = symbol.upper()

    if symbol not in COINS:
        raise ValueError(f"Unsupported coin: {symbol}")

    coin_id = COINS[symbol]
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                raise Exception(f"CoinGecko API error: HTTP {response.status}")

            data = await response.json()

    if coin_id not in data or "usd" not in data[coin_id]:
        raise Exception("Could not read coin price from API response.")

    return float(data[coin_id]["usd"])


def format_price(price: float) -> str:
    if price >= 1000:
        return f"${price:,.2f}"
    return f"${price:,.6f}"



@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user}")
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as exc:
        print(f"Command sync failed: {exc}")

    if not check_alerts.is_running():
        check_alerts.start()


# =========================
# COMMANDS
# =========================
@bot.tree.command(name="price", description="Get the current USD price of a crypto coin")
@app_commands.describe(symbol="Coin symbol, for example BTC or ETH")
async def price(interaction: discord.Interaction, symbol: str):
    symbol = symbol.upper()

    try:
        current_price = await fetch_coin_price(symbol)

        embed = discord.Embed(title=f"{symbol} Price", description="Current market price in USD")
        embed.add_field(name="Price", value=format_price(current_price), inline=False)

        supported = ", ".join(COINS.keys())
        embed.set_footer(text=f"Supported coins: {supported}")

        await interaction.response.send_message(embed=embed)
    except ValueError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
    except Exception as exc:
        await interaction.response.send_message(f"Error: {exc}", ephemeral=True)


@bot.tree.command(name="alert", description="Create a price alert for a crypto coin")
@app_commands.describe(
    symbol="Coin symbol, for example BTC or ETH",
    target_price="Target price in USD",
    direction="Choose 'above' or 'below'"
)
@app_commands.choices(direction=[
    app_commands.Choice(name="above", value="above"),
    app_commands.Choice(name="below", value="below"),
])
async def alert(
    interaction: discord.Interaction,
    symbol: str,
    target_price: float,
    direction: app_commands.Choice[str]
):
    symbol = symbol.upper()

    if symbol not in COINS:
        await interaction.response.send_message(
            f"Unsupported coin: {symbol}",
            ephemeral=True
        )
        return

    if target_price <= 0:
        await interaction.response.send_message(
            "Target price must be greater than 0.",
            ephemeral=True
        )
        return

    alert_item = {
        "user_id": interaction.user.id,
        "channel_id": interaction.channel_id,
        "symbol": symbol,
        "target_price": float(target_price),
        "direction": direction.value,
    }

    alerts.append(alert_item)

    await interaction.response.send_message(
        f"Alert created: {symbol} {direction.value} {format_price(target_price)}"
    )


@bot.tree.command(name="alerts", description="Show your active crypto alerts")
async def list_alerts(interaction: discord.Interaction):
    user_alerts = [a for a in alerts if a["user_id"] == interaction.user.id]

    if not user_alerts:
        await interaction.response.send_message("You have no active alerts.", ephemeral=True)
        return

    embed = discord.Embed(title="Your Active Alerts")

    for index, alert_item in enumerate(user_alerts, start=1):
        embed.add_field(
            name=f"Alert {index}",
            value=(
                f"**Coin:** {alert_item['symbol']}\n"
                f"**Direction:** {alert_item['direction']}\n"
                f"**Target:** {format_price(alert_item['target_price'])}"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="clearalerts", description="Remove all of your active alerts")
async def clear_alerts(interaction: discord.Interaction):
    global alerts
    before_count = len(alerts)
    alerts = [a for a in alerts if a["user_id"] != interaction.user.id]
    removed = before_count - len(alerts)

    await interaction.response.send_message(
        f"Removed {removed} alert(s).",
        ephemeral=True
    )


# =========================
# BACKGROUND TASK
# =========================
@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def check_alerts():
    global alerts

    if not alerts:
        return

    remaining_alerts = []

    for alert_item in alerts:
        try:
            current_price = await fetch_coin_price(alert_item["symbol"])
            should_trigger = (
                alert_item["direction"] == "above" and current_price >= alert_item["target_price"]
            ) or (
                alert_item["direction"] == "below" and current_price <= alert_item["target_price"]
            )

            if should_trigger:
                channel = bot.get_channel(alert_item["channel_id"])
                user = bot.get_user(alert_item["user_id"])

                if channel is not None:
                    mention = user.mention if user is not None else "User"
                    await channel.send(
                        f"🚨 {mention} Alert triggered: "
                        f"{alert_item['symbol']} is now {format_price(current_price)} "
                        f"({alert_item['direction']} {format_price(alert_item['target_price'])})"
                    )
            else:
                remaining_alerts.append(alert_item)

        except Exception as exc:
            print(f"Alert check failed for {alert_item['symbol']}: {exc}")
            remaining_alerts.append(alert_item)

        await asyncio.sleep(1)

    alerts = remaining_alerts


@check_alerts.before_loop
async def before_check_alerts():
    await bot.wait_until_ready()


bot.run(DISCORD_BOT_TOKEN)