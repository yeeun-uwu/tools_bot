import discord
from discord import app_commands
from discord.ext import tasks 
import sqlite3
import datetime
import pytz
import os
import glob
import json
import unicodedata

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
        cutoff = today - datetime.timedelta(days=6) # 오늘 포함 7일치 유지
        
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
                borrower_nick TEXT,  -- 닉네임 컬럼
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

    # 모든 도구 조회
    def get_all_tools(self):
        self.cursor.execute("""
            SELECT category, name, borrower_id, borrower_name, borrower_nick, borrowed_at 
            FROM tools 
            ORDER BY category ASC, name ASC
        """)
        return self.cursor.fetchall()
    
    # 대여 중인 도구 조회
    def get_all_rented_tools(self):
        """대여 중인 모든 도구 조회 (관리자용)"""
        self.cursor.execute("""
            SELECT category, name, borrower_name, borrower_nick, borrowed_at 
            FROM tools 
            WHERE borrower_id IS NOT NULL
            ORDER BY borrowed_at ASC
        """)
        return self.cursor.fetchall()

    # 특정 도구 상태 조회
    def get_tool_status(self, category, name):
        self.cursor.execute("""
            SELECT borrower_id, borrower_name, borrower_nick, borrowed_at 
            FROM tools 
            WHERE category=? AND name=?
        """, (category, name))
        return self.cursor.fetchone()
    
    def get_user_rent_count(self, user_id):
        """특정 유저가 현재 대여 중인 아이템 개수 반환"""
        self.cursor.execute("SELECT COUNT(*) FROM tools WHERE borrower_id=?", (user_id,))
        return self.cursor.fetchone()[0]
    
    def get_user_borrowed_tools(self, user_id):
        """특정 유저가 대여 중인 도구 목록 반환"""
        self.cursor.execute("""
            SELECT category, name, borrowed_at 
            FROM tools 
            WHERE borrower_id=?
            ORDER BY borrowed_at ASC
        """, (user_id,))
        return self.cursor.fetchall()

    # 대여 정보 업데이트
    def update_borrow(self, category, name, user_id, user_name, user_nick, time_str):
        self.cursor.execute('''
            UPDATE tools 
            SET borrower_id=?, borrower_name=?, borrower_nick=?, borrowed_at=? 
            WHERE category=? AND name=?
        ''', (user_id, user_name, user_nick, time_str, category, name))
        self.conn.commit()

db = Database()

# ==========================================
# [3] 캐시 (Autocomplete 최적화)
# ==========================================

class ToolCache:
    def __init__(self):
        self.data = {}
        self.categories = set()

    def refresh(self):
        """DB에서 전체 데이터를 불러와 캐시를 초기화"""
        print("[System] 캐시 전체 동기화 중...")
        # get_all_tools가 이제 6개 값을 반환함 (nick 추가됨)
        raw_data = db.get_all_tools()
        self.data = {}
        self.categories = set()
        
        for cat, name, bid, bname, bnick, bat in raw_data:
            if cat not in self.data:
                self.data[cat] = {}
            self.categories.add(cat)
            self.data[cat][name] = {
                'borrower': bid,
                'borrower_name': bname, # 아이디
                'borrower_nick': bnick, # [NEW] 닉네임
                'time': bat
            }
        print("[System] 캐시 동기화 완료.")
    
    def get_categories(self):
        return sorted(list(self.categories))
    
    # 대여/반납 시 해당 아이템만 캐시 수정
    def update_tool(self, category, name, borrower_id, borrower_name, borrower_nick, time_str):
        if category in self.data and name in self.data[category]:
            self.data[category][name] = {
                'borrower': borrower_id,
                'borrower_name': borrower_name,
                'borrower_nick': borrower_nick, # [NEW]
                'time': time_str
            }

    # 도구 추가 시 캐시에 즉시 반영
    def add_tool_local(self, category, name):
        if category not in self.data:
            self.data[category] = {}
            self.categories.add(category)
        
        self.data[category][name] = {
            'borrower': None,
            'borrower_name': None,
            'borrower_nick': None,
            'time': None
        }

    # 도구 삭제 시 캐시에서 즉시 제거
    def remove_tool_local(self, category, name):
        if category in self.data and name in self.data[category]:
            del self.data[category][name]
            # 카테고리가 비어있으면 제거
            if not self.data[category]:
                del self.data[category]
                self.categories.discard(category)

