import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

CATEGORIES = {
    "การเมือง (Politics)": "politics",
    "ธุรกิจ (Business)": "business",
    "สังคม (Social)": "social",
    "โลก (World)": "world",
    "วัฒนธรรม (Culture)": "culture",
    "ไลฟ์สไตล์ (Lifestyle)": "lifestyle",
    "กีฬา (Sport)": "sport",
    "Deep Space (บทความพิเศษ)": "deep-space"
}

def get_normal_news_links(soup):
    highlight_header = soup.find("h2", string="เรื่องเด่นประจำวัน")
    if highlight_header:
        highlight_block = highlight_header.find_parent("div", class_="w-full")
        if highlight_block:
            highlight_block.decompose()
    news_links = soup.find_all("a", attrs={"aria-label": ["articleLink", "latestArticleLink"]})
    return news_links

def scrape_news(category, start_page, end_page, csv_path, log_func, progress_func, page_progress_func):
    base_url = "https://spacebar.th"
    articles = []
    seen_urls = set()
    total_scraped = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyBot/1.0; +https://yourdomain.com/bot)"
    }
    page = start_page
    finished = False
    total_pages = end_page - start_page + 1 if end_page != 0 else "?"
    while not finished:
        # === แสดง label หน้า ===
        if end_page != 0:
            page_progress_func(page - start_page + 1, end_page - start_page + 1)
        else:
            page_progress_func(page - start_page + 1, "?")

        if end_page != 0 and page > end_page:
            break

        if page == 1:
            category_url = f"{base_url}/category/{category}"
        else:
            category_url = f"{base_url}/category/{category}/page/{page}"
        log_func(f"กำลังโหลดหน้า {page}: {category_url}")

        if end_page != 0:
            progress_func(page - start_page + 1, end_page - start_page + 1)

        try:
            resp = requests.get(category_url, headers=headers, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            log_func(f"[Error] โหลด {category_url} ผิดพลาด: {e}")
            time.sleep(2)
            page += 1
            continue

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        news_links = get_normal_news_links(soup)
        if not news_links:
            log_func(f"[End] ไม่พบข่าวเพิ่มเติมที่หน้า {page}")
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

                if f"/{category}/" not in news_url and not news_url.endswith(f"/{category}"):
                    continue
                if news_url in seen_urls:
                    continue
                seen_urls.add(news_url)

                try:
                    news_resp = requests.get(news_url, headers=headers, timeout=10)
                    news_resp.raise_for_status()
                except Exception as e:
                    log_func(f"[Error] โหลดข่าว {news_url} ผิดพลาด: {e}")
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
                    "หัวข้อ": title,
                    "เนื้อหา": content,
                    "วันที่": date,
                    "URL": news_url,
                })

                found_this_page += 1
                total_scraped += 1

                log_func(f"[{total_scraped}] {title[:45]} | Date: {date}")
                time.sleep(0.7)
            except Exception as e:
                log_func(f"[Error] ใน page {page}, idx {idx}: {e}")
                continue

        log_func(f"[สรุป] หน้า {page}: ได้ข่าวใหม่ {found_this_page} ข่าว (รวมทั้งหมด {total_scraped})")
        if found_this_page == 0:
            log_func(f"[End] ไม่มีข่าวใหม่ที่หน้า {page}")
            break
        page += 1

    df = pd.DataFrame(articles)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log_func(f"[Done] บันทึก {total_scraped} ข่าวเป็น {csv_path}")
    messagebox.showinfo("เสร็จสิ้น", f"บันทึก {total_scraped} ข่าวเป็น\n{csv_path}")

def choose_csv_path():
    filename = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialfile="spacebar_news.csv"
    )
    if filename:
        csv_path_var.set(filename)

def run_scraper():
    try:
        start = int(entry_start.get()) if entry_start.get().strip() else 1
        end = int(entry_end.get()) if entry_end.get().strip() else 1
        if start < 1: start = 1
    except Exception:
        start, end = 1, 1

    csv_path = csv_path_var.get().strip()
    if not csv_path:
        messagebox.showerror("Error", "กรุณากำหนดชื่อไฟล์หรือ path สำหรับ CSV ก่อน")
        return

    category_label = dropdown_category.get()
    category = CATEGORIES[category_label]

    entry_start.config(state="disabled")
    entry_end.config(state="disabled")
    dropdown_category.config(state="disabled")
    btn_choose_path.config(state="disabled")
    btn_start.config(state="disabled")

    if end == 0:
        progress_bar["mode"] = "indeterminate"
        progress_bar.start()
    else:
        progress_bar["mode"] = "determinate"
        progress_bar["maximum"] = (end - start + 1)
        progress_bar["value"] = 0

    log_text.config(state="normal")
    log_text.delete(1.0, tk.END)
    log_text.config(state="disabled")

    def log_func(msg):
        log_text.config(state="normal")
        log_text.insert(tk.END, msg + "\n")
        log_text.see(tk.END)
        log_text.config(state="disabled")
        log_text.update_idletasks()

    def progress_func(val, maxval):
        if end == 0:
            return
        progress_bar["maximum"] = maxval
        progress_bar["value"] = val
        progress_bar.update_idletasks()

    def page_progress_func(current, end_val):
        lbl_page_progress.config(text=f"กำลังดึงหน้าที่: {current} / {end_val}")
        lbl_page_progress.update_idletasks()

    def enable_all():
        entry_start.config(state="normal")
        entry_end.config(state="normal")
        dropdown_category.config(state="readonly")
        btn_choose_path.config(state="normal")
        btn_start.config(state="normal")
        progress_bar.stop()
        progress_bar["mode"] = "determinate"
        progress_bar.update_idletasks()
        lbl_page_progress.config(text="")

    def wrapper():
        scrape_news(category, start, end, csv_path, log_func, progress_func, page_progress_func)
        enable_all()

    threading.Thread(target=wrapper).start()

