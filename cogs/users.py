import discord
from discord import app_commands
from discord.ext import commands
from modules.logger import bot_logger

class Users(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # [Command 1] 닉네임 설정
    # ==========================================
    @app_commands.command(name="닉네임설정", description="봇에서 사용할 고정 닉네임을 설정합니다.")
    @app_commands.describe(name="사용할 이름")
    async def set_nickname(self, interaction: discord.Interaction, name: str):
        # 1. 유효성 검사 (너무 길거나 짧은 경우)
        if len(name) > 6:
            return await interaction.response.send_message("❌ 닉네임은 6글자 이내로 설정해주세요.", ephemeral=True)
        
        # 2. DB 업데이트
        user_id = interaction.user.id
        await self.bot.db.set_user_nickname(user_id, name)
        
        # 3. [System Log] 텍스트 형식
        bot_logger.info(f"[+] [User] 닉네임 변경: {interaction.user.name}({user_id}) -> {name}")
        
        # 4. [User Message] 이모지 형식
        await interaction.response.send_message(f"✅ **{name}**(으)로 닉네임이 고정되었습니다.\n이제 디스코드 닉네임을 바꿔도 이 이름으로 표시됩니다.", ephemeral=True)

    # ==========================================
    # [Command 2] 닉네임 초기화
    # ==========================================
    @app_commands.command(name="닉네임초기화", description="고정 닉네임을 삭제하고 디스코드 닉네임을 사용합니다.")
    async def reset_nickname(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        
        # 현재 설정된 닉네임이 있는지 확인
        current_nick = await self.bot.db.get_user_nickname(user_id)
        
        if not current_nick:
            return await interaction.response.send_message("👀 설정된 고정 닉네임이 없습니다.", ephemeral=True)
            
        # DB에서 삭제 (현재 로직상 빈 문자열("")로 업데이트하면 get_real_name에서 False 처리됨)
        
        await self.bot.db.set_user_nickname(user_id, "") 
        
        # [System Log]
        bot_logger.info(f"[-] [User] 닉네임 초기화: {interaction.user.name}({user_id})")
        
        # [User Message]
        await interaction.response.send_message("🙇 고정 닉네임이 초기화되었습니다.\n이제 **디스코드 닉네임**이 표시됩니다.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Users(bot))