cache = ToolCache()

# ==========================================
# [4] 봇 클라이언트 설정 (스케줄러 추가됨)
# ==========================================

# 토큰 설정
TOKEN = "PUT_YOUR_TOKEN_ON_CONFIG_FILE" 
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
        
        # [중요] 봇 시작 시 1회 전체 로드
        cache.refresh() 
        
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
        filtered.sort()
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
        filtered.sort()
        return [app_commands.Choice(name=n, value=n) for n in filtered][:25]
    return []

# 3. 강제반납용: 대여 중인(borrower is not None) 도구만 표시 (관리자용)
async def borrowed_only_autocomplete(interaction: discord.Interaction, current: str, type_field: str):
    selected_type = getattr(interaction.namespace, type_field, None)
    
    if selected_type and selected_type in cache.data:
        filtered = []
        for name, info in cache.data[selected_type].items():
            if info['borrower'] is not None: # 누가 빌려간 것만 표시
                if current in name:
                    filtered.append(name)
        filtered.sort()
        return [app_commands.Choice(name=n, value=n) for n in filtered][:25]
    return []

# 관리자용: 대여 여부 상관없이 모든 도구 표시 (삭제 명령어용)
async def admin_name_autocomplete_logic(interaction: discord.Interaction, current: str, type_field: str):
    selected_type = getattr(interaction.namespace, type_field, None)
    if selected_type and selected_type in cache.data:
        filtered = []
        for name in cache.data[selected_type].keys():
            if current in name:
                filtered.append(name)
        filtered.sort()
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

# 한글/영어 너비 계산
def get_width(text):
    width = 0
    for char in text:
        # 한글(East Asian Wide)이나 특수문자는 2칸, 나머지는 1칸
        if unicodedata.east_asian_width(char) in ['W', 'F', 'A']:
            width += 2
        else:
            width += 1
    return width

# 너비에 맞춰 공백 채우기
def pad_text(text, target_width):
    current_width = get_width(text)
    
    # 글자가 목표보다 길면 자르기 (.. 붙임)
    if current_width > target_width:
        temp = ""
        curr = 0
        for char in text:
            w = 2 if unicodedata.east_asian_width(char) in ['W', 'F', 'A'] else 1
            if curr + w > target_width - 2: break # .. 공간 확보
            temp += char
            curr += w
        return temp + ".." + " " * (target_width - (curr + 2))
    
    # 글자가 짧으면 공백 채우기
    else:
        return text + " " * (target_width - current_width)
    
# ==========================================
# (1) 도구 목록
# ==========================================

@client.tree.command(name="도구목록", description="특정 종류의 도구 상태와 대여 정보를 표 형식으로 확인합니다.")
@app_commands.autocomplete(kind=type_autocomplete)
async def tool_list(interaction: discord.Interaction, kind: str):
    if kind not in cache.data:
        return await interaction.response.send_message("❌ 존재하지 않는 도구 종류입니다.", ephemeral=True)
    
    tools = cache.data[kind]
    
    # [헤더 설정] 너비 설정
    col_name = 20
    col_stat = 10
    col_who = 16
    col_time = 12

    name_head = pad_text('이 름', col_name)
    stat_head = pad_text('상 태', col_stat)
    who_head  = pad_text('대여자', col_who)
    
    header = f"{name_head} | {stat_head} | {who_head} | 대여 시간"
    separator = "-" * (col_name + col_stat + col_who + col_time + 9)
    
    body = ""
    for name in sorted(tools.keys()):
        status = tools[name]
        
        # 1. 도구 이름
        tool_name = pad_text(name, col_name)
        
        if status['borrower'] is None:
            emoji = "🟢"
            state = pad_text("대여가능", col_stat)
            borrower = pad_text("-", col_who)
            time_str = "-"
        else:
            emoji = "🔴"
            state = pad_text("대여중", col_stat)
            
            # 2. 대여자 (닉네임(아이디))
            nick = status.get('borrower_nick')
            u_name = status.get('borrower_name') or "Unknown"
            
            if nick:
                full_name = f"{nick}({u_name})"
            else:
                full_name = u_name
                
            borrower = pad_text(full_name, col_who)
            
            # 3. 시간
            if status['time']:
                time_str = status['time'][5:-3] 
            else:
                time_str = "?"

        body += f"{emoji} {tool_name} | {state} | {borrower} | {time_str}\n"

    message = f"**[ {kind} 목록 ]**\n```text\n{header}\n{separator}\n{body}```"
    await interaction.response.send_message(message, ephemeral=True)

