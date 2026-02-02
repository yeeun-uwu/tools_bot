import aiosqlite
import os
import datetime
import pytz

# 데이터 저장 경로 설정
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "tools.db")

class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """data 폴더가 없으면 생성"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    async def initialize(self):
        """DB 연결 및 테이블 초기화 (봇 시작 시 호출)"""
        async with aiosqlite.connect(self.db_path) as db:
            # 1. 도구 테이블
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    borrower_id INTEGER,
                    borrower_name TEXT,
                    borrower_nick TEXT,
                    borrowed_at TEXT,
                    UNIQUE(category, name)
                )
            ''')
            
            # 2. 유저 정보 테이블 (고정 닉네임용) 
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, -- Discord ID
                    custom_nickname TEXT,        -- 사용자가 설정한 고정 닉네임
                    created_at TEXT
                )
            ''')

            # 3. 잠광 설정 테이블 (설정값 1개 row만 유지)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS mining_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1), -- 오직 1개의 설정만 존재하도록 강제함 설정하면 id 1이 생김 
                    channel_id INTEGER,
                    role_id INTEGER,
                    last_cleared_at TEXT, -- 마지막 비움 시간
                    dashboard_msg_id INTEGER
                )
            ''')

            # 4. 잠광 진행중 유저 테이블
            await db.execute('''
                CREATE TABLE IF NOT EXISTS mining_users (
                    user_id INTEGER PRIMARY KEY,
                    start_time TEXT
                )
            ''')

            #
            
            await db.commit()
            print("[DB] 데이터베이스 및 테이블 초기화 완료")
            
            # 스키마 마이그레이션 (필요시 컬럼 추가 로직)
            await self._migrate_schema(db)

    async def _migrate_schema(self, db):
        """기존 DB에 새 컬럼이 없을 경우 자동 추가"""
        # 예: tools 테이블에 borrower_nick 컬럼 확인
        async with db.execute("PRAGMA table_info(tools)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
            
        if 'borrower_nick' not in columns:
            print("[DB] 'borrower_nick' 컬럼 추가 중...")
            await db.execute("ALTER TABLE tools ADD COLUMN borrower_nick TEXT")
            await db.commit()

    # ==========================
    # [1] 공통 유틸리티
    # ==========================
    
    def get_korea_time(self):
        return datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')

    # ==========================
    # [2] 도구 관련 쿼리
    # ==========================

    async def get_all_tools(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT category, name, borrower_id, borrower_name, borrower_nick, borrowed_at FROM tools ORDER BY category, name") as cursor:
                return await cursor.fetchall()

    async def get_tool_status(self, category, name):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT borrower_id, borrower_name, borrower_nick, borrowed_at FROM tools WHERE category=? AND name=?", (category, name)) as cursor:
                return await cursor.fetchone()

    async def update_borrow(self, category, name, user_id, user_name, user_nick, time_str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE tools 
                SET borrower_id=?, borrower_name=?, borrower_nick=?, borrowed_at=? 
                WHERE category=? AND name=?
            ''', (user_id, user_name, user_nick, time_str, category, name))
            await db.commit()
            
    async def get_user_rent_count(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM tools WHERE borrower_id=?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def get_user_borrowed_tools(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT category, name, borrowed_at FROM tools WHERE borrower_id=?", (user_id,)) as cursor:
                return await cursor.fetchall()
            
    async def add_tool(self, category, name):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("INSERT INTO tools (category, name) VALUES (?, ?)", (category, name))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_tool(self, category, name):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM tools WHERE category=? AND name=?", (category, name))
            await db.commit()
            return True

    # ==========================
    # [3] 유저(닉네임) 관련 쿼리
    # ==========================

    async def get_user_nickname(self, user_id):
        """등록된 닉네임이 있으면 반환, 없으면 None"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT custom_nickname FROM users WHERE user_id=?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None

    async def set_user_nickname(self, user_id, nickname):
        now = self.get_korea_time()
        async with aiosqlite.connect(self.db_path) as db:
            # Upsert (있으면 업데이트, 없으면 삽입)
            await db.execute('''
                INSERT INTO users (user_id, custom_nickname, created_at) 
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET custom_nickname=excluded.custom_nickname
            ''', (user_id, nickname, now))
            await db.commit()

    # ==========================
    # [4] 잠광(Mining) 관련 쿼리
    # ==========================
    
    async def get_mining_config(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT channel_id, role_id, last_cleared_at, dashboard_msg_id FROM mining_config WHERE id=1") as cursor:
                return await cursor.fetchone()

    async def set_mining_config(self, channel_id, role_id):
        async with aiosqlite.connect(self.db_path) as db:
            # 초기 설정이 없으면 생성, 있으면 업데이트
            await db.execute('''
                INSERT INTO mining_config (id, channel_id, role_id) VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET channel_id=excluded.channel_id, role_id=excluded.role_id
            ''', (channel_id, role_id))
            await db.commit()

    async def update_mining_last_cleared(self, time_str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE mining_config SET last_cleared_at=? WHERE id=1", (time_str,))
            await db.commit()
            
    async def update_mining_dashboard_id(self, msg_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE mining_config SET dashboard_msg_id=? WHERE id=1", (msg_id,))
            await db.commit()

    async def add_mining_user(self, user_id):
        now = self.get_korea_time()
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("INSERT INTO mining_users (user_id, start_time) VALUES (?, ?)", (user_id, now))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False # 이미 진행중

    async def remove_mining_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM mining_users WHERE user_id=?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_all_mining_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id, start_time FROM mining_users") as cursor:
                return await cursor.fetchall()