import asyncio
import sqlite3
import os
import requests
import json
from browser_use import Agent
from browser_use.llm import ChatGoogle
from dotenv import load_dotenv

load_dotenv()

def setup_db():
    conn = sqlite3.connect('jobs_state.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (url TEXT PRIMARY KEY, title TEXT, company TEXT, date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn

def send_telegram_alert(job_data: dict):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message = (
        f"🎯 <b>משרת סטודנט אמיתית חדשה אותרה!</b>\n\n"
        f"<b>חברה:</b> {job_data.get('company_name', 'לא צוין')}\n"
        f"<b>תפקיד:</b> {job_data.get('job_title', 'לא צוין')}\n\n"
        f"<b>למה זה מתאים?</b>\n{job_data.get('reasoning', 'נמצאה התאמה לדרישות.')}\n\n"
        f"<a href='{job_data.get('job_url', '#')}'>למעבר לעמוד המשרה לחץ כאן</a>"
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
    Go to Israeli job boards (like drushim.co.il, alljobs.co.il) or LinkedIn.
    Search for student roles in the area between Haifa and Karmiel (North Israel).
    Focus specifically on these fields: Data Analyst, Information Systems (מערכות מידע), PMO, and Project Management (ניהול פרויקטים).
    
    CRITICAL STEP: You must read the FULL job description and the requirements section for the jobs you find.
    Classify the job as a match ONLY if all the following conditions are met:
    1. It is a part-time student position.
    2. The requirements specifically mention or highly fit a student studying Industrial Engineering (הנדסת תעשייה וניהול) with a technical/information systems orientation.
    3. STRICTLY EXCLUDE classic manufacturing roles: reject any job related to PP&C (תפ"י / תכנון פיקוח ייצור), Quality Control (בקרת איכות / הנדסת איכות), and production floor roles.
    
    Return ONE matching job STRICTLY as a valid JSON object with the following keys:
    "is_relevant_role" (boolean), "is_student_position" (boolean), "location_match" (boolean), 
    "job_title" (string), "company_name" (string), "job_url" (string URL), "reasoning" (string, short explanation of why it fits the Information Systems/Data criteria and how it matches an IE student).
    Do not add any text before or after the JSON.
    """
    
    # שימוש במעטפת הייעודית של הספרייה במקום בזו של LangChain
    llm = ChatGoogle(model='gemini-2.5-pro', api_key=os.getenv("LLM_API_KEY"))
    agent = Agent(task=task_description, llm=llm)
    
    print("מתחיל סריקה אמיתית ברחבי הרשת...")
    history = await agent.run()
    
    try:
        final_result = history.final_result()
        if "```json" in final_result:
            final_result = final_result.split("```json")[1].split("```")[0].strip()
        elif "```" in final_result:
            final_result = final_result.split("```")[1].strip()
            
        job = json.loads(final_result)
        
        if job.get("is_relevant_role") and job.get("is_student_position") and job.get("location_match"):
            try:
                cursor.execute("INSERT INTO jobs (url, title, company) VALUES (?, ?, ?)", 
                               (job["job_url"], job["job_title"], job["company_name"]))
                db_conn.commit()
                
                send_telegram_alert(job)
                print(f"נמצאה משרה אמיתית! התראה נשלחה: {job['job_title']}")
                
            except sqlite3.IntegrityError:
                print(f"המשרה כבר קיימת במסד הנתונים ולא תישלח שוב: {job['job_title']}")
        else:
            print("המשרה שנמצאה אינה תואמת ב-100% לדרישות ולכן לא נשלחה.")
            
    except Exception as e:
        print(f"שגיאה בפענוח המשרה או שלא נמצאו משרות חדשות: {e}")

    db_conn.close()

if __name__ == "__main__":
    asyncio.run(main())