# ==========================================
# (2) 대여
# ==========================================

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
    user_name = interaction.user.name         # 고유 아이디 (로그 저장용)
    user_nick = interaction.user.display_name # 서버 별명 (표시용)
    
    # 1. 현재 빌린 개수 확인
    current_rent_count = db.get_user_rent_count(user_id)
    if current_rent_count >= 3:
        return await interaction.followup.send(
            f"🚫 **대여 불가**: 이미 3개를 대여 중입니다.\n반납 후 다시 시도해주세요."
        )

    # 2. 이번 요청 개수 계산
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

            db.update_borrow(cat, name, user_id, user_name, user_nick, now)
            cache.update_tool(cat, name, user_id, user_name, user_nick, now)
            
            success_list.append(name)

    reply = "[ 대여 결과 ]\n"
    if success_list:
        reply += f"+ 성공: {', '.join(success_list)}\n"
        # [수정됨] 대여 시간 표시 추가 (줄바꿈 후 들여쓰기)
        reply += f"  (대여자: {user_nick}, 시간: {now})\n"

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

# ==========================================
# (3) 반납
# ==========================================

@client.tree.command(name="반납", description="도구를 반납합니다.")
@app_commands.describe(type1="종류 또는 전체반납", name1="이름")
@app_commands.autocomplete(type1=type_autocomplete)
async def return_tool(interaction: discord.Interaction, type1: str, name1: str = None):
    await interaction.response.defer()
    
    user_id = interaction.user.id
    success_list = []
    fail_list = []
    targets = []

    # 1. 전체 반납 로직
    if type1 == '전체반납':
        # cache.refresh() 제거 -> 메모리 캐시 바로 조회
        for cat, tools in cache.data.items():
            for name, info in tools.items():
                if info['borrower'] == user_id:
                    targets.append({'type': cat, 'name': name})
    
    # 2. 개별 반납 로직
    else:
        if not name1:
            # cache.data.get(type1, {}) 처리로 안전하게 접근
            my_borrowed = [n for n, info in cache.data.get(type1, {}).items() if info['borrower'] == user_id]
            
            if len(my_borrowed) == 1:
                targets.append({'type': type1, 'name': my_borrowed[0]})
            elif len(my_borrowed) > 1:
                return await interaction.followup.send("❌ 해당 종류로 빌린 도구가 여러 개입니다. 이름을 입력해주세요.")
            else:
                return await interaction.followup.send("❌ 해당 종류로 빌린 내역이 없습니다.")
        else:
            targets.append({'type': type1, 'name': name1})

    # 3. 반납 처리 루프
    for item in targets:
        cat, name = item['type'], item['name']
        status = db.get_tool_status(cat, name)
        
        if not status:
            fail_list.append(f"{name}은 존재하지 않는 도구입니다.")
        # status[0]은 borrower_id
        elif status[0] != user_id:
            fail_list.append(f"{name}은 본인이 빌린 도구가 아닙니다.")
        else:
            # 인자 개수 맞추기 (None 4개 전달: id, name, nick, time)
            db.update_borrow(cat, name, None, None, None, None)
            cache.update_tool(cat, name, None, None, None, None)
            
            success_list.append(name)

    now = get_korea_time()
    
    # 4. 결과 전송
    reply = f"[ 반납 결과 ]\n+ 완료: {', '.join(success_list)}" if success_list else "반납 실패"
    reply += f"  (시간: {now})\n"
    
    if fail_list:
        reply += f"\n- 실패: {', '.join(fail_list)}"

    await interaction.followup.send(f"```diff\n{reply}```")

    if success_list:
        # 로그는 고유 아이디(interaction.user.name)로 남김
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
# (4) 본인 대여도구 조회
# ==========================================

