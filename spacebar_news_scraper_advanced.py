import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from datetime import datetime

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
EXPORT_FORMATS = ['CSV', 'Excel', 'JSON', 'Text']
EXPORT_EXT = {'CSV': '.csv', 'Excel': '.xlsx', 'JSON': '.json', 'Text': '.txt'}

def get_normal_news_links(soup):
    highlight_header = soup.find("h2", string="เรื่องเด่นประจำวัน")
    if highlight_header:
        highlight_block = highlight_header.find_parent("div", class_="w-full")
        if highlight_block:
            highlight_block.decompose()
    news_links = soup.find_all("a", attrs={"aria-label": ["articleLink", "latestArticleLink"]})
    return news_links

def parse_date(date_str):
    for fmt in ["%d %b. %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str, fmt)
        except Exception:
            continue
    try:
        return datetime.strptime(date_str.split()[0], "%d/%m/%Y")
    except Exception:
        return None

def in_date_range(date_str, date_start, date_end):
    d = parse_date(date_str)
    if not d:
        return False
    if date_start and d < date_start:
        return False
    if date_end and d > date_end:
        return False
    return True

def read_existing_urls(filepath):
    if not os.path.exists(filepath):
        return set()
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.xlsx':
            df = pd.read_excel(filepath)
        elif ext == '.json':
            df = pd.read_json(filepath)
        elif ext == '.txt':
            urls = set()
            with open(filepath, encoding='utf-8') as f:
                for line in f:
                    if line.startswith("URL:"):
                        urls.add(line.strip()[4:].strip())
            return urls
        else:
            df = pd.read_csv(filepath)
        return set(df['URL']) if 'URL' in df.columns else set()
    except Exception:
        return set()

def scrape_news(category, start_page, end_page, log_func, progress_func, date_start=None, date_end=None, page_callback=None):
    base_url = "https://spacebar.th"
    articles = []
    seen_urls = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyBot/1.0; +https://yourdomain.com/bot)"
    }
    page = start_page
    while True:
        if end_page != 0 and page > end_page:
            break

        if page_callback:
            if end_page == 0:
                page_callback(page, None)
            else:
                page_callback(page, end_page)

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
                    if headline_tag:
                        headline = headline_tag.get_text(strip=True)
                    else:
                        headline = "[ไม่พบ headline] (DOM อาจเปลี่ยน)"

                news_url = link.get("href")
                if not news_url:
                    log_func(f"[Warn] ข่าวลำดับ {idx} ไม่พบลิงก์ (DOM เปลี่ยน?)")
                    continue

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
                if title == "[ไม่พบ headline] (DOM อาจเปลี่ยน)":
                    log_func(f"[Warn] ไม่พบ title/headline ใน {news_url}")

                date_tag = news_soup.find("p", class_="text-gray-400 text-subheadsm mb-4 md:mb-0")
                date = date_tag.get_text(strip=True) if date_tag else None
                if not date:
                    log_func(f"[Warn] ไม่พบวันที่ใน {news_url}")

                if (date_start or date_end) and date:
                    if not in_date_range(date, date_start, date_end):
                        continue

                content_div = news_soup.find("div", class_="payload-richtext")
                content = ""
                if content_div:
                    for tag in content_div.find_all(['p', 'li', 'blockquote']):
                        content += tag.get_text(separator=" ", strip=True) + "\n"
                    content = content.strip()
                else:
                    log_func(f"[Warn] ไม่พบเนื้อหา (payload-richtext) ใน {news_url}")

                articles.append({
                    "หมวด": category,
                    "หัวข้อ": title,
                    "เนื้อหา": content,
                    "วันที่": date,
                    "URL": news_url,
                })

                found_this_page += 1

                log_func(f"[{len(articles)}] {title[:45]} | Date: {date}")
                time.sleep(0.5)
            except Exception as e:
                log_func(f"[Error] ใน page {page}, idx {idx}: {e}")
                continue

        log_func(f"[สรุป] หน้า {page}: ได้ข่าวใหม่ {found_this_page} ข่าว (รวมทั้งหมด {len(articles)})")
        if found_this_page == 0:
            log_func(f"[End] ไม่มีข่าวใหม่ที่หน้า {page}")
            break
        page += 1

    return articles

def export_news(df, export_path, format_type):
    if format_type == "CSV":
        df.to_csv(export_path, index=False, encoding="utf-8-sig")
    elif format_type == "Excel":
        df.to_excel(export_path, index=False)
    elif format_type == "JSON":
        df.to_json(export_path, orient="records", force_ascii=False, indent=2)
    elif format_type == "Text":
        with open(export_path, "w", encoding="utf-8") as f:
            for idx, row in df.iterrows():
                f.write(f"หมวด: {row['หมวด']}\nหัวข้อ: {row['หัวข้อ']}\nวันที่: {row['วันที่']}\nURL: {row['URL']}\n{row['เนื้อหา']}\n{'-'*60}\n")