def toggle_dark_mode():
    mode = darkmode_var.get()
    style = ttk.Style()
    if mode:
        root.configure(bg="#23272f")
        frm.configure(style="Dark.TFrame")
        style.configure("Dark.TFrame", background="#23272f")
        style.configure("Dark.TLabel", background="#23272f", foreground="#e3eaf7")
        style.configure("Dark.TButton", background="#394150", foreground="#c9d1e9")
        style.configure("Dark.TCombobox", fieldbackground="#394150", background="#394150", foreground="#e3eaf7")
        style.configure("Dark.TEntry", fieldbackground="#394150", background="#394150", foreground="#e3eaf7")
        for widget in frm.winfo_children():
            if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Combobox):
                widget.configure(style="Dark.TEntry" if isinstance(widget, ttk.Entry) else "Dark.TCombobox")
            elif isinstance(widget, ttk.Label):
                widget.configure(style="Dark.TLabel")
            elif isinstance(widget, ttk.Button):
                widget.configure(style="Dark.TButton")
        log_text.config(bg="#242933", fg="#e3eaf7")
    else:
        root.configure(bg="#f6f7fb")
        frm.configure(style="TFrame")
        for widget in frm.winfo_children():
            if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Combobox):
                widget.configure(style="TEntry" if isinstance(widget, ttk.Entry) else "TCombobox")
            elif isinstance(widget, ttk.Label):
                widget.configure(style="TLabel")
            elif isinstance(widget, ttk.Button):
                widget.configure(style="TButton")
        log_text.config(bg="#f8fafb", fg="#333")

root = tk.Tk()
root.title("Spacebar News Scraper")
root.geometry("440x520")
root.resizable(False, False)
root.configure(bg="#f6f7fb")

frm = ttk.Frame(root, padding=22)
frm.pack(fill="both", expand=True)

# ----- หมวดข่าว -----
ttk.Label(frm, text="เลือกหมวดข่าว:").grid(row=0, column=0, sticky="e", pady=4)
dropdown_category = ttk.Combobox(frm, values=list(CATEGORIES.keys()), state="readonly", width=23)
dropdown_category.set("การเมือง (Politics)")
dropdown_category.grid(row=0, column=1, pady=4, sticky="w")

# ----- หน้าเริ่มต้น/สิ้นสุด -----
ttk.Label(frm, text="หน้าเริ่มต้น:").grid(row=1, column=0, sticky="e", pady=4)
entry_start = ttk.Entry(frm, width=8)
entry_start.grid(row=1, column=1, sticky="w", pady=4)
entry_start.insert(0, "1")
ttk.Label(frm, text="(ค่าเริ่มต้น = 1)").grid(row=1, column=2, sticky="w", padx=2)

ttk.Label(frm, text="หน้าสิ้นสุด:").grid(row=2, column=0, sticky="e", pady=4)
entry_end = ttk.Entry(frm, width=8)
entry_end.grid(row=2, column=1, sticky="w", pady=4)
entry_end.insert(0, "1")
ttk.Label(frm, text="(0 = ดึงจนจบ)").grid(row=2, column=2, sticky="w", padx=2)

# ----- เลือกไฟล์ CSV -----
ttk.Label(frm, text="CSV ไฟล์ปลายทาง:").grid(row=3, column=0, sticky="e", pady=4)
csv_path_var = tk.StringVar()
entry_csv = ttk.Entry(frm, textvariable=csv_path_var, width=28)
entry_csv.grid(row=3, column=1, pady=4, sticky="w")
entry_csv.insert(0, "spacebar_news.csv")
btn_choose_path = ttk.Button(frm, text="เลือก...", command=choose_csv_path)
btn_choose_path.grid(row=3, column=2, padx=2)

# ----- ปุ่มเริ่ม -----
btn_start = ttk.Button(frm, text="เริ่มดึงข่าว", command=run_scraper)
btn_start.grid(row=4, column=0, columnspan=3, pady=14, ipadx=12)

# ----- Label แสดงหน้าปัจจุบัน -----
lbl_page_progress = ttk.Label(frm, text="", font=("Tahoma", 11))
lbl_page_progress.grid(row=5, column=0, columnspan=3, sticky="w")

# ----- Progress & Log -----
progress_bar = ttk.Progressbar(frm, length=350, mode="determinate")
progress_bar.grid(row=6, column=0, columnspan=3, pady=3)

ttk.Label(frm, text="Log:").grid(row=7, column=0, columnspan=3, sticky="w")
log_text = tk.Text(frm, height=12, width=52, state="disabled", bg="#f8fafb", fg="#333", wrap="word", font=("Consolas", 10))
log_text.grid(row=8, column=0, columnspan=3, pady=4)

# ----- Dark Mode -----
darkmode_var = tk.IntVar()
cb_dark = tk.Checkbutton(frm, text="Dark mode", variable=darkmode_var, command=toggle_dark_mode)
cb_dark.grid(row=9, column=0, sticky="w", pady=8, columnspan=3)

root.mainloop()
