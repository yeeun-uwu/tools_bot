import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import pytz
from modules.logger import bot_logger

# ==========================================
# [UI View 1] 알림 메시지용 버튼 (일회성)
# ==========================================
class ClearMiningView(discord.ui.View):
    def __init__(self, bot, dashboard_updater):
        super().__init__(timeout=None)
        self.bot = bot
        self.update_dashboard = dashboard_updater

    @discord.ui.button(label="상자 비움 완료", style=discord.ButtonStyle.success, emoji="🗑️")
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        # DB 업데이트
        now = self.bot.db.get_korea_time()
        await self.bot.db.update_mining_last_cleared(now, interaction.user.id)
        
        # 로그
        user_nick = await self.bot.db.get_user_nickname(interaction.user.id) or interaction.user.display_name
        bot_logger.info(f"[+] [Mining] 알림 버튼으로 비움 완료: {user_nick}")

        # 버튼 비활성화
        button.disabled = True
        button.label = f"비움 완료 ({user_nick})"
        await interaction.followup.edit_message(message_id=interaction.message.id, view=self)

        # 알림 메시지 삭제 예약
        await interaction.message.delete(delay=300) 

        # 대시보드 갱신
        await self.update_dashboard()
        await interaction.followup.send("✅ 상자를 비웠습니다! 타이머가 리셋되었습니다.", ephemeral=True)


# ==========================================
# [UI View 2] 대시보드 부착용 버튼 (상시 유지)
# ==========================================
class DashboardView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # 중요: 타임아웃 없음
        self.bot = bot

    @discord.ui.button(label="잠광 시작", style=discord.ButtonStyle.success, emoji="⛏️", custom_id="mining_dash_start_btn", row=0)
    async def dash_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if await self.bot.db.add_mining_user(interaction.user.id):
            bot_logger.info(f"[+] [Mining] 대시보드 시작: {interaction.user.name}")
            cog = self.bot.get_cog("Mining")
            if cog: await cog.update_dashboard()
            await interaction.followup.send("⛏️ 잠광 시작이 기록되었습니다!", ephemeral=True)
        else:
            await interaction.followup.send("👀 이미 진행 중으로 등록되어 있습니다.", ephemeral=True)

    @discord.ui.button(label="잠광 종료", style=discord.ButtonStyle.danger, emoji="👋", custom_id="mining_dash_end_btn", row=0)
    async def dash_end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if await self.bot.db.remove_mining_user(interaction.user.id):
            bot_logger.info(f"[-] [Mining] 대시보드 종료: {interaction.user.name}")
            cog = self.bot.get_cog("Mining")
            if cog: await cog.update_dashboard()
            await interaction.followup.send("👋 수고하셨습니다! 종료 처리되었습니다.", ephemeral=True)
        else:
            await interaction.followup.send("❌ 진행 중인 잠광 기록이 없습니다.", ephemeral=True)

    @discord.ui.button(label="상자 비움 (타이머 리셋)", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="mining_dash_clear_btn", row=1)
    async def dash_clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 권한 체크 (현재는 모두 허용)
        await interaction.response.defer()

        # DB 업데이트
        now = self.bot.db.get_korea_time()
        await self.bot.db.update_mining_last_cleared(now, interaction.user.id)
        
        user_nick = await self.bot.db.get_user_nickname(interaction.user.id) or interaction.user.display_name
        bot_logger.info(f"[+] [Mining] 대시보드에서 비움/리셋: {user_nick}")

        # 대시보드 즉시 갱신
        cog = self.bot.get_cog("Mining")
        if cog: await cog.update_dashboard()
        
        await interaction.followup.send("✅ 상자 비움 처리 완료! 타이머가 0분으로 초기화되었습니다.", ephemeral=True)


