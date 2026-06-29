import os
import re
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

INSTAGRAM_PATTERN = re.compile(r'https?://(?:www\.)?instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)')

def extract_instagram_url(text: str) -> str | None:
    match = INSTAGRAM_PATTERN.search(text)
    return match.group(0) if match else None

def parse_caption_simple(text: str, reel_url: str) -> dict:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    name = None
    location = None
    category = "food"

    activity_keywords = ['액티비티', '놀거리', '투어', '체험', '클라이밍', '서핑', '하이킹', 
                        'activity', 'tour', 'experience', 'climbing', 'surfing', 'hiking', 
                        '공원', '전시', '박물관', '미술관']
    food_keywords = ['맛집', '식당', '카페', '레스토랑', '음식', 'cafe', 'restaurant', 
                    'food', 'ramen', '라멘', '스시', '초밥', '커피', 'coffee', '바']

    text_lower = text.lower()
    for kw in activity_keywords:
        if kw.lower() in text_lower:
            category = "activity"
            break

    hashtags = re.findall(r'#(\w+)', text)
    
    location_patterns = [
        r'📍\s*(.+)',
        r'위치[:\s]+(.+)',
        r'location[:\s]+(.+)',
        r'주소[:\s]+(.+)',
    ]
    for pattern in location_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            location = m.group(1).strip()
            break

    if lines:
        first_line = lines[0]
        if not first_line.startswith('#') and not first_line.startswith('📍'):
            name = first_line[:50]

    if not name:
        name = "저장된 장소"
    if not location:
        for tag in hashtags:
            if len(tag) > 2 and not any(kw in tag.lower() for kw in ['맛집', 'food', 'daily', 'instagood']):
                location = f"#{tag}"
                break
        if not location:
            location = "위치 미상"

    return {
        "name": name,
        "location": location,
        "category": category,
        "reel_url": reel_url,
        "caption": text[:500],
    }

async def save_to_supabase(data: dict, added_by: str) -> bool:
    data["added_by"] = added_by
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/spots",
            json=data,
            headers=headers
        )
        return resp.status_code in (200, 201)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    reel_url = extract_instagram_url(text)

    if not reel_url:
        return

    user = update.message.from_user
    username = user.username or user.first_name or "unknown"

    await update.message.reply_text("🔍 릴스 분석 중...")

    lines = text.strip().split('\n')
    extra_info = '\n'.join(lines[1:]) if len(lines) > 1 else ''
    
    if '|' in extra_info:
        parts = [p.strip() for p in extra_info.split('|')]
        name = parts[0] if len(parts) > 0 else None
        location = parts[1] if len(parts) > 1 else None
        category_raw = parts[2].lower() if len(parts) > 2 else 'food'
        category = 'activity' if '활동' in category_raw or 'activity' in category_raw else 'food'
        
        spot_data = {
            "name": name or "저장된 장소",
            "location": location or "위치 미상",
            "category": category,
            "reel_url": reel_url,
            "caption": extra_info[:500],
        }
    else:
        caption_text = extra_info if extra_info else text
        spot_data = parse_caption_simple(caption_text, reel_url)

    spot_data["reel_url"] = reel_url
    success = await save_to_supabase(spot_data, username)

    if success:
        cat_emoji = "🍜" if spot_data["category"] == "food" else "🎯"
        await update.message.reply_text(
            f"✅ 저장 완료!\n\n"
            f"{cat_emoji} {spot_data['name']}\n"
            f"📍 {spot_data['location']}\n"
            f"🔗 {reel_url}"
        )
    else:
        await update.message.reply_text("❌ 저장 실패. 다시 시도해줘!")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("봇 시작!")
    app.run_polling()

if __name__ == "__main__":
    main()