def show_summary(df_all, df_new, cat_display):
    total = len(df_all)
    total_new = len(df_new)
    msg = f"สรุปผลการดึงข่าว\n\nข่าวทั้งหมด: {total}\nข่าวใหม่: {total_new}\n"
    counts = df_all['หมวด'].value_counts()
    msg += "\nจำนวนข่าวแยกตามหมวด:\n"
    for c in cat_display:
        code = CATEGORIES[c]
        count = counts.get(code, 0)
        msg += f"- {c}: {count} ข่าว\n"
    messagebox.showinfo("รายงานสรุป", msg)

# ---------- GUI -----------
root = tk.Tk()
root.title("Spacebar News Scraper")
root.geometry("510x570")
root.resizable(False, False)
root.configure(bg="#f6f7fb")

frm = ttk.Frame(root, padding=(18, 15, 18, 15))
frm.pack(fill="both", expand=True)

ttk.Label(frm, text="เลือกที่หมวดหมู่:").grid(row=0, column=0, sticky="e", pady=(6, 2))
dropdown_category = ttk.Combobox(frm, values=list(CATEGORIES.keys()), state="readonly", width=24)
dropdown_category.set(list(CATEGORIES.keys())[0])
dropdown_category.grid(row=0, column=1, pady=(6, 2), columnspan=2, sticky="w")

ttk.Label(frm, text="หน้าเริ่มต้น:").grid(row=1, column=0, sticky="e", pady=4)
entry_start = ttk.Entry(frm, width=8)
entry_start.grid(row=1, column=1, sticky="w", pady=4)
entry_start.insert(0, "1")
ttk.Label(frm, text="หน้าสิ้นสุด:").grid(row=1, column=2, sticky="e", pady=4)
entry_end = ttk.Entry(frm, width=8)
entry_end.grid(row=1, column=3, sticky="w", pady=4)
entry_end.insert(0, "1")

ttk.Label(frm, text="วันที่เริ่มต้น (yyyy-mm-dd):").grid(row=2, column=0, sticky="e", pady=4)
entry_date_start = ttk.Entry(frm, width=12)
entry_date_start.grid(row=2, column=1, sticky="w", pady=4)
ttk.Label(frm, text="วันที่สิ้นสุด (yyyy-mm-dd):").grid(row=2, column=2, sticky="e", pady=4)
entry_date_end = ttk.Entry(frm, width=12)
entry_date_end.grid(row=2, column=3, sticky="w", pady=4)

lbl_hint = ttk.Label(frm, text="*ถ้าไม่กรอกวัน จะดึงตามหน้า (page) ที่เลือก", foreground="#6c6c6c")
lbl_hint.grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 6))

ttk.Label(frm, text="ไฟล์ปลายทาง:").grid(row=4, column=0, sticky="e", pady=4)
csv_path_var = tk.StringVar()
entry_csv = ttk.Entry(frm, textvariable=csv_path_var, width=32)
entry_csv.grid(row=4, column=1, pady=4, sticky="w", columnspan=2)
entry_csv.insert(0, "spacebar_news")
def choose_csv_path():
    filename = filedialog.asksaveasfilename(
        defaultextension="",
        filetypes=[
            ("CSV files", "*.csv"), ("Excel files", "*.xlsx"),
            ("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")]
        ,
        initialfile=entry_csv.get().strip() or "spacebar_news"
    )
    if filename:
        # ใช้ basename ไม่เอานามสกุล
        name_only = os.path.splitext(os.path.basename(filename))[0]
        csv_path_var.set(name_only)
btn_choose_path = ttk.Button(frm, text="เลือก...", command=choose_csv_path)
btn_choose_path.grid(row=4, column=3, padx=2)

ttk.Label(frm, text="Export เป็นไฟล์:").grid(row=5, column=0, sticky="e", pady=4)
dropdown_format = ttk.Combobox(frm, values=EXPORT_FORMATS, state="readonly", width=10)
dropdown_format.set("CSV")
dropdown_format.grid(row=5, column=1, pady=4, sticky="w")

export_new_var = tk.IntVar(value=1)
cb_export_new = tk.Checkbutton(frm, text="Export เฉพาะข่าวใหม่ (เทียบไฟล์เดิม)", variable=export_new_var)
cb_export_new.grid(row=5, column=2, columnspan=2, sticky="w", pady=2)

btn_start = ttk.Button(frm, text="เริ่มดึงข่าว", width=20)
btn_start.grid(row=6, column=0, columnspan=4, pady=14, ipadx=8)

progress_bar = ttk.Progressbar(frm, length=350, mode="determinate")
progress_bar.grid(row=7, column=0, columnspan=4, pady=(3, 0))

label_current_page = ttk.Label(frm, text="", foreground="#0076D6", font=("Segoe UI", 10, "bold"))
label_current_page.grid(row=8, column=0, columnspan=4, pady=(2, 2), sticky="w")

ttk.Label(frm, text="Log:").grid(row=9, column=0, columnspan=4, sticky="w")
log_text = tk.Text(frm, height=12, width=58, state="disabled", bg="#f8fafb", fg="#333", wrap="word", font=("Consolas", 10))
log_text.grid(row=10, column=0, columnspan=4, pady=4)

darkmode_var = tk.IntVar()
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
        label_current_page.config(foreground="#44aaff")
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
        label_current_page.config(foreground="#0076D6")
