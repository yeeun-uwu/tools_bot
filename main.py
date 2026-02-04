import discord
from discord.ext import commands
import json
import os
import sys
from modules.database import Database  # 작성했던 DB 모듈 import
from modules.logger import bot_logger  # 방금 작성한 로거 import

# ==========================================
# [1] 설정 로드
# ==========================================

CONFIG_FILE = 'config.json'

if not os.path.exists(CONFIG_FILE):
    bot_logger.error(f"[-] {CONFIG_FILE} 파일을 찾을 수 없습니다.")
    sys.exit(1)

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
        TOKEN = config.get('token')
        if not TOKEN:
            bot_logger.error("[-] config.json 파일에 'token' 값이 비어있습니다.")
            sys.exit(1)
except Exception as e:
    bot_logger.error(f"[-] 설정 파일 로드 중 오류 발생: {e}")
    sys.exit(1)

# ==========================================
# [2] 봇 클래스 정의
# ==========================================
class MyBot(commands.Bot):
    def __init__(self):
        # Intents 설정

        intents = discord.Intents.default()
        intents.guilds = True
        
        super().__init__(
            command_prefix="!", 
            intents=intents,
            help_command=None # 기본 도움말 끔 (슬래시 커맨드 위주라 불필요)
        )
    
        # DB 인스턴스 생성
        self.db = Database()

    async def setup_hook(self):
        """봇이 로그인한 직후, 준비 단계에서 실행되는 함수"""
        bot_logger.info("[*] [System] 봇 초기화 시작...")

        # 1. 데이터베이스 초기화 (테이블 생성 등)
        await self.db.initialize()
        
        # 2. Cogs(기능 모듈) 로드
        cogs_folder = 'cogs'
        if not os.path.exists(cogs_folder):
            os.makedirs(cogs_folder)
            bot_logger.warning(f"[!] '{cogs_folder}' 폴더가 없어 생성했습니다.")

        for filename in os.listdir(cogs_folder):
            if filename.endswith('.py') and not filename.startswith('__'):
                extension_name = f"{cogs_folder}.{filename[:-3]}"
                try:
                    await self.load_extension(extension_name)
                    bot_logger.info(f"[+] [Module] '{filename}' 로드 완료")
                except Exception as e:
                    bot_logger.error(f"[-] [Module] '{filename}' 로드 실패: {e}")

        # 3. 슬래시 커맨드 동기화 (서버에 명령어 등록)
        # 소규모 봇이므로 전역 동기화(self.tree.sync()) 사용
        try:
            synced = await self.tree.sync()
            bot_logger.info(f"[+] [System] 슬래시 커맨드 {len(synced)}개 동기화 완료")
        except Exception as e:
            bot_logger.error(f"[-] [System] 커맨드 동기화 실패: {e}")

    async def on_ready(self):
        """봇이 완전히 준비되었을 때 실행"""
        bot_logger.info(f"[+] [System] {self.user} (ID: {self.user.id}) 로 로그인 성공!")
        bot_logger.info(f"[i] Running on: Discord.py {discord.__version__}")
        
        # 상태 메시지 설정
        activity = discord.Game(name="/도구목록 | 봇 관리")
        await self.change_presence(status=discord.Status.online, activity=activity)

# ==========================================
# [3] 봇 실행
# ==========================================
if __name__ == '__main__':
    bot = MyBot()
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        bot_logger.critical("[!] 유효하지 않은 토큰입니다. config.json을 확인해주세요.")
    except Exception as e:
        bot_logger.critical(f"[!] 봇 실행 중 치명적 오류 발생: {e}")