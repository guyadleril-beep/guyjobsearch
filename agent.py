import asyncio
import sqlite3
import os
import requests
from pydantic import BaseModel
from browser_use import Agent, ChatBrowserUse
from dotenv import load_dotenv

load_dotenv()

class JobMatch(BaseModel):
    is_relevant_role: bool
    is_student_position: bool
    location_match: bool
    job_title: str
    company_name: str
    job_url: str
    reasoning: str

def setup_db():
    conn = sqlite3.connect('jobs_state.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (url TEXT PRIMARY KEY, title TEXT, company TEXT, date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn

def send_telegram_alert(job_data: JobMatch):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message = (
        f"🎯 <b>משרת סטודנט חדשה אותרה!</b>\n\n"
        f"<b>חברה:</b> {job_data.company_name}\n"
        f"<b>תפקיד:</b> {job_data.job_title}\n\n"
        f"<b>למה זה מתאים?</b>\n{job_data.reasoning}\n\n"
        f"<a href='{job_data.job_url}'>למעבר לעמוד המשרה לחץ כאן</a>"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=payload)

async def main():
    db_conn = setup_db()
    cursor = db_conn.cursor()
    
    task_description = """
    Go to a major Israeli job board or LinkedIn. Search for student positions in Industrial Engineering 
    (סטודנט תעשייה וניהול) located strictly between Haifa and Karmiel. 
    """
    
    # שימוש במודל של גוגל לפי ה-API KEY שהזנת
    agent = Agent(
        task=task_description,
        llm=ChatBrowserUse(model='google/gemini-2.5-pro', api_key=os.getenv("LLM_API_KEY"))
    )
    
    simulated_found_jobs = [
        JobMatch(
            is_relevant_role=True,
            is_student_position=True,
            location_match=True,
            job_title="סטודנט/ית הנדסת תעשייה וניהול",
            company_name="חברה לדוגמה - פארק בר לב",
            job_url="https://example.com/job",
            reasoning="המשרה ממוקמת באזור הצפון (בין חיפה לכרמיאל) ומיועדת במפורש לסטודנטים."
        )
    ]
    
    for job in simulated_found_jobs:
        if job.is_relevant_role and job.is_student_position and job.location_match:
            try:
                cursor.execute("INSERT INTO jobs (url, title, company) VALUES (?, ?, ?)", 
                               (job.job_url, job.job_title, job.company_name))
                db_conn.commit()
                send_telegram_alert(job)
                print(f"Alert sent for: {job.job_title}")
            except sqlite3.IntegrityError:
                print(f"Job already exists: {job.job_title}")

    db_conn.close()

if __name__ == "__main__":
    asyncio.run(main())