@client.tree.command(name="내정보", description="현재 내가 대여 중인 도구 목록을 표 형식으로 확인합니다.")
async def my_info(interaction: discord.Interaction):
    # DB에서 내 대여 목록 조회 (category, name, time 반환)
    items = db.get_user_borrowed_tools(interaction.user.id)
    
    if not items:
        return await interaction.response.send_message("📜 현재 대여 중인 도구가 없습니다.", ephemeral=True)
    
    # 2. 헤더 생성
    # 종류(8칸) | 이름(20칸) | 대여 시간
    header = f"{pad_text('종류', 8)} | {pad_text('이름', 20)} | 대여 시간"
    separator = "-" * 45
    
    body = ""
    for category, name, time in items:
        # 3. 데이터 가공
        cat_str = pad_text(category, 8)
        name_str = pad_text(name, 20)
        
        # 시간 포맷 단축 (YYYY-MM-DD HH:MM:SS -> MM-DD HH:MM)
        if time:
            time_str = time[5:-3]
        else:
            time_str = "?"
            
        body += f"{cat_str} | {name_str} | {time_str}\n"
    
    # 4. 결과 전송
    msg = f"**[ 👤 {interaction.user.display_name}님의 대여 목록 ]**\n```text\n{header}\n{separator}\n{body}```"
    
    await interaction.response.send_message(msg, ephemeral=True)


# ==========================================
# [7] 로그 조회 및 관리자 명령어
# ==========================================

# ==========================================
# (1) 로그 조회
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

# ==========================================
# (2) 도구 관리
# ==========================================

@client.tree.command(name="도구관리_추가", description="[관리자] 새로운 도구를 목록에 추가합니다.")
@app_commands.describe(category="도구 종류", name="도구 이름")
@app_commands.default_permissions(administrator=True)
async def ad_add(interaction: discord.Interaction, category: str, name: str):
    if db.add_tool(category, name): 
        # 1. 캐시 즉시 반영 (최적화)
        cache.add_tool_local(category, name)
        
        # 2. [LOG] 로그 파일에 기록
        logger.write("도구추가", interaction.user.name, f"{category} - {name}")
        
        await interaction.response.send_message(f"✅ **[{category}] {name}** 추가 완료!", ephemeral=True)
    else: 
        await interaction.response.send_message("❌ 실패 (이미 존재하는 도구입니다)", ephemeral=True)

@client.tree.command(name="도구관리_삭제", description="[관리자] 기존 도구를 목록에서 삭제합니다.")
@app_commands.describe(category="도구 종류", name="도구 이름")
@app_commands.default_permissions(administrator=True)
@app_commands.autocomplete(category=type_autocomplete)
async def ad_del(interaction: discord.Interaction, category: str, name: str):
    if db.remove_tool(category, name): 
        # 1. 캐시 즉시 제거 (최적화)
        cache.remove_tool_local(category, name)
        
        # 2. [LOG] 로그 파일에 기록
        logger.write("도구삭제", interaction.user.name, f"{category} - {name}")
        
        await interaction.response.send_message(f"🗑️ **[{category}] {name}** 삭제 완료!", ephemeral=True)
    else: 
        await interaction.response.send_message("❌ 실패 (존재하지 않는 도구입니다)", ephemeral=True)

