import discord
from discord import app_commands
from discord.ext import tasks 
import sqlite3
import datetime
import pytz
import os
import glob
import json

# ==========================================
# [1] 설정 및 로깅 시스템 (최적화됨)
# ==========================================

DB_NAME = "tools.db"
LOG_DIR = "logs"

class DailyLogger:
    def __init__(self):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        # 초기 실행 시 한 번은 체크 (봇 켜질 때)
        self.cleanup_old_logs()

    def _get_today_str(self):
        return datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d')

    def write(self, action, user_name, content):
        """로그 파일에 내용만 기록 (IO 최적화)"""
        today = self._get_today_str()
        time_now = datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%H:%M:%S')
        file_path = os.path.join(LOG_DIR, f"{today}.txt")

        log_line = f"[{time_now}] [{action}] {user_name}: {content}\n"
        
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            print(f"[!] 로그 저장 실패: {e}")

    def cleanup_old_logs(self):
        """7일 지난 로그 파일 삭제 (스케줄러에 의해 호출됨)"""
        print("[*] [System] 오래된 로그 정리 시작...")
        today = datetime.datetime.now()
        cutoff = today - datetime.timedelta(days=7)
        
        for file_path in glob.glob(os.path.join(LOG_DIR, "*.txt")):
            filename = os.path.basename(file_path)
            try:
                file_date_str = filename.replace(".txt", "")
                file_date = datetime.datetime.strptime(file_date_str, "%Y-%m-%d")
                
                if file_date < cutoff:
                    os.remove(file_path)
                    print(f"[*] [System] 삭제됨: {filename}")
            except ValueError:
                continue

    def get_log_file(self, date_str):
        file_path = os.path.join(LOG_DIR, f"{date_str}.txt")
        if os.path.exists(file_path):
            return file_path
        return None

logger = DailyLogger()

