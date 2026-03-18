import discord
from discord import app_commands
from discord.ext import commands
from modules.logger import bot_logger

class easter_egg(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

# ==========================================
# [이스터에그] eodu
# ==========================================

    @app_commands.command(name="eodu", description="?")
    async def eodu(self, interaction: discord.Interaction):
        nick = await self.bot.db.get_user_nickname(interaction.user.id) or interaction.user.display_name
        embed = discord.Embed(
            description=f"{nick}님, 한영키를 한번 확인해 볼까요?",
            color=discord.Color.brand_red()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="qksskq", description="?")
    async def qksskq(self, interaction: discord.Interaction):
        nick = await self.bot.db.get_user_nickname(interaction.user.id) or interaction.user.display_name
        embed = discord.Embed(
            description=f"{nick}님, 한영키를 한번 확인해 볼까요?",
            color=discord.Color.og_blurple()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="섬", description="?")
    async def island_warp(self, interaction: discord.Interaction, sub: str = None, sub2: str = None):
        nick = await self.bot.db.get_user_nickname(interaction.user.id) or interaction.user.display_name
        embed = discord.Embed(
            description=f"{nick}님, 디스코드 말고 마인크래프트 창을 눌러볼까요?",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(easter_egg(bot))