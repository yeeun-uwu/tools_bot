import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

# 로그 저장 경로 (프로젝트 루트의 data/logs 폴더)
LOG_DIR = os.path.join("data", "logs")

def setup_logger():
    """로깅 설정을 초기화하고 로거 인스턴스를 반환합니다."""
    
    # 로그 폴더가 없으면 생성
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    # 로거 생성
    logger = logging.getLogger("MyBot")
    logger.setLevel(logging.INFO) # INFO 등급 이상만 기록 (Debug < Info < Warning < Error)

    # 포맷 설정 (시간 - 등급 - 메시지)
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 파일 핸들러 설정 (매일 자정마다 새 파일 생성)
    # 파일명: bot.log -> (날짜 지나면) bot.log.2023-10-01
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "bot.log"),
        when="midnight",  # 자정 기준 회전
        interval=1,       # 1일마다
        backupCount=7,   # 30일치 로그 보관 (오래된 것 자동 삭제)
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d" # 백업 파일명 뒤에 날짜 형식

    # 스트림 핸들러 설정 (터미널 출력용)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # 핸들러 등록 (중복 방지)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    
    return logger

# 다른 파일에서 import bot_logger만 하면 바로 쓸 수 있게 미리 생성
bot_logger = setup_logger()