# ==========================================
# [2] 데이터베이스 (SQLite)
# ==========================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                borrower_id INTEGER,
                borrower_name TEXT,
                borrowed_at TEXT,
                UNIQUE(category, name)
            )
        ''')
        self.conn.commit()

    def add_tool(self, category, name):
        try:
            self.cursor.execute("INSERT INTO tools (category, name) VALUES (?, ?)", (category, name))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_tool(self, category, name):
        self.cursor.execute("DELETE FROM tools WHERE category=? AND name=?", (category, name))
        if self.cursor.rowcount > 0:
            self.conn.commit()
            return True
        return False

    def get_all_tools(self):
        self.cursor.execute("SELECT category, name, borrower_id, borrower_name, borrowed_at FROM tools")
        return self.cursor.fetchall()

    def get_tool_status(self, category, name):
        self.cursor.execute("SELECT borrower_id, borrower_name FROM tools WHERE category=? AND name=?", (category, name))
        return self.cursor.fetchone()
    
    def get_user_rent_count(self, user_id):
        """특정 유저가 현재 대여 중인 아이템 개수 반환"""
        self.cursor.execute("SELECT COUNT(*) FROM tools WHERE borrower_id=?", (user_id,))
        return self.cursor.fetchone()[0]

    def update_borrow(self, category, name, user_id, user_name, time_str):
        self.cursor.execute('''
            UPDATE tools 
            SET borrower_id=?, borrower_name=?, borrowed_at=? 
            WHERE category=? AND name=?
        ''', (user_id, user_name, time_str, category, name))
        self.conn.commit()

db = Database()

# ==========================================
# [3] 캐시 (Autocomplete 최적화)
# ==========================================

class ToolCache:
    def __init__(self):
        self.refresh()

    def refresh(self):
        raw_data = db.get_all_tools()
        self.data = {}
        self.categories = set()
        
        for cat, name, bid, bname, bat in raw_data:
            if cat not in self.data:
                self.data[cat] = {}
            self.categories.add(cat)
            self.data[cat][name] = {
                'borrower': bid,
                'borrower_name': bname,
                'time': bat
            }
    
    def get_categories(self):
        return sorted(list(self.categories))

cache = ToolCache()

# ==========================================
# [4] 봇 클라이언트 설정 (스케줄러 추가됨)
# ==========================================

# 토큰 설정
TOKEN = "YOUR_TOKEN_HERE" 
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        TOKEN = json.load(f)['token']
except:
    pass

class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        # 봇이 켜질 때 백그라운드 태스크 시작
        self.scheduled_cleanup.start()
        print("[*] 명령어 동기화 및 스케줄러 시작 완료")

    async def on_ready(self):
        print(f'[*] {self.user} 로 로그인되었습니다.')

    # 매일 한국 시간 00:00:00에 실행되는 태스크 (오래된 로그 삭제)
    @tasks.loop(time=datetime.time(hour=0, minute=0, second=0, tzinfo=pytz.timezone('Asia/Seoul')))
    async def scheduled_cleanup(self):
        logger.cleanup_old_logs()

client = MyClient()

def get_korea_time():
    return datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')

# ==========================================
# [5] 자동완성 로직
# ==========================================

async def type_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=t, value=t)
        for t in cache.get_categories() if current in t
    ][:25]

# 대여용: 대여 가능한(borrower is None) 도구만 표시
async def borrow_name_autocomplete_logic(interaction: discord.Interaction, current: str, type_field: str):
    selected_type = getattr(interaction.namespace, type_field, None)
    
    if selected_type and selected_type in cache.data:
        filtered = []
        for name, info in cache.data[selected_type].items():
            if info['borrower'] is None:
                if current in name:
                    filtered.append(name)
        return [app_commands.Choice(name=n, value=n) for n in filtered][:25]
    return []

# 반납용: 내가 빌린(borrower == user_id) 도구만 표시
async def return_name_autocomplete_logic(interaction: discord.Interaction, current: str, type_field: str):
    selected_type = getattr(interaction.namespace, type_field, None)
    user_id = interaction.user.id
    
    if selected_type and selected_type != '전체반납' and selected_type in cache.data:
        filtered = []
        for name, info in cache.data[selected_type].items():
            if info['borrower'] == user_id:
                if current in name:
                    filtered.append(name)
        return [app_commands.Choice(name=n, value=n) for n in filtered][:25]
    return []

# [NEW] 관리자용: 대여 여부 상관없이 모든 도구 표시 (삭제 명령어용)
async def admin_name_autocomplete_logic(interaction: discord.Interaction, current: str, type_field: str):
    selected_type = getattr(interaction.namespace, type_field, None)
    if selected_type and selected_type in cache.data:
        filtered = []
        for name in cache.data[selected_type].keys():
            if current in name:
                filtered.append(name)
        return [app_commands.Choice(name=n, value=n) for n in filtered][:25]
    return []

# 로그 조회용 날짜 자동완성 (logs 폴더 파일 기준)
async def log_date_autocomplete(interaction: discord.Interaction, current: str):
    files = glob.glob(os.path.join(LOG_DIR, "*.txt"))
    dates = []
    for f in files:
        name = os.path.basename(f).replace(".txt", "")
        dates.append(name)
    dates.sort(reverse=True)
    return [app_commands.Choice(name=d, value=d) for d in dates if current in d][:25]


# ==========================================
# [6] 명령어
# ==========================================

@client.tree.command(name="도구목록", description="특정 종류의 도구 상태를 확인합니다.")
@app_commands.autocomplete(kind=type_autocomplete)
async def tool_list(interaction: discord.Interaction, kind: str):
    cache.refresh()
    if kind not in cache.data:
        return await interaction.response.send_message("❌ 존재하지 않는 도구 종류입니다.", ephemeral=True)
    
    message = f"**[ {kind} 목록 ]**\n"
    tools = cache.data[kind]
    for name in sorted(tools.keys()):
        status = tools[name]
        if status['borrower'] is None:
            message += f"🟢 **{name}** : 대여 가능\n"
        else:
            message += f"🔴 **{name}** : {status['borrower_name']}님 대여 중\n"
    await interaction.response.send_message(message, ephemeral=True)


@client.tree.command(name="대여", description="도구를 대여합니다. (1인당 최대 3개 보유 가능)")
@app_commands.describe(
    type1="1번 도구 종류", name1="1번 도구 이름",
    type2="2번 도구 종류", name2="2번 도구 이름",
    type3="3번 도구 종류", name3="3번 도구 이름"
)
@app_commands.autocomplete(
    type1=type_autocomplete, type2=type_autocomplete, type3=type_autocomplete
)
async def borrow(interaction: discord.Interaction, 
                 type1: str, name1: str, 
                 type2: str = None, name2: str = None,
                 type3: str = None, name3: str = None):
    
    await interaction.response.defer()
    
    user_id = interaction.user.id
    user_name = interaction.user.name
    
    # [제한 로직] 1. 현재 빌린 개수 확인
    current_rent_count = db.get_user_rent_count(user_id)
    if current_rent_count >= 3:
        return await interaction.followup.send(
            f"🚫 **대여 불가**: 이미 3개를 대여 중입니다.\n반납 후 다시 시도해주세요."
        )

    # [제한 로직] 2. 이번 요청 개수 계산
    targets = [{'type': type1, 'name': name1}]
    if type2 and name2: targets.append({'type': type2, 'name': name2})
    if type3 and name3: targets.append({'type': type3, 'name': name3})
    
    request_count = len(targets)
    
    if current_rent_count + request_count > 3:
        return await interaction.followup.send(
            f"🚫 **대여 불가**: 최대 3개까지만 보유할 수 있습니다.\n"
            f"(현재: {current_rent_count}개 / 요청: {request_count}개 / 초과: {current_rent_count + request_count - 3}개)"
        )

    success_list = []
    fail_list = []
    now = get_korea_time()

    for item in targets:
        cat, name = item['type'], item['name']
        current_status = db.get_tool_status(cat, name)
        
        if not current_status:
            fail_list.append(f"{name} (존재하지 않음)")
        elif current_status[0] is not None:
            fail_list.append(f"{name} (이미 대여중)")
        else:
            db.update_borrow(cat, name, user_id, user_name, now)
            success_list.append(name)

    cache.refresh()

    reply = "[ 대여 결과 ]\n"
    if success_list:
        reply += f"+ 성공: {', '.join(success_list)}\n"
        logger.write("대여", user_name, f"{', '.join(success_list)}")
    if fail_list:
        reply += f"- 실패: {', '.join(fail_list)}\n"
    
    await interaction.followup.send(f"```diff\n{reply}```")

# 대여 자동완성 연결
@borrow.autocomplete("name1")
async def b_n1(i, c): return await borrow_name_autocomplete_logic(i, c, "type1")
@borrow.autocomplete("name2")
async def b_n2(i, c): return await borrow_name_autocomplete_logic(i, c, "type2")
@borrow.autocomplete("name3")
async def b_n3(i, c): return await borrow_name_autocomplete_logic(i, c, "type3")


@client.tree.command(name="반납", description="도구를 반납합니다.")
@app_commands.describe(type1="종류 또는 전체반납", name1="이름")
@app_commands.autocomplete(type1=type_autocomplete)
async def return_tool(interaction: discord.Interaction, type1: str, name1: str = None):
    await interaction.response.defer()
    
    user_id = interaction.user.id
    success_list = []
    fail_list = []
    targets = []

    if type1 == '전체반납':
        cache.refresh()
        for cat, tools in cache.data.items():
            for name, info in tools.items():
                if info['borrower'] == user_id:
                    targets.append({'type': cat, 'name': name})
    else:
        if not name1:
            cache.refresh()
            my_borrowed = [n for n, info in cache.data.get(type1, {}).items() if info['borrower'] == user_id]
            
            if len(my_borrowed) == 1:
                targets.append({'type': type1, 'name': my_borrowed[0]})
            elif len(my_borrowed) > 1:
                return await interaction.followup.send("❌ 해당 종류로 빌린 도구가 여러 개입니다. 이름을 입력해주세요.")
            else:
                return await interaction.followup.send("❌ 해당 종류로 빌린 내역이 없습니다.")
        else:
            targets.append({'type': type1, 'name': name1})

    for item in targets:
        cat, name = item['type'], item['name']
        status = db.get_tool_status(cat, name)
        
        if not status:
            fail_list.append(f"{name} (오류)")
        elif status[0] != user_id:
            fail_list.append(f"{name} (본인이 빌리지 않음)")
        else:
            db.update_borrow(cat, name, None, None, None)
            success_list.append(name)
    
    cache.refresh()

    reply = f"[ 반납 결과 ]\n+ 완료: {', '.join(success_list)}" if success_list else "반납 실패"
    await interaction.followup.send(f"```diff\n{reply}```")

    if success_list:
        logger.write("반납", interaction.user.name, f"{', '.join(success_list)}")

# 반납 자동완성 재연결
async def return_type_ac_wrapper(interaction: discord.Interaction, current: str):
    user_id = interaction.user.id
    my_types = set()
    for cat, tools in cache.data.items():
        for t_info in tools.values():
            if t_info['borrower'] == user_id:
                my_types.add(cat)
                break 
    choices = ['전체반납'] + list(my_types)
    return [app_commands.Choice(name=c, value=c) for c in choices if current in c][:25]

@return_tool.autocomplete("type1")
async def rt_ac(i, c): return await return_type_ac_wrapper(i, c)
@return_tool.autocomplete("name1")
async def rn_ac(i, c): return await return_name_autocomplete_logic(i, c, "type1")


# ==========================================
# [7] 로그 조회 및 관리자 명령어
# ==========================================

@client.tree.command(name="로그조회", description="[관리자] 특정 날짜의 대여/반납 로그를 파일로 다운로드합니다.")
@app_commands.default_permissions(administrator=True)
@app_commands.autocomplete(date=log_date_autocomplete)
async def get_log(interaction: discord.Interaction, date: str):
    fp = logger.get_log_file(date)
    if fp: 
        await interaction.response.send_message(f"📂 {date} 로그", file=discord.File(fp), ephemeral=True)
    else: 
        await interaction.response.send_message("❌ 해당 날짜의 로그 파일이 존재하지 않습니다.", ephemeral=True)

@client.tree.command(name="도구관리_추가")
@app_commands.default_permissions(administrator=True)
async def ad_add(interaction: discord.Interaction, category: str, name: str):
    if db.add_tool(category, name): 
        cache.refresh()
        await interaction.response.send_message(f"✅ 추가 완료: {category} - {name}", ephemeral=True)
    else: 
        await interaction.response.send_message("❌ 실패 (이미 존재함)", ephemeral=True)

@client.tree.command(name="도구관리_삭제")
@app_commands.autocomplete(category=type_autocomplete)
async def ad_del(interaction: discord.Interaction, category: str, name: str):
    if db.remove_tool(category, name): 
        cache.refresh()
        await interaction.response.send_message(f"🗑️ 삭제 완료: {name}", ephemeral=True)
    else: 
        await interaction.response.send_message("❌ 실패 (존재하지 않음)", ephemeral=True)

# [수정됨] 삭제 시에는 '대여 중'인 도구도 보여야 하므로 admin_name_autocomplete_logic 사용
@ad_del.autocomplete("name")
async def ad_n(i, c): return await admin_name_autocomplete_logic(i, c, "category")

client.run(TOKEN)