import discord
from discord import app_commands
from discord.ext import commands
import unicodedata
from modules.logger import bot_logger

class Tools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 자동완성 속도를 위한 메모리 캐시 (DB 부하 방지)
        # 구조: { "곡괭이": { "피닉스 곡괭이": {info...}, ... }, "낚싯대": ... }
        self.cache = {} 
        self.cache_categories = set()

    async def cog_load(self):
        """Cog 로드 시 캐시 초기화"""
        await self.sync_cache()
        bot_logger.info("[+] [Tools] 도구 모듈 로드 및 캐시 동기화 완료")

    async def sync_cache(self):
        """DB 내용을 메모리 캐시로 동기화 (이름순 정렬 저장)"""
        raw_data = await self.bot.db.get_all_tools()
        
        raw_data.sort(key=lambda x: x[1])

        self.cache = {}
        self.cache_categories = set()

        for category, name, b_id, b_name, b_nick, b_at in raw_data:
            if category not in self.cache:
                self.cache[category] = {} # 순서가 보장되는 Dict
            self.cache_categories.add(category)
            
            self.cache[category][name] = {
                'borrower_id': b_id,
                'borrower_name': b_name,
                'borrower_nick': b_nick,
                'borrowed_at': b_at
            }

    # ==========================================
    # [Helper] 유틸리티 함수
    # ==========================================

    def get_width(self, text):
        width = 0
        for char in text:
            if unicodedata.east_asian_width(char) in ['W', 'F', 'A']:
                width += 2
            else:
                width += 1
        return width

    def pad_text(self, text, target_width):
        """표 정렬을 위한 공백 채우기"""
        text = str(text) if text else "-"
        current_width = self.get_width(text)
        
        if current_width > target_width:
            # 너무 길면 자르기 (.. 추가)
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

    async def get_real_name(self, user: discord.User):
        """DB에서 고정 닉네임 조회 -> 없으면 디스코드 닉네임 반환"""
        custom_nick = await self.bot.db.get_user_nickname(user.id)
        if custom_nick:
            return custom_nick
        return user.display_name

    # ==========================================
    # [Autocomplete] 자동완성 로직
    # ==========================================

    async def type_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=t, value=t)
            for t in sorted(list(self.cache_categories)) if current in t
        ][:25]

    async def borrow_name_autocomplete(self, interaction: discord.Interaction, current: str):
        # 1. 옵션 파싱 (기존과 동일)
        options = interaction.data.get('options', [])
        focused_option = next((opt for opt in options if opt.get('focused')), None)
        if not focused_option: return []
            
        focused_name = focused_option['name']
        target_type_key = None
        
        if focused_name == "name1": target_type_key = "type1"
        elif focused_name == "name2": target_type_key = "type2"
        elif focused_name == "name3": target_type_key = "type3"
        
        selected_type = next((opt['value'] for opt in options if opt['name'] == target_type_key), None)
        
        # 2. [최적화 핵심] 정렬 없이 앞에서부터 25개 찾으면 바로 리턴
        if selected_type and selected_type in self.cache:
            choices = []
            # self.cache는 이미 이름순으로 정렬되어 있음 (sync_cache 덕분)
            for name, info in self.cache[selected_type].items():
                # 대여 가능한 것만 체크
                if info['borrower_id'] is None:
                    # 검색어가 없거나(전체목록), 검색어가 포함된 경우
                    if not current or current in name:
                        choices.append(app_commands.Choice(name=name, value=name))
                        
                        # [Speed Up] 25개 꽉 차면 더 이상 찾지 말고 끝냄
                        if len(choices) >= 25:
                            break
            
            return choices
        
        return []

    async def return_name_autocomplete(self, interaction: discord.Interaction, current: str):
        user_id = interaction.user.id
        
        # 1. 안전하게 interaction.data에서 옵션 목록 가져오기
        options = interaction.data.get('options', [])
        focused_option = next((opt for opt in options if opt.get('focused')), None)
        if not focused_option: return []
            
        focused_name = focused_option['name']
        target_type_key = None
        
        # 2. 현재 입력 중인 칸(name1, 2, 3)에 맞는 type(1, 2, 3) 찾기
        if focused_name == "name1": target_type_key = "type1"
        elif focused_name == "name2": target_type_key = "type2"
        elif focused_name == "name3": target_type_key = "type3"
        
        selected_type = next((opt['value'] for opt in options if opt['name'] == target_type_key), None)
        
        # 3. 캐시에서 검색 (내가 빌린 것만)
        if selected_type and selected_type in self.cache:
            if selected_type == '전체반납':
                return [] 
            
            choices = []
            # self.cache는 이미 이름순 정렬되어 있음
            for name, info in self.cache[selected_type].items():
                if info['borrower_id'] == user_id:
                    if not current or current in name:
                        choices.append(app_commands.Choice(name=name, value=name))
                        # [Speed Up] 25개 채우면 중단
                        if len(choices) >= 25: break
            
            return choices
        return []

    async def return_type_autocomplete(self, interaction: discord.Interaction, current: str):
        user_id = interaction.user.id
        my_types = set()
        
        for cat, tools in self.cache.items():
            for t_info in tools.values():
                if t_info['borrower_id'] == user_id:
                    my_types.add(cat)
                    break
        
        choices = ['전체반납'] + sorted(list(my_types))
        return [app_commands.Choice(name=c, value=c) for c in choices if current in c][:25]

    # ==========================================
    # [Command 1] 도구 목록
    # ==========================================

    @app_commands.command(name="도구목록", description="특정 종류의 도구 상태를 확인합니다.")
    @app_commands.autocomplete(kind=type_autocomplete)
    async def tool_list(self, interaction: discord.Interaction, kind: str):
        if kind not in self.cache:
            return await interaction.response.send_message("❌ 존재하지 않는 도구 종류입니다.", ephemeral=True)
        
        tools = self.cache[kind]
        
        # 헤더 설정
        col_name, col_stat, col_who, col_time = 20, 10, 16, 12
        header = f"{self.pad_text('이 름', col_name)} | {self.pad_text('상 태', col_stat)} | {self.pad_text('대여자', col_who)} | 대여 시간"
        separator = "-" * (col_name + col_stat + col_who + col_time + 9)
        
        body = ""
        for name in sorted(tools.keys()):
            status = tools[name]
            tool_name = self.pad_text(name, col_name)
            
            if status['borrower_id'] is None:
                body += f"🟢 {tool_name} | {self.pad_text('대여가능', col_stat)} | {self.pad_text('-', col_who)} | -\n"
            else:
                # 닉네임 표시: DB에서 고정 닉네임 확인 -> 없으면 저장된 스냅샷 사용
                # (목록 조회 시마다 DB를 긁으면 느리므로, 캐시값 사용)
                display_nick = status['borrower_nick'] or "Unknown"
                
                # 시간 포맷 (초 단위 제거)
                time_str = status['borrowed_at'][5:-3] if status['borrowed_at'] else "?"
                
                body += f"🔴 {tool_name} | {self.pad_text('대여중', col_stat)} | {self.pad_text(display_nick, col_who)} | {time_str}\n"

        await interaction.response.send_message(f"**[ {kind} 목록 ]**\n```text\n{header}\n{separator}\n{body}```", ephemeral=True)

    # ==========================================
    # [Command 2] 대여
    # ==========================================

    @app_commands.command(name="대여", description="도구를 대여합니다. (최대 3개)")
    @app_commands.describe(
    type1="1번 도구 종류", name1="1번 도구 이름",
    type2="2번 도구 종류", name2="2번 도구 이름",
    type3="3번 도구 종류", name3="3번 도구 이름"
    )
    @app_commands.autocomplete(
        type1=type_autocomplete, name1=borrow_name_autocomplete,
        type2=type_autocomplete, name2=borrow_name_autocomplete,
        type3=type_autocomplete, name3=borrow_name_autocomplete
    )
    async def borrow(self, interaction: discord.Interaction, 
                     type1: str, name1: str, 
                     type2: str = None, name2: str = None, 
                     type3: str = None, name3: str = None):
        
        await interaction.response.defer()
        
        user_id = interaction.user.id
        user_name = interaction.user.name # 고유 ID (태그)
        
        # 1. 고정 닉네임 확인 2. 없으면 디스코드 닉네임
        real_nick = await self.get_real_name(interaction.user)

        # 1. 현재 대여 개수 확인
        current_count = await self.bot.db.get_user_rent_count(user_id)
        
        # 2. 요청 처리
        targets = [{'type': type1, 'name': name1}]
        if type2 and name2: targets.append({'type': type2, 'name': name2})
        if type3 and name3: targets.append({'type': type3, 'name': name3})
        
        if current_count + len(targets) > 3:
            return await interaction.followup.send(f"‼️ 대여 불가: 최대 3개까지만 동시에 대여 가능합니다. (현재: {current_count}개)")

        success_list = []
        fail_list = []
        now = self.bot.db.get_korea_time()

        for item in targets:
            cat, name = item['type'], item['name']
            
            # DB 상태 확인 (동시성 문제 최소화)
            status = await self.bot.db.get_tool_status(cat, name)
            
            if not status:
                fail_list.append(f"{name} (존재하지 않는 도구입니다)")
            elif status[0] is not None: # borrower_id가 있으면 대여중
                fail_list.append(f"{name} (이미 대여중)")
            else:
                # 대여 수행
                await self.bot.db.update_borrow(cat, name, user_id, user_name, real_nick, now)
                success_list.append(name)

        # 3. 캐시 동기화 (성공한 게 하나라도 있다면)
        if success_list:
            await self.sync_cache()
            bot_logger.info(f"[+] [대여] {real_nick}({user_name}): {', '.join(success_list)}")

        # 4. 결과 출력
        msg = "[ 대여 결과 ]\n"
        if success_list:
            msg += f"💚 성공: {', '.join(success_list)}\n"
            msg += f"  (대여자: {real_nick}, 시간: {now})\n"
        if fail_list:
            msg += f"❌ 실패: {', '.join(fail_list)}\n"
            
        await interaction.followup.send(f"```diff\n{msg}```")

    # ==========================================
    # [Command 3] 반납
    # ==========================================

    @app_commands.command(name="반납", description="도구를 반납합니다. (최대 3개)")
    @app_commands.describe(
        type1="1번 도구 종류", name1="1번 도구 이름 (비우면 해당 종류 내 도구 자동 선택)",
        type2="2번 도구 종류", name2="2번 도구 이름",
        type3="3번 도구 종류", name3="3번 도구 이름"
    )
    @app_commands.autocomplete(
        type1=return_type_autocomplete, name1=return_name_autocomplete,
        type2=return_type_autocomplete, name2=return_name_autocomplete,
        type3=return_type_autocomplete, name3=return_name_autocomplete
    )
    async def return_tool(self, interaction: discord.Interaction, 
                          type1: str, name1: str = None,
                          type2: str = None, name2: str = None,
                          type3: str = None, name3: str = None):
        
        await interaction.response.defer()
        
        user_id = interaction.user.id
        targets = []
        inputs = [(type1, name1), (type2, name2), (type3, name3)]
        
        msg_logs = [] # 결과 메시지 저장용

        # 1. 입력값 정리 및 유효성 검사
        for cat, name in inputs:
            if not cat: continue # 입력 없는 칸 패스

            # Case A: 전체 반납
            if cat == '전체반납':
                found_any = False
                for c_key, tools in self.cache.items():
                    for t_name, info in tools.items():
                        if info['borrower_id'] == user_id:
                            targets.append({'type': c_key, 'name': t_name})
                            found_any = True
                if not found_any:
                    msg_logs.append("⚠️ 전체 반납: 빌린 도구가 없습니다.")
                # 전체 반납이 포함되면 뒤에 개별 입력은 무시해도 되지만, 일단 계속 진행
                continue

            # Case B: 개별 반납
            if not name: 
                # 종류는 골랐는데 이름을 안 고름 -> 해당 종류에서 내가 빌린 것 자동 찾기
                my_borrowed = [n for n, i in self.cache.get(cat, {}).items() if i['borrower_id'] == user_id]
                
                if len(my_borrowed) == 1:
                    targets.append({'type': cat, 'name': my_borrowed[0]})
                elif len(my_borrowed) > 1:
                    msg_logs.append(f"⚠️ '{cat}': 여러 개를 빌렸습니다. 이름을 정확히 선택해주세요.")
                else:
                    msg_logs.append(f"⚠️ '{cat}': 빌린 도구가 없습니다.")
            else:
                # 종류와 이름을 다 고름
                targets.append({'type': cat, 'name': name})

        # 2. 반납 실행 (중복 제거)
        # (전체반납과 개별반납이 섞여 있을 때 중복 처리 방지)
        unique_targets = []
        seen = set()
        for t in targets:
            key = (t['type'], t['name'])
            if key not in seen:
                seen.add(key)
                unique_targets.append(t)

        success_list = []
        fail_list = []

        if not unique_targets and not msg_logs:
            return await interaction.followup.send("‼️ 반납할 도구가 없습니다.")

        for item in unique_targets:
            cat, name = item['type'], item['name']
            
            # DB 상태 확인 (더블 체크)
            status = await self.bot.db.get_tool_status(cat, name)
            
            if not status or status[0] != user_id:
                fail_list.append(name) # 내 것이 아니거나 이미 반납됨
            else:
                await self.bot.db.update_borrow(cat, name, None, None, None, None)
                success_list.append(name)

        # 3. 마무리 및 결과 출력
        if success_list:
            await self.sync_cache()
            real_nick = await self.get_real_name(interaction.user)
            bot_logger.info(f"[+] [반납] {real_nick}({interaction.user.name}): {', '.join(success_list)}")
            
            result_msg = f"[ 반납 완료 ]\n✅ 항목: {', '.join(success_list)}\n  (시간: {self.bot.db.get_korea_time()})"
        else:
            result_msg = ""

        # 경고/실패 메시지 합치기
        if fail_list:
            msg_logs.append(f"❌ 반납 실패(본인 아님/이미 반납): {', '.join(fail_list)}")
        
        final_text = ""
        if result_msg: final_text += f"```diff\n{result_msg}```\n"
        if msg_logs: final_text += "\n".join(msg_logs)

        if not final_text.strip():
            final_text = "❌ 처리된 내용이 없습니다."

        await interaction.followup.send(final_text)

    # ==========================================
    # [Command 4] 내 정보
    # ==========================================
    @app_commands.command(name="내정보", description="현재 대여 중인 목록을 확인합니다.")
    async def my_info(self, interaction: discord.Interaction):
        items = await self.bot.db.get_user_borrowed_tools(interaction.user.id)
        real_nick = await self.get_real_name(interaction.user)
        
        if not items:
            return await interaction.response.send_message(f"📜 **{real_nick}**님은 대여 중인 도구가 없습니다.", ephemeral=True)
            
        header = f"{self.pad_text('종류', 8)} | {self.pad_text('이름', 20)} | 대여 시간"
        separator = "-" * 45
        body = ""
        
        for cat, name, time in items:
            time_str = time[5:-3] if time else "?"
            body += f"{self.pad_text(cat, 8)} | {self.pad_text(name, 20)} | {time_str}\n"
            
        await interaction.response.send_message(f"**[ 👤 {real_nick}님의 대여 목록 ]**\n```text\n{header}\n{separator}\n{body}```", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tools(bot))