# 삭제 명령어용 자동완성 (모든 도구 표시)
@ad_del.autocomplete("name")
async def ad_n(i, c): return await admin_name_autocomplete_logic(i, c, "category")

# ==========================================
# (3) 특정 사용자 대여 도구 조회
# ==========================================

@client.tree.command(name="유저대여조회", description="[관리자] 특정 유저가 대여 중인 도구를 조회합니다.")
@app_commands.describe(user="조회할 유저 (닉네임 검색 가능)")
@app_commands.default_permissions(administrator=True)
async def admin_user_info(interaction: discord.Interaction, user: discord.User):
    
    items = db.get_user_borrowed_tools(user.id)
    
    if not items:
        return await interaction.response.send_message(f"📜 **{user.display_name}**님은 대여 중인 도구가 없습니다.", ephemeral=True)
    
    # 3. 표 생성 (내정보 명령어와 동일한 포맷)
    # 종류(8칸) | 이름(20칸) | 대여 시간
    header = f"{pad_text('종류', 8)} | {pad_text('이름', 20)} | 대여 시간"
    separator = "-" * 45
    
    body = ""
    for category, name, time in items:
        cat_str = pad_text(category, 8)
        name_str = pad_text(name, 20)
        
        # 시간 포맷 (MM-DD HH:MM)
        if time:
            time_str = time[5:-3]
        else:
            time_str = "?"
            
        body += f"{cat_str} | {name_str} | {time_str}\n"
    
    # 4. 결과 전송
    msg = f"**[ 🔍 {user.display_name}님의 대여 현황 ]**\n```text\n{header}\n{separator}\n{body}```"
    await interaction.response.send_message(msg, ephemeral=True)

# ==========================================
# (4) 전체 대여 도구 조회
# ==========================================

@client.tree.command(name="전체대여현황", description="[관리자] 현재 대여 중인 도구 목록만 모아서 파일로 확인합니다.")
@app_commands.default_permissions(administrator=True)
async def all_rent_status(interaction: discord.Interaction):
    # 1. 대여 중인 도구만 조회
    items = db.get_all_rented_tools() # (cat, name, b_name, b_nick, time)
    
    if not items:
        return await interaction.response.send_message("👀 현재 대여 중인 도구가 하나도 없습니다!", ephemeral=True)
    
    # 2. 파일 내용 작성
    lines = []
    now_str = get_korea_time()
    
    lines.append(f"[ 전체 대여 현황 Report ]")
    lines.append(f"기준 시간: {now_str}")
    lines.append(f"대여 건수: {len(items)}건")
    lines.append("")
    
    # 헤더 설정
    col_cat, col_name, col_who = 10, 24, 24
    
    header = f"{pad_text('종류', col_cat)} | {pad_text('이름', col_name)} | {pad_text('대여자', col_who)} | 대여 시간"
    separator = "-" * 85
    
    lines.append(header)
    lines.append(separator)
    
    for category, name, b_name, b_nick, time in items:
        # 데이터 가공
        cat_str = pad_text(category, col_cat)
        name_str = pad_text(name, col_name)
        
        # 닉네임(아이디)
        full_name = f"{b_nick}({b_name})" if b_nick else b_name
        who_str = pad_text(full_name, col_who)
        
        time_str = time if time else "?"
        
        lines.append(f"{cat_str} | {name_str} | {who_str} | {time_str}")
        
    # 3. 파일 생성 및 전송
    filename = f"rented_status_{now_str[:10]}.txt"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        await interaction.response.send_message("📂 **전체 대여 현황**입니다.", file=discord.File(filename), ephemeral=True)
    finally:
        if os.path.exists(filename): os.remove(filename)

# ==========================================
# (5) 전체 도구 현황
# ==========================================