cb_dark = tk.Checkbutton(frm, text="Dark mode", variable=darkmode_var, command=toggle_dark_mode)
cb_dark.grid(row=11, column=0, sticky="w", pady=8, columnspan=4)

def run_scraper():
    try:
        start = int(entry_start.get()) if entry_start.get().strip() else 1
        end = int(entry_end.get()) if entry_end.get().strip() else 1
        if start < 1: start = 1
    except Exception:
        start, end = 1, 1

    date_start_str = entry_date_start.get().strip()
    date_end_str = entry_date_end.get().strip()
    date_start = None
    date_end = None
    if date_start_str:
        try:
            date_start = datetime.strptime(date_start_str, "%Y-%m-%d")
        except Exception:
            messagebox.showerror("Error", "วันที่เริ่มต้นไม่ถูกต้อง! ใช้รูปแบบ yyyy-mm-dd")
            entry_date_start.focus()
            return
    if date_end_str:
        try:
            date_end = datetime.strptime(date_end_str, "%Y-%m-%d")
        except Exception:
            messagebox.showerror("Error", "วันที่สิ้นสุดไม่ถูกต้อง! ใช้รูปแบบ yyyy-mm-dd")
            entry_date_end.focus()
            return

    # ---- Generate export path ----
    file_basename = csv_path_var.get().strip()
    file_type = dropdown_format.get()
    if not file_basename:
        messagebox.showerror("Error", "กรุณากำหนดชื่อไฟล์ (ไม่ต้องใส่นามสกุล)")
        return
    ext = EXPORT_EXT[file_type]
    export_path = file_basename + ext

    cat_display = [dropdown_category.get()]
    cat_code = CATEGORIES[cat_display[0]]

    format_type = file_type
    export_only_new = export_new_var.get()

    entry_start.config(state="disabled")
    entry_end.config(state="disabled")
    dropdown_category.config(state="disabled")
    btn_choose_path.config(state="disabled")
    btn_start.config(state="disabled")
    entry_date_start.config(state="disabled")
    entry_date_end.config(state="disabled")
    dropdown_format.config(state="disabled")
    cb_export_new.config(state="disabled")

    progress_bar["mode"] = "determinate"
    progress_bar["value"] = 0

    log_text.config(state="normal")
    log_text.delete(1.0, tk.END)
    log_text.config(state="disabled")

    label_current_page.config(text="")  # reset

    def log_func(msg):
        log_text.config(state="normal")
        log_text.insert(tk.END, msg + "\n")
        log_text.see(tk.END)
        log_text.config(state="disabled")
        log_text.update_idletasks()
    def progress_func(val, maxval):
        progress_bar["maximum"] = maxval
        progress_bar["value"] = val
        progress_bar.update_idletasks()
    def page_callback(current, end_val):
        if end_val:
            label_current_page.config(text=f"กำลังดึงหน้าที่: {current} / {end_val}")
        else:
            label_current_page.config(text=f"หน้าปัจจุบัน: {current} (ดึงจนจบ)")
        label_current_page.update_idletasks()

    def enable_all():
        entry_start.config(state="normal")
        entry_end.config(state="normal")
        dropdown_category.config(state="readonly")
        btn_choose_path.config(state="normal")
        btn_start.config(state="normal")
        entry_date_start.config(state="normal")
        entry_date_end.config(state="normal")
        dropdown_format.config(state="readonly")
        cb_export_new.config(state="normal")
        progress_bar.stop()
        progress_bar["mode"] = "determinate"
        progress_bar.update_idletasks()
        label_current_page.config(text="")

    def wrapper():
        if (not date_start_str and not date_end_str):
            log_func("**ไม่ได้กำหนดช่วงวันที่ จะดึงข่าวตามหน้า (page) ที่เลือก**")
        else:
            log_func("**กำลังกรองข่าวเฉพาะในช่วงวันที่**")

        all_articles = scrape_news(
            cat_code, start, end, log_func, progress_func,
            date_start=date_start, date_end=date_end,
            page_callback=page_callback
        )
        if not all_articles:
            log_func("ไม่พบข่าวตามเงื่อนไข")
            enable_all()
            return
        df_all = pd.DataFrame(all_articles)
        df_new = df_all
        if export_only_new:
            existing_urls = read_existing_urls(export_path)
            df_new = df_all[~df_all["URL"].isin(existing_urls)]
            log_func(f"ข่าวใหม่ที่จะ export: {len(df_new)} ข่าว")
        else:
            log_func(f"ข่าวทั้งหมดที่จะ export: {len(df_all)} ข่าว")
        if len(df_new) == 0:
            messagebox.showinfo("ไม่มีข่าวใหม่", "ไม่มีข่าวใหม่ที่จะ export")
        else:
            export_news(df_new, export_path, format_type)
            log_func(f"[Done] Export {len(df_new)} ข่าวเป็น {export_path}")
        show_summary(df_all, df_new, cat_display)
        enable_all()
    threading.Thread(target=wrapper).start()

btn_start.config(command=run_scraper)

root.mainloop()
