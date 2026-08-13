import asyncio
import sqlite3
import os
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ==========================================
# 1. הגדרת המבנה שאנחנו דורשים מ-Gemini להחזיר
# ==========================================
class JobMatch(BaseModel):
    is_relevant_role: bool = Field(description="Is it Data Analysis, PMO, or Information Systems?")
    is_student_position: bool = Field(description="Is it a student or part-time position?")
    location_match: bool = Field(description="Is it located in Northern Israel (Haifa, Yokneam, Karmiel)?")
    job_title: str = Field(description="The specific job title found")
    company_name: str = Field(description="The company name")
    job_url: str = Field(description="The URL to apply for the job")
    reasoning: str = Field(description="Short explanation of why it matched or why it was rejected")

# ==========================================
# 2. מסד נתונים וטלגרם (הפונקציות המקוריות שלך)
# ==========================================
def setup_db():
    conn = sqlite3.connect('jobs_state.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (url TEXT PRIMARY KEY, title TEXT, company TEXT, date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn

def send_telegram_alert(job: JobMatch):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ חסרים נתוני טלגרם, מדלג על שליחת התראה.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message = (
        f"🎯 <b>משרת סטודנט אמיתית חדשה אותרה!</b>\n\n"
        f"<b>חברה:</b> {job.company_name}\n"
        f"<b>תפקיד:</b> {job.job_title}\n\n"
        f"<b>למה זה מתאים?</b>\n{job.reasoning}\n\n"
        f"<a href='{job.job_url}'>למעבר לעמוד המשרה לחץ כאן</a>"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=payload)

# ==========================================
# 3. רשימת האתרים לסריקה
# ==========================================
URLS = [
    "https://career.rafael.co.il/students/",
    "https://career.rafael.co.il/search/",
    "https://www.alljobs.co.il/m/p/company?cid=47510",
    "https://jobs.intel.com/en/search-jobs?k=&l=Haifa",
    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
    "https://jobs.apple.com/en-il/search?location=haifa-HFA",
    "https://careers.microsoft.com/v2/global/en/home.html",
    "https://careers.philips.com/global/en/search-results?location=Haifa",
    "https://careers.kla.com/jobs/search",
    "https://www.marvell.com/company/careers.html",
    "https://jobs.jnj.com/en/jobs/?search=&location=Yokneam",
    "https://careers.solaredge.com/jobs",
    "https://careers.ibm.com/job/search/?q=&location=Haifa",
    "https://careers.amazon.com/search?location=Haifa",
    "https://careers.medtronic.com/search-jobs/Yokneam",
    "https://lumenis.com/careers/",
    "https://www.towersemi.com/about/careers/",
    "https://jobs.checkpointexperience.com/",
    "https://jobs.amdocs.com/",
    "https://www.zim.com/about-zim/careers",
    "https://careers.flex.com/search-jobs",
    "https://strauss-group.co.il/careers/"
]

# ==========================================
# 4. לוגיקת הסריקה והניתוח
# ==========================================
async def scrape_and_analyze(url, page, structured_llm):
    print(f"🔍 סורק את: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000) 
        
        page_text = await page.evaluate("document.body.innerText")
        
        if not page_text or len(page_text.strip()) < 50:
            print(f"❌ לא נמצא תוכן משמעותי באתר {url}")
            return None

        prompt = f"""
        You are an expert HR assistant helping an Industrial Engineering student (Information Systems track) find a job.
        Scan the following text extracted from a career page: {url}
        
        Find the BEST single match for a student position in Data Analysis, PMO, or Information Systems.
        
        Rules for matching:
        1. Must be a student/part-time position.
        2. Relevant for Industrial Engineering (Information Systems track).
        3. Exclude classic manufacturing/production roles (like QC or PP&C).
        4. Must be located in Northern Israel (Haifa, Yokneam, Karmiel, Migdal HaEmek, Krayot).
        
        If no job perfectly matches all criteria, just return the closest one and set the booleans accurately to False.
        
        Page Text:
        {page_text[:40000]}
        """
        
        result = await structured_llm.ainvoke(prompt)
        return result
        
    except Exception as e:
        print(f"⚠️ שגיאה בשליפת הטקסט מ-{url}: {e}")
        return None

# ==========================================
# 5. פונקציית הריצה המרכזית
# ==========================================
async def main():
    db_conn = setup_db()
    cursor = db_conn.cursor()
    
    # תמיכה בשם המשתנה המקורי שלך (LLM_API_KEY) או בסטנדרט של langchain
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("שגיאה: לא נמצא מפתח API של גוגל בקובץ ה-.env")
        return

    # אתחול המודל עם יציאת JSON מובנית
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0.0,
        google_api_key=api_key
    )
    structured_llm = llm.with_structured_output(JobMatch)
    
    print("🚀 מתחיל סריקה אמיתית ברחבי הרשת...")
    
    # הרצת דפדפן (שמרתי את הארגומנטים שלך לסביבת לינוקס/שרת)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # עקיפת הגנות נגד בוטים של חברות כמו אינטל ואפל
        await stealth_async(page)
        
        for url in URLS:
            job_match = await scrape_and_analyze(url, page, structured_llm)
            
            if job_match:
                if job_match.is_relevant_role and job_match.is_student_position and job_match.location_match:
                    try:
                        # ניסיון הכנסה למסד הנתונים כדי למנוע כפילויות
                        cursor.execute("INSERT INTO jobs (url, title, company) VALUES (?, ?, ?)", 
                                       (job_match.job_url, job_match.job_title, job_match.company_name))
                        db_conn.commit()
                        
                        send_telegram_alert(job_match)
                        print(f"✅ נמצאה משרה אמיתית! התראה נשלחה: {job_match.job_title}")
                        
                    except sqlite3.IntegrityError:
                        print(f"⏭️ המשרה כבר קיימת במסד הנתונים ולא תישלח שוב: {job_match.job_title}")
                else:
                    print("⏭️ המשרה שנמצאה אינה תואמת ב-100% לדרישות ולכן לא נשלחה.")
        
        await browser.close()
    
    db_conn.close()
    print("✅ הסריקה הסתיימה בהצלחה.")

if __name__ == "__main__":
    asyncio.run(main())
