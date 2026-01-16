#!/bin/bash

# 1. 가상환경 폴더 이름
VENV_NAME="venv"

# 2. 가상환경이 없으면 생성
if [ ! -d "$VENV_NAME" ]; then
    echo "[*] 가상환경($VENV_NAME)이 없습니다. 새로 생성합니다..."
    python3 -m venv $VENV_NAME
    echo "[*] 가상환경 생성 완료."
fi

# 3. 가상환경 활성화
source $VENV_NAME/bin/activate

# 4. pip 업그레이드 (선택사항)
pip install --upgrade pip

# 5. requirements.txt 설치
if [ -f "requirements.txt" ]; then
    echo "[*] 패키지 설치 중..."
    pip install -r requirements.txt
else
    echo "[!] requirements.txt 파일이 없습니다."
    exit 1
fi

# 6. 봇 실행
echo "[*] 봇을 실행합니다..."
python3 app.py