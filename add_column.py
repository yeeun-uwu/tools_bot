import sqlite3

# DB 연결
conn = sqlite3.connect("tools.db")
cursor = conn.cursor()

try:
    # borrower_nick 컬럼 추가 명령어
    cursor.execute("ALTER TABLE tools ADD COLUMN borrower_nick TEXT")
    conn.commit()
    print("[*] 컬럼 추가 완료!")
except sqlite3.OperationalError:
    print("[!] 이미 컬럼이 존재하거나 오류가 발생했습니다.")

conn.close()