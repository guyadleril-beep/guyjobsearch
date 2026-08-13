import asyncio
import sqlite3
import os
import requests
import json
from browser_use import Agent, Browser
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
    Go DIRECTLY to the following career pages in Israel:
    1. https://career.rafael.co.il/students/ (Rafael)
    2. https://career.rafael.co.il/search/ (Rafael)
    3. https://www.alljobs.co.il/m/p/company?cid=47510 (Elbit Systems)
    4. https://jobs.intel.com/en/search-jobs?k=&l=Haifa (Intel Haifa)
    5. https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite (NVIDIA / Mellanox Yokneam)
    6. https://jobs.apple.com/en-il/search?location=haifa-HFA (Apple Haifa)
    7. https://careers.microsoft.com/v2/global/en/home.html (Microsoft Haifa)
    8. https://careers.philips.com/global/en/search-results?location=Haifa (Philips Healthcare Haifa)
    9. https://careers.kla.com/jobs/search (KLA Migdal HaEmek)
    10. https://www.marvell.com/company/careers.html (Marvell Yokneam)
    11. https://jobs.jnj.com/en/jobs/?search=&location=Yokneam (Biosense Webster Yokneam)
    12. https://careers.solaredge.com/jobs (SolarEdge North)
    13. https://careers.ibm.com/job/search/?q=&location=Haifa (IBM Haifa)
    14. https://careers.amazon.com/search?location=Haifa (Amazon Haifa)
    15. https://careers.medtronic.com/search-jobs/Yokneam (Medtronic Yokneam)
    16. https://lumenis.com/careers/ (Lumenis Yokneam)
    17. https://www.towersemi.com/about/careers/ (Tower Semiconductor Migdal HaEmek)
    18. https://jobs.checkpointexperience.com/ (Check Point Haifa)
    19. https://jobs.amdocs.com/ (Amdocs Haifa / Nazareth)
    20. https://www.zim.com/about-zim/careers (ZIM Haifa)
    21. https://careers.flex.com/search-jobs (Flex Haifa / Migdal HaEmek)
    22. https://strauss-group.co.il/careers/ (Strauss Group Karmiel)
    
    Scan the job listings on these pages. 
    Find the BEST match for a student position in Data Analysis, PMO, or Information Systems.
    
    Rules for matching:
    1. Must be a student/part-time position.
    2. Relevant for Industrial Engineering (Information Systems track).
    3. Exclude classic manufacturing/production roles (like QC or PP&C).
    4. Must be located in Northern Israel (specifically the area between Haifa, Yokneam, and Karmiel).
    
    Review the jobs on these pages. If you find a good match, return it STRICTLY as a valid JSON object with the following keys:
    "is_relevant_role" (boolean), "is_student_position" (boolean), "location_match" (boolean), 
    "job_title" (string), "company_name" (string), "job_url" (string URL), "reasoning" (string).
    Do not add any text before or after the JSON.
"""
    
    llm = ChatGoogle(model='gemini-2.5-pro', api_key=os.getenv("LLM_API_KEY"))
    
    # הפתרון: מעבירים את נתוני סביבת הלינוקס ישירות לאובייקט הדפדפן ללא BrowserConfig
    browser = Browser(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox']
    )
    
    agent = Agent(task=task_description, llm=llm, browser=browser)
    
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