@client.tree.command(name="전체도구현황", description="[관리자] 대여 여부와 상관없이 등록된 모든 도구 목록을 파일로 확인합니다.")
@app_commands.default_permissions(administrator=True)
async def all_tool_status(interaction: discord.Interaction):
    # 1. 모든 도구 조회
    # (cat, name, b_id, b_name, b_nick, time)
    items = db.get_all_tools()
    
    if not items:
        return await interaction.response.send_message("❌ 등록된 도구가 없습니다.", ephemeral=True)
    
    # 2. 파일 내용 작성
    lines = []
    now_str = get_korea_time()
    
    lines.append(f"[ 전체 도구 목록 Report ]")
    lines.append(f"기준 시간: {now_str}")
    lines.append(f"총 도구 수: {len(items)}개")
    lines.append("")
    
    # 헤더 설정 (상태 칸 추가)
    col_cat, col_name, col_stat, col_who = 10, 24, 10, 24
    
    header = f"{pad_text('종류', col_cat)} | {pad_text('이름', col_name)} | {pad_text('상태', col_stat)} | {pad_text('대여자', col_who)} | 대여 시간"
    separator = "-" * 95
    
    lines.append(header)
    lines.append(separator)
    
    for category, name, b_id, b_name, b_nick, time in items:
        cat_str = pad_text(category, col_cat)
        name_str = pad_text(name, col_name)
        
        if b_id is None:
            # 대여 가능한 상태
            stat_str = pad_text("대여가능", col_stat)
            who_str = pad_text("-", col_who)
            time_str = "-"
        else:
            # 대여 중인 상태
            stat_str = pad_text("대여중", col_stat)
            full_name = f"{b_nick}({b_name})" if b_nick else b_name
            who_str = pad_text(full_name, col_who)
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

# ==========================================
# (6) 강제 반납
# ==========================================

@client.tree.command(name="강제반납", description="[관리자] 대여 중인 도구를 강제로 반납 처리합니다.")
@app_commands.describe(category="도구 종류", name="도구 이름")
@app_commands.default_permissions(administrator=True)
@app_commands.autocomplete(category=type_autocomplete)
async def force_return(interaction: discord.Interaction, category: str, name: str):
    # [수정 1] 모두가 볼 수 있도록 defer() 호출 (ephemeral 제거)
    await interaction.response.defer()
    
    # 1. 현재 상태 확인
    status = db.get_tool_status(category, name)
    
    if not status:
        return await interaction.followup.send("❌ 존재하지 않는 도구입니다.")
    
    # status: (id, user_name, user_nick, rent_time)
    b_id = status[0]
    b_name = status[1] # 아이디
    b_nick = status[2] # 닉네임
    rent_time = status[3] # 대여 시간
    
    if b_id is None:
        return await interaction.followup.send(f"👀 **[{category}] {name}**은(는) 이미 반납된 상태입니다.")

    # 2. 강제 반납 처리 (DB & 캐시)
    db.update_borrow(category, name, None, None, None, None)
    cache.update_tool(category, name, None, None, None, None)
    
    # 3. 시간 정보 가공
    now = get_korea_time()
    
    # 시간 포맷 단축 (MM-DD HH:MM)
    rent_str = rent_time[5:-3] if rent_time else "?"
    return_str = now[5:-3]

    # 닉네임(아이디)
    prev_user = f"{b_nick}({b_name})" if b_nick else b_name

    # 4. 로그 기록
    logger.write("강제반납", interaction.user.name, f"{category} - {name} (대상: {prev_user})")
    
    # 5. [수정 2] 결과 메시지 구성 (대여/반납 시간 표시)
    message = (
        f"[ 🚨 강제 반납 실행 ]\n"
        f"- 도구: [{category}] {name}\n"
        f"- 대상: {prev_user}\n"
        f"# 대여: {rent_str}\n"
        f"# 반납: {return_str} (관리자 처리)"
    )
    
    await interaction.followup.send(f"```diff\n{message}```")

# 이름 자동완성 연결 (대여 중인 것만 표시)
@force_return.autocomplete("name")
async def fr_name_ac(i, c): return await borrowed_only_autocomplete(i, c, "category")

# ==========================================
# [8] 봇 실행
# ==========================================

client.run(TOKEN)