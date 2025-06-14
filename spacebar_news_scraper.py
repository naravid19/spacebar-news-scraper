import requests
from bs4 import BeautifulSoup
import time
import pandas as pd

def ask_category():
    categories = {
        "การเมือง": "politics",
        "ธุรกิจ": "business",
        "สังคม": "social",
        "โลก": "world",
        "วัฒนธรรม": "culture",
        "ไลฟ์สไตล์": "lifestyle",
        "กีฬา": "sport",
        "Deep Space": "deep-space"
    }
    print("Available categories:")
    for i, (th, en) in enumerate(categories.items(), 1):
        print(f"  {i}. {th} ({en})")
    sel = input("เลือก category ที่ต้องการ (en หรือ เลข): ").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(categories):
        return list(categories.values())[int(sel)-1]
    if sel in categories.values():
        return sel
    print("Category ไม่ถูกต้อง ใช้ 'politics' (ข่าวการเมือง) เป็นค่าเริ่มต้น")
    return "politics"

def ask_page_range():
    try:
        start = input("ต้องการดึงข่าวจากหน้าไหน? (เริ่มหน้า, default=1): ")
        end = input("ถึงหน้าไหน? (จบหน้า, 0=ดึงจนจบ, default=1): ")
        start_page = int(start.strip()) if start.strip() else 1
        end_page = int(end.strip()) if end.strip() else 1
        if start_page < 1: start_page = 1
        if end_page != 0 and end_page < start_page:
            end_page = start_page
        return start_page, end_page
    except Exception as e:
        print(f"ค่าที่ใส่ไม่ถูกต้อง ใช้หน้าแรกแทน (1)")
        return 1, 1

def main():
    base_url = "https://spacebar.th"
    category = ask_category()
    start_page, end_page = ask_page_range()
    articles = []
    seen_urls = set()
    total_scraped = 0

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyBot/1.0; +https://yourdomain.com/bot)"
    }

    page = start_page
    try:
        while True:
            if end_page != 0 and page > end_page:
                break

            if page == 1:
                category_url = f"{base_url}/category/{category}"
            else:
                category_url = f"{base_url}/category/{category}/page/{page}"
            print(f"\n[Progress] Loading page {page}: {category_url}")

            try:
                resp = requests.get(category_url, headers=headers, timeout=10)
                resp.raise_for_status()
            except Exception as e:
                print(f"[Error] โหลด {category_url} ผิดพลาด: {e}")
                time.sleep(2)
                page += 1
                continue

            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            news_links = soup.find_all("a", attrs={"aria-label": ["articleLink", "latestArticleLink"]})
            if not news_links:
                print(f"\n[End] No more news found on page {page}. Stop scraping.")
                break

            found_this_page = 0
            for idx, link in enumerate(news_links, start=1):
                try:
                    headline_div = link.find("div", class_="w-full text-base font-semibold text-gray-700 hover:text-accentual-blue-main mb-2 line-clamp-3")
                    if headline_div:
                        headline = headline_div.get_text(strip=True)
                    else:
                        headline_tag = link.find("h3")
                        headline = headline_tag.get_text(strip=True) if headline_tag else None

                    news_url = link["href"]
                    if news_url.startswith("/"):
                        news_url = base_url + news_url

                    if f"/{category}/" not in news_url:
                        continue
                    if news_url in seen_urls:
                        continue
                    seen_urls.add(news_url)

                    # Request ข่าวแต่ละชิ้น
                    try:
                        news_resp = requests.get(news_url, headers=headers, timeout=10)
                        news_resp.raise_for_status()
                    except Exception as e:
                        print(f"[Error] โหลดข่าว {news_url} ผิดพลาด: {e}")
                        time.sleep(2)
                        continue

                    news_resp.encoding = "utf-8"
                    news_soup = BeautifulSoup(news_resp.text, "html.parser")

                    title_tag = news_soup.find("h1", class_="article-title")
                    title = title_tag.get_text(strip=True) if title_tag else headline

                    date_tag = news_soup.find("p", class_="text-gray-400 text-subheadsm mb-4 md:mb-0")
                    date = date_tag.get_text(strip=True) if date_tag else None

                    content_div = news_soup.find("div", class_="payload-richtext")
                    content = ""
                    if content_div:
                        for tag in content_div.find_all(['p', 'li', 'blockquote']):
                            content += tag.get_text(separator=" ", strip=True) + "\n"
                    content = content.strip()

                    articles.append({
                        "category": category,
                        "title": title,
                        "content": content,
                        "date": date,
                        "URL": news_url,
                    })

                    found_this_page += 1
                    total_scraped += 1

                    print(f"[{total_scraped}] {title[:45]} | Date: {date} | {news_url}")

                    time.sleep(1)

                except Exception as e:
                    print(f"[Error] Processing news on page {page}, idx {idx}: {e}")
                    continue

            print(f"[Summary] Page {page} — Scraped {found_this_page} new news articles (Total: {total_scraped})")

            if found_this_page == 0:
                print(f"[End] No new news on page {page}. Scraping likely complete.")
                break

            page += 1

    except KeyboardInterrupt:
        print("\n[Stopped] Scraper interrupted by user. Saving results...")

    # Export CSV
    try:
        df = pd.DataFrame(articles)
        outname = f"spacebar_{category}_news.csv"
        df.to_csv(outname, index=False, encoding="utf-8-sig")
        print(f"\n[Done] Exported {total_scraped} news articles to {outname}")
    except Exception as e:
        print(f"[Error] ไม่สามารถบันทึกไฟล์ CSV: {e}")

if __name__ == "__main__":
    main()
