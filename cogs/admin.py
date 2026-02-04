import discord
from discord import app_commands
from discord.ext import commands
import os
import glob
import datetime
import unicodedata # [추가] 표 정렬을 위해 필요
from modules.logger import bot_logger, LOG_DIR

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # [Internal Helper] 표 정렬 함수 (Admin 전용)
    # ==========================================
    def _get_width(self, text):
        """한글 등 전각 문자는 너비 2, 반각은 1로 계산"""
        width = 0
        for char in text:
            if unicodedata.east_asian_width(char) in ['W', 'F', 'A']:
                width += 2
            else:
                width += 1
        return width

    def _pad_text(self, text, target_width):
        """표 정렬을 위한 공백 채우기"""
        text = str(text) if text else "-"
        current_width = self._get_width(text)
        
        if current_width > target_width:
            temp = ""
            curr = 0
            for char in text:
                w = 2 if unicodedata.east_asian_width(char) in ['W', 'F', 'A'] else 1
                if curr + w > target_width - 2: break
                temp += char
                curr += w
            return temp + ".." + " " * (target_width - (curr + 2))
        else:
            return text + " " * (target_width - current_width)

    # ==========================================
    # [Helper] 자동완성 로직 모음
    # ==========================================
    
    # 1. 로그 날짜 자동완성
    async def log_date_autocomplete(self, interaction: discord.Interaction, current: str):
        dates = []
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        if os.path.exists(os.path.join(LOG_DIR, "bot.log")):
            dates.append(today_str)
            
        for f in glob.glob(os.path.join(LOG_DIR, "bot.log.20*")):
            date_part = f.split(".")[-1]
            dates.append(date_part)
            
        dates.sort(reverse=True)
        return [app_commands.Choice(name=d, value=d) for d in dates if current in d][:25]

    # 2. 도구 카테고리 자동완성
    async def tool_category_autocomplete(self, interaction: discord.Interaction, current: str):
        tools_cog = self.bot.get_cog("Tools")
        if not tools_cog: return []
        
        return [
            app_commands.Choice(name=t, value=t)
            for t in sorted(list(tools_cog.cache_categories)) if current in t
        ][:25]

    # 3. 모든 도구 이름 자동완성 (삭제용)
    async def tool_name_autocomplete(self, interaction: discord.Interaction, current: str):
        tools_cog = self.bot.get_cog("Tools")
        if not tools_cog: return []

        selected_category = interaction.namespace.category
        
        if selected_category and selected_category in tools_cog.cache:
            return [
                app_commands.Choice(name=n, value=n)
                for n in sorted(tools_cog.cache[selected_category].keys()) 
                if current in n
            ][:25]
        return []

    # 4. [최적화됨] 대여 중인 도구만 자동완성 (강제반납용)
    async def borrowed_tool_name_autocomplete(self, interaction: discord.Interaction, current: str):
        tools_cog = self.bot.get_cog("Tools")
        if not tools_cog: return []

        selected_category = interaction.namespace.category
        
        if selected_category and selected_category in tools_cog.cache:
            choices = []
            for name, info in tools_cog.cache[selected_category].items():
                # 대여 중인 것(borrower_id가 있는 것)만 필터링
                if info['borrower_id'] is not None:
                    # 검색어가 포함된 경우 확인
                    if not current or current in name:
                        choices.append(app_commands.Choice(name=name, value=name))
                        
                        # [Speed Up] 25개 꽉 차면 즉시 중단 (Early Exit)
                        if len(choices) >= 25:
                            break
            
            return choices
        return []

    # ==========================================
    # [Command 1] 로그 조회
    # ==========================================
    @app_commands.command(name="로그조회", description="[관리자] 특정 날짜의 로그 파일을 다운로드합니다.")
    @app_commands.autocomplete(date=log_date_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def get_log(self, interaction: discord.Interaction, date: str):
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        file_path = None
        
        if date == today_str:
            target = os.path.join(LOG_DIR, "bot.log")
            if os.path.exists(target): file_path = target
        else:
            target = os.path.join(LOG_DIR, f"bot.log.{date}")
            if os.path.exists(target): file_path = target
                
        if file_path:
            await interaction.response.send_message(
                f"📂 **{date}** 로그 파일입니다.",
                file=discord.File(file_path, filename=f"log_{date}.txt"),
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ 해당 날짜의 로그 파일을 찾을 수 없습니다.", ephemeral=True)

    # ==========================================
    # [Command 2] 도구 관리 (추가)
    # ==========================================
    @app_commands.command(name="도구관리_추가", description="[관리자] 새로운 도구를 목록에 추가합니다.")
    @app_commands.describe(category="도구 종류", name="도구 이름")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(category=tool_category_autocomplete)
    async def add_tool(self, interaction: discord.Interaction, category: str, name: str):
        if await self.bot.db.add_tool(category, name):
            tools_cog = self.bot.get_cog("Tools")
            if tools_cog: await tools_cog.sync_cache()
            
            bot_logger.info(f"[+] [Admin] 도구 추가: {category} - {name} by {interaction.user.name}")
            await interaction.response.send_message(f"✅ **[{category}] {name}** 추가 완료!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ 이미 존재하는 도구입니다.", ephemeral=True)

    # ==========================================
    # [Command 3] 도구 관리 (삭제)
    # ==========================================
    @app_commands.command(name="도구관리_삭제", description="[관리자] 기존 도구를 목록에서 삭제합니다.")
    @app_commands.describe(category="도구 종류", name="도구 이름")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(category=tool_category_autocomplete, name=tool_name_autocomplete)
    async def remove_tool(self, interaction: discord.Interaction, category: str, name: str):
        if await self.bot.db.remove_tool(category, name):
            tools_cog = self.bot.get_cog("Tools")
            if tools_cog: await tools_cog.sync_cache()
                
            bot_logger.info(f"[-] [Admin] 도구 삭제: {category} - {name} by {interaction.user.name}")
            await interaction.response.send_message(f"🗑️ **[{category}] {name}** 삭제 완료!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ 존재하지 않는 도구입니다.", ephemeral=True)

    # ==========================================
    # [Command 4] 강제 반납
    # ==========================================
    @app_commands.command(name="강제반납", description="[관리자] 대여 중인 도구를 강제로 반납 처리합니다.")
    @app_commands.describe(category="도구 종류", name="도구 이름")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(category=tool_category_autocomplete, name=borrowed_tool_name_autocomplete)
    async def force_return(self, interaction: discord.Interaction, category: str, name: str):
        await interaction.response.defer(ephemeral=True)
        
        status = await self.bot.db.get_tool_status(category, name)
        
        if not status:
            return await interaction.followup.send("❌ 존재하지 않는 도구입니다.")
        
        b_id = status[0]
        if b_id is None:
            return await interaction.followup.send(f"👀 **[{category}] {name}**은(는) 이미 반납된 상태입니다.")

        # [NEW] DM 발송 로직
        dm_result = ""
        try:
            # 빌려간 유저 객체 찾기
            target_user = await self.bot.fetch_user(b_id)
            
            # DM 내용 구성
            embed = discord.Embed(
                title="📢 관리 알림",
                description=f"관리자에 의해 **[{category}] {name}** 도구가 **강제 반납** 처리되었습니다.\n**다음부터는 잊지 말고 직접 반납해 주세요!**",
                color=discord.Color.orange()
            )
            await target_user.send(embed=embed)
            dm_result = "(DM 전송됨)"
        except discord.Forbidden:
            dm_result = "(DM 차단됨)"
        except Exception:
            dm_result = "(DM 실패/유저없음)"

        # DB 업데이트 (반납 처리)
        await self.bot.db.update_borrow(category, name, None, None, None, None)
        
        # 캐시 동기화
        tools_cog = self.bot.get_cog("Tools")
        if tools_cog: await tools_cog.sync_cache()

        # 로그 및 관리자 응답
        bot_logger.info(f"[!] [Admin] 강제반납 실행: {category}-{name} (User: {b_id}) {dm_result} by {interaction.user.name}")
        await interaction.followup.send(f"✅ **[{category}] {name}** 강제 반납 처리가 완료되었습니다. {dm_result}")

    # ==========================================
    # [Command 5] 전체 대여 현황 리포트
    # ==========================================
    @app_commands.command(name="전체대여현황", description="[관리자] 현재 대여 중인 도구 목록만 파일로 확인합니다.")
    @app_commands.default_permissions(administrator=True)
    async def report_rent(self, interaction: discord.Interaction):
        tools_cog = self.bot.get_cog("Tools")
        if not tools_cog:
            return await interaction.response.send_message("❌ Tools 모듈이 로드되지 않았습니다.", ephemeral=True)

        lines = []
        now_str = self.bot.db.get_korea_time()
        lines.append(f"[ 전체 대여 현황 Report - {now_str} ]\n")
        
        count = 0
        for cat, tools in tools_cog.cache.items():
            for name, info in tools.items():
                if info['borrower_id'] is not None:
                    nick = info['borrower_nick'] or info['borrower_name']
                    time = info['borrowed_at']
                    lines.append(f"[{cat}] {name} | 대여자: {nick} | 시간: {time}")
                    count += 1
        
        if count == 0:
            return await interaction.response.send_message("👀 현재 대여 중인 도구가 없습니다.", ephemeral=True)

        filename = f"rent_report_{now_str[:10]}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        await interaction.response.send_message(
            f"📂 총 {count}개의 대여 항목이 있습니다.", 
            file=discord.File(filename), 
            ephemeral=True
        )
        os.remove(filename)

    # ==========================================
    # [Command 6] 유저 대여 조회
    # ==========================================
    @app_commands.command(name="유저대여조회", description="[관리자] 특정 유저가 대여 중인 도구를 조회합니다.")
    @app_commands.describe(user="조회할 유저")
    @app_commands.default_permissions(administrator=True)
    async def admin_user_info(self, interaction: discord.Interaction, user: discord.User):
        # DB 조회 (await 필수)
        items = await self.bot.db.get_user_borrowed_tools(user.id)
        
        if not items:
            return await interaction.response.send_message(f"📜 **{user.display_name}**님은 대여 중인 도구가 없습니다.", ephemeral=True)
        
        header = f"{self._pad_text('종류', 8)} | {self._pad_text('이름', 20)} | 대여 시간"
        separator = "-" * 45
        
        body = ""
        for category, name, time in items:
            cat_str = self._pad_text(category, 8)
            name_str = self._pad_text(name, 20)
            
            # 시간 포맷 (MM-DD HH:MM)
            if time:
                time_str = time[5:-3] # 2024-02-05 14:00:00 -> 02-05 14:00
            else:
                time_str = "?"
                
            body += f"{cat_str} | {name_str} | {time_str}\n"
        
        msg = f"**[ 🔍 {user.display_name}님의 대여 현황 ]**\n```text\n{header}\n{separator}\n{body}```"
        await interaction.response.send_message(msg, ephemeral=True)

    # ==========================================
    # [Command 7] 전체 도구 현황 (파일)
    # ==========================================
    @app_commands.command(name="전체도구현황", description="[관리자] 대여 여부와 상관없이 등록된 모든 도구 목록을 파일로 확인합니다.")
    @app_commands.default_permissions(administrator=True)
    async def all_tool_status(self, interaction: discord.Interaction):
        # 1. 모든 도구 조회 (await 필수)
        items = await self.bot.db.get_all_tools()
        
        if not items:
            return await interaction.response.send_message("❌ 등록된 도구가 없습니다.", ephemeral=True)
        
        # 2. 파일 내용 작성
        lines = []
        now_str = self.bot.db.get_korea_time()
        
        lines.append(f"[ 전체 도구 목록 Report ]")
        lines.append(f"기준 시간: {now_str}")
        lines.append(f"총 도구 수: {len(items)}개")
        lines.append("")
        
        # 헤더 설정
        col_cat, col_name, col_stat, col_who = 10, 24, 10, 24
        header = f"{self._pad_text('종류', col_cat)} | {self._pad_text('이름', col_name)} | {self._pad_text('상태', col_stat)} | {self._pad_text('대여자', col_who)} | 대여 시간"
        separator = "-" * 95
        
        lines.append(header)
        lines.append(separator)
        
        for category, name, b_id, b_name, b_nick, time in items:
            cat_str = self._pad_text(category, col_cat)
            name_str = self._pad_text(name, col_name)
            
            if b_id is None:
                # 대여 가능한 상태
                stat_str = self._pad_text("대여가능", col_stat)
                who_str = self._pad_text("-", col_who)
                time_str = "-"
            else:
                # 대여 중인 상태
                stat_str = self._pad_text("대여중", col_stat)
                full_name = f"{b_nick}({b_name})" if b_nick else b_name
                who_str = self._pad_text(full_name, col_who)
                time_str = time if time else "?"
                
            lines.append(f"{cat_str} | {name_str} | {stat_str} | {who_str} | {time_str}")
        
        # 3. 파일 생성 및 전송
        filename = f"all_tools_{now_str[:10]}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            await interaction.response.send_message("📂 **전체 도구 현황**입니다.", file=discord.File(filename), ephemeral=True)
        finally:
            if os.path.exists(filename): os.remove(filename)

async def setup(bot):
    await bot.add_cog(Admin(bot))