# ==========================================
# [Cog] 잠광 매니저
# ==========================================
class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.alert_sent = False
        self.check_mining_timer.start()

    async def cog_unload(self):
        self.check_mining_timer.cancel()

    # ==========================================
    # [Helper] 대시보드(현황판) 업데이트 로직
    # ==========================================
    async def update_dashboard(self):
        """잠광 현황 메시지를 갱신하거나 새로 보냅니다."""
        config = await self.bot.db.get_mining_config() 
        if not config: return

        channel_id, _, last_cleared, msg_id, last_cleared_user_id = config
        channel = self.bot.get_channel(channel_id)
        if not channel: return

        users = await self.bot.db.get_all_mining_users()
        
        # Embed 구성
        embed = discord.Embed(title="💸 잠광 현황판", color=discord.Color.gold())
        kst = pytz.timezone('Asia/Seoul')
        
        if last_cleared:
            dt = datetime.datetime.strptime(last_cleared, '%Y-%m-%d %H:%M:%S')
            dt = kst.localize(dt) 
            timestamp = int(dt.timestamp())

            clear_user_nick = "알 수 없음"
            if last_cleared_user_id:
                clear_user_nick = await self.bot.db.get_user_nickname(last_cleared_user_id) or f"ID:{last_cleared_user_id}"
                if not clear_user_nick:
                    try:
                        u_obj = await self.bot.fetch_user(last_cleared_user_id)
                        clear_user_nick = u_obj.display_name
                    except:
                        pass

            time_field = f"<t:{timestamp}:T> (<t:{timestamp}:R>) - 마지막 비움: **{clear_user_nick}**님"
        else:
            time_field = "기록 없음"
            
        embed.add_field(name="🗑️ 마지막 비움", value=time_field, inline=False)

        if users:
            user_lines = []
            for uid, start_time in users:
                nick = await self.bot.db.get_user_nickname(uid)
                if not nick:
                    try:
                        u_obj = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                        nick = u_obj.display_name
                    except:
                        nick = "Unknown"
                
                s_dt = datetime.datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                s_dt = kst.localize(s_dt)
                s_ts = int(s_dt.timestamp())
                
                user_lines.append(f"👤 **{nick}** (~<t:{s_ts}:R>)")
            
            embed.add_field(name=f"🌕 잠광 인원 ({len(users)}명)", value="\n".join(user_lines), inline=False)
            embed.set_footer(text="상자 비움 알림은 1시간 50분마다 발송됩니다.")
            embed.color = discord.Color.green()
        else:
            embed.add_field(name="🌑 잠광 인원", value="현재 잠광 중인 인원이 없습니다.", inline=False)
            embed.set_footer(text="/잠광시작 명령어 혹은 버튼 상호작용을 통해 등록해주세요.")
            embed.color = discord.Color.light_grey()

        # 대시보드용 버튼 뷰 생성
        view = DashboardView(self.bot)

        # 메시지 전송/수정 로직
        dashboard_msg = None
        
        if msg_id:
            try:
                dashboard_msg = await channel.fetch_message(msg_id)
                # 메시지 내용과 함께 view(버튼)도 업데이트
                await dashboard_msg.edit(embed=embed, view=view)
            except discord.NotFound:
                dashboard_msg = None
        
        if dashboard_msg is None:
            new_msg = await channel.send(embed=embed, view=view)
            await self.bot.db.update_mining_dashboard_id(new_msg.id)

    # ==========================================
    # [Task] 1분 주기 타이머 체크
    # ==========================================
    @tasks.loop(minutes=1)
    async def check_mining_timer(self):
        config = await self.bot.db.get_mining_config()
        if not config: return
        channel_id, role_id, last_cleared, msg_id, last_cleared_user_id = config

        if not last_cleared or not channel_id: return

        users = await self.bot.db.get_all_mining_users()
        if not users:
            self.alert_sent = False
            return

        kst = pytz.timezone('Asia/Seoul')
        now = datetime.datetime.now(kst)
        
        last = datetime.datetime.strptime(last_cleared, '%Y-%m-%d %H:%M:%S')
        last = kst.localize(last) 
        
        diff = now - last
        minutes_diff = diff.total_seconds() / 60

        # 110분 = 1시간 50분
        if minutes_diff >= 110:
            if not self.alert_sent:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    role_mention = f"<@&{role_id}>" if role_id else "@here"
                    
                    # 알림 메시지용 뷰 (DashboardView가 아님)
                    view = ClearMiningView(self.bot, self.update_dashboard)
                    await channel.send(
                        f"🚨 {role_mention} **상자 비움 알림**\n잠광 시작 후 1시간 50분이 경과했습니다! 상자를 비워주세요.",
                        view=view
                    )
                    
                    bot_logger.info(f"[+] [Mining] 시간 경과 알림 발송 ({int(minutes_diff)}분 경과)")
                    self.alert_sent = True
        else:
            self.alert_sent = False

    @check_mining_timer.before_loop
    async def before_timer(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # [Command 1] 설정 (관리자)
    # ==========================================
    @app_commands.command(name="잠광설정", description="[관리자] 잠광 알림 채널과 역할을 설정합니다.")
    @app_commands.describe(channel="알림을 보낼 채널", role="호출할 역할 (비우면 @here로 설정)")
    @app_commands.default_permissions(administrator=True)
    async def set_config(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
        role_id = role.id if role else None

        await self.bot.db.set_mining_config(channel.id, role_id)
        
        now = self.bot.db.get_korea_time()
        await self.bot.db.update_mining_last_cleared(now)

        role_name = role.name if role else "@here (전체)"
        role_mention = role.mention if role else "@here"
        
        bot_logger.info(f"[+] [Mining] 설정 변경: 채널({channel.name}), 역할({role_name})")
        await interaction.response.send_message(f"✅ 설정 완료!\n채널: {channel.mention}\n역할: {role_mention}", ephemeral=True)
        
        # 5. 대시보드 갱신
        await self.update_dashboard()

    # ==========================================
    # [Command 2] 잠광 시작
    # ==========================================
    @app_commands.command(name="잠광시작", description="잠수 광질을 시작합니다.")
    async def start_mining(self, interaction: discord.Interaction):
        config = await self.bot.db.get_mining_config()
        if config and interaction.channel_id != config[0]:
            return await interaction.response.send_message("❌ 잠광 채널에서만 사용할 수 있습니다.", ephemeral=True)

        if await self.bot.db.add_mining_user(interaction.user.id):
            bot_logger.info(f"[+] [Mining] 시작: {interaction.user.name}")
            await interaction.response.send_message("⛏️ 잠광 시작이 기록되었습니다!", ephemeral=True)
            await self.update_dashboard()
        else:
            await interaction.response.send_message("👀 이미 진행 중으로 등록되어 있습니다.", ephemeral=True)

    # ==========================================
    # [Command 3] 잠광 종료
    # ==========================================
    @app_commands.command(name="잠광종료", description="잠수 광질을 종료합니다.")
    async def end_mining(self, interaction: discord.Interaction):
        if await self.bot.db.remove_mining_user(interaction.user.id):
            bot_logger.info(f"[-] [Mining] 종료: {interaction.user.name}")
            
            users = await self.bot.db.get_all_mining_users()
            remain_msg = f"(남은 인원: {len(users)}명)" if users else "(모두 종료됨)"
            
            await interaction.response.send_message(f"👋 수고하셨습니다! {remain_msg}", ephemeral=True)
            await self.update_dashboard()
        else:
            await interaction.response.send_message("❌ 진행 중인 잠광 기록이 없습니다.", ephemeral=True)

    # ==========================================
    # [Command 4] 강제 조작 (관리자)
    # ==========================================
    @app_commands.command(name="강제잠광", description="[관리자] 유저의 잠광 상태를 강제로 변경합니다.")
    @app_commands.choices(action=[
        app_commands.Choice(name="시작처리", value="start"),
        app_commands.Choice(name="종료처리", value="end")
    ])
    @app_commands.default_permissions(administrator=True)
    async def force_mining(self, interaction: discord.Interaction, action: str, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        
        async def send_dm_warning(target_user, act_str):
            try:
                embed = discord.Embed(
                    title="📢 관리 알림",
                    description=f"관리자에 의해 잠광 상태가 **[{act_str}]** 되었습니다.\n**다음부터는 잊지 말고 직접 기록해 주세요!**",
                    color=discord.Color.orange()
                )
                await target_user.send(embed=embed)
                return "DM 전송됨"
            except discord.Forbidden:
                return "DM 차단됨"
            except Exception:
                return "DM 실패"

        if action == "start":
            if await self.bot.db.add_mining_user(user.id):
                dm_result = await send_dm_warning(user, "시작")
                await interaction.followup.send(f"✅ **{user.display_name}**님을 시작 상태로 등록했습니다. ({dm_result})")
                bot_logger.info(f"[+] [Mining] 강제시작: {user.name} by {interaction.user.name}")
            else:
                await interaction.followup.send(f"⚠️ **{user.display_name}**님은 이미 진행 중입니다.")
        
        else: 
            if await self.bot.db.remove_mining_user(user.id):
                dm_result = await send_dm_warning(user, "종료")
                await interaction.followup.send(f"✅ **{user.display_name}**님을 종료 처리했습니다. ({dm_result})")
                bot_logger.info(f"[-] [Mining] 강제종료: {user.name} by {interaction.user.name}")
            else:
                await interaction.followup.send(f"⚠️ **{user.display_name}**님은 잠광 중이 아닙니다.")
        
        await self.update_dashboard()

    # ==========================================
    # [Command 5] 테스트용 강제 시간 설정 (관리자)
    # ==========================================
    @app_commands.command(name="강제비움시간", description="[관리자/테스트] 마지막 비움 시간을 'N분 전'으로 강제 설정합니다.")
    @app_commands.describe(minutes="몇 분 전으로 돌릴까요? (예: 110 입력 시 즉시 알림 조건 충족)")
    @app_commands.default_permissions(administrator=True)
    async def force_clear_time(self, interaction: discord.Interaction, minutes: int):
        await interaction.response.defer(ephemeral=True)
        # 1. 한국 시간 기준 계산
        kst = pytz.timezone('Asia/Seoul')
        now = datetime.datetime.now(kst)
        
        # 입력한 분(minutes)만큼 과거로 돌림
        target_time = now - datetime.timedelta(minutes=minutes)
        time_str = target_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # 2. DB 업데이트
        await self.bot.db.update_mining_last_cleared(time_str, None)
        
        # 3. 로그 및 대시보드 갱신
        bot_logger.warning(f"[!] [Mining] 관리자 테스트: 비움 시간 {minutes}분 전으로 변경")
        await self.update_dashboard()
        
        # 4. 결과 메시지
        await interaction.followup.send(
            f"🧪 **테스트 모드**: 마지막 비움 시간을 **{minutes}분 전**(`{time_str}`)으로 설정했습니다.\n"
            f"잠시 후 타이머 체크 주기가 돌아오면 알림이 발송될 수 있습니다.",
            ephemeral=True
        )

    # ==========================================
    # [Command 6] 비움 기록 로그 확인 (관리자)
    # ==========================================
    @app_commands.command(name="비움기록", description="[관리자] 최근 비움 기록을 확인합니다.")
    @app_commands.describe(limit="몇 건의 기록을 볼까요? (기본 20)")
    @app_commands.default_permissions(administrator=True)
    async def view_clear_logs(self, interaction: discord.Interaction, limit: int = 20):
        logs = await self.bot.db.get_mining_clear_logs(limit)
        
        if not logs:
            await interaction.response.send_message("📝 최근 비움 기록이 없습니다.", ephemeral=True)
            return

        lines = []
        # limit 개수까지만 화면에 보여주도록 반복 (마지막 1개는 순수하게 계산용)
        for i in range(min(len(logs), limit)):
            uid, time_str = logs[i]
            
            # 닉네임 가져오기 (최적화 적용)
            nick = await self.bot.db.get_user_nickname(uid)
            if not nick:
                try:
                    u_obj = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    nick = u_obj.display_name
                except:
                    nick = "알 수 없음"
            
            # 1. 초 단위까지 표시되도록 포맷 가공 (YYYY- 자르기) -> MM-DD HH:MM:SS
            short_time = time_str[5:]
            
            # 2. 이전 기록과의 시간 차이 계산
            diff_text = ""
            # 현재 로그의 다음 인덱스(i+1)가 이전 시간 로그임 (최신순 정렬이므로)
            if i + 1 < len(logs):
                prev_time_str = logs[i+1][1]
                
                curr_dt = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                prev_dt = datetime.datetime.strptime(prev_time_str, '%Y-%m-%d %H:%M:%S')
                
                diff = curr_dt - prev_dt
                total_seconds = int(diff.total_seconds())
                
                hours, remainder = divmod(total_seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if hours > 0:
                    diff_text = f" `(+{hours}시간 {minutes}분)`"
                else:
                    diff_text = f" `(+{minutes}분)`"
            
            lines.append(f"• {short_time} - **{nick}**{diff_text}")
            
        embed = discord.Embed(title="🗑️ 최근 상자 비움 기록", description="\n".join(lines), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Mining(bot))