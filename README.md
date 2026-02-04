## 현재 파일 구조 

```
TOOLS_BOT/  
├── .gitignore             # 보안 및 불필요 파일 제외 설정  
├── config.json            # 봇 토큰 등 설정 파일  
├── main.py                #  봇 실행 및 Cogs 로드  
├── requirements.txt       # 필요한 라이브러리 목록  
├── run.sh                 # 실행 스크립트  
├── data/                  # DB와 로그를 한곳에 모아 백업 편의성 증대  
│   ├── tools.db           # 통합 데이터베이스 (자동 생성됨)  
│   └── logs/              # 일자별 로그 폴더  
├── cogs/                  # 명령어 모듈 폴더  
│   ├── __init__.py
│   ├── tools.py           # 도구 대여/반납/목록  
│   ├── users.py           # 닉네임 설정/내정보  
│   ├── mining.py          # 잠광 관리(타이머, 버튼, 대시보드)  
│   └── admin.py           # 관리자 기능 (로그다운, 강제조치 등)  
└── modules/               # 공통 로직  
    ├── __init__.py
    ├── database.py        # DB 연결/마이그레이션/쿼리 전담  
    └── logger.py          # 로깅 시스템 래퍼(Wrapper)
```
