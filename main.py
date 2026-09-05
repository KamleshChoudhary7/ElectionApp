import os
import re
import sqlite3
import shutil
import threading
import time
import unicodedata
from datetime import datetime
from pypdf import PdfReader
from openpyxl import Workbook
from PIL import Image as PILImage

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.image import Image
from kivy.uix.filechooser import FileChooserListView
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.utils import platform
from kivy.clock import Clock

if platform not in ('android', 'ios'):
    Window.size = (420, 780)

# --- ANDROID SAFE PATH GENERATOR ---
def get_db_path():
    if platform == 'android':
        return os.path.join(App.get_running_app().user_data_dir, "voters_warroom.db")
    return "voters_warroom.db"

def get_export_dir():
    if platform == 'android':
        try:
            from android.storage import primary_external_storage_path
            export_path = os.path.join(primary_external_storage_path(), "Download")
            if not os.path.exists(export_path):
                os.makedirs(export_path)
            return export_path
        except Exception:
            return App.get_running_app().user_data_dir
    return os.getcwd()

# ----------------- OFFLINE DATA ENGINE -----------------

CHAR_MAP = {'क':'k','ख':'kh','ग':'g','घ':'gh','ङ':'n','च':'ch','छ':'chh','ज':'j','झ':'jh','ञ':'n','ट':'t','ठ':'th','ड':'d','ढ':'dh','ण':'n','त':'t','थ':'th','द':'d','ध':'dh','न':'n','प':'p','फ':'ph','ब':'b','भ':'bh','म':'m','य':'y','र':'r','ल':'l','व':'v','श':'sh','ष':'sh','स':'s','ह':'h','क्ष':'ksh','त्र':'tr','ज्ञ':'gy','ा':'a','ि':'i','ी':'ee','ु':'u','ू':'oo','ृ':'ri','े':'e','ै':'ai','ो':'o','ौ':'au','ं':'n','्':'','़':''}
VOWEL_MAP = {'अ':'a','आ':'aa','इ':'i','ई':'ee','उ':'u','ऊ':'oo','ए':'e','ऐ':'ai','ओ':'o','औ':'au'}

def clean_hindi(raw_text):
    if not raw_text: return ""
    t = unicodedata.normalize('NFC', raw_text).replace("Photo is", "").replace("Available", "").strip()
    return re.sub(r'\s+', ' ', t).strip()

def init_db():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS voters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ward TEXT, part TEXT, sr_no INTEGER, epic TEXT, 
        name TEXT, rel_type TEXT, rel_name TEXT, house TEXT, age INTEGER, gender TEXT, 
        mobile TEXT DEFAULT '', tag TEXT DEFAULT 'सामान्य', notes TEXT DEFAULT '', 
        voted INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0, UNIQUE(part, sr_no))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS evm_diary (
        id INTEGER PRIMARY KEY, cu TEXT, bu TEXT, vvpat TEXT, mock_votes INTEGER, notes TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY, time TEXT, detail TEXT)''')
    conn.commit(); conn.close()

def extract_pdf(pdf_path, part_no):
    init_db()
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    count = 0
    pat = re.compile(r'(\d+)\s+([A-Z0-9/]+)\s*\nनाम[ः:]\s*([^\n]+)\s*\n(पिता का नाम|पति का नाम|माता का नाम|अन्य का नाम)[ः:]\s*([^\n]+)\s*\nमकान संख्या[ः:]\s*([^\n]*)\s*\nआयु[ः:]\s*(\d+)\s+लिंग[ः:]\s*([^\n]+)')
    
    reader = PdfReader(pdf_path)
    for page in reader.pages[2:]:
        raw = page.extract_text()
        if not raw: continue
        for m in pat.findall(unicodedata.normalize('NFC', raw)):
            sr, epic, nm, rel_t, rel_n, hs, age, gen = m
            is_del = 1 if "DELETED" in raw or "विलोपित" in raw else 0
            c.execute('''INSERT OR REPLACE INTO voters 
                (ward, part, sr_no, epic, name, rel_type, rel_name, house, age, gender, is_deleted, mobile, tag, notes, voted) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?, 
                COALESCE((SELECT mobile FROM voters WHERE part=? AND sr_no=?), ''),
                COALESCE((SELECT tag FROM voters WHERE part=? AND sr_no=?), 'सामान्य'),
                COALESCE((SELECT notes FROM voters WHERE part=? AND sr_no=?), ''),
                COALESCE((SELECT voted FROM voters WHERE part=? AND sr_no=?), 0))''', 
                ("12", str(part_no), int(sr), epic.strip(), clean_hindi(nm), rel_t.strip(), clean_hindi(rel_n), 
                 clean_hindi(hs) or "-", int(age), "स्त्री" if "स्त्री" in gen else "पुरुष", is_del,
                 str(part_no), int(sr), str(part_no), int(sr), str(part_no), int(sr), str(part_no), int(sr)))
            count += 1
    conn.commit(); conn.close()
    return count

# ----------------- UI STYLES & CARDS -----------------

TAG_COLORS = {"सामान्य": (0.5,0.5,0.5,1), "पक्का समर्थक": (0.1,0.7,0.2,1), "विरोधी": (0.8,0.1,0.1,1), "संदेहास्पद": (0.9,0.5,0.1,1), "प्रवासी": (0.2,0.5,0.8,1), "VIP": (0.8,0.2,0.6,1)}

class SlipLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'; self.padding = 10; self.spacing = 8
        with self.canvas.before:
            Color(1,1,1,1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_bg, size=self.update_bg)
    def update_bg(self, *args): self.bg.pos, self.bg.size = self.pos, self.size

class VoterCard(BoxLayout):
    def __init__(self, v, action_cb, **kwargs):
        super().__init__(**kwargs)
        self.v = v
        self.orientation = 'vertical'; self.size_hint_y = None; self.height = 160
        self.padding = [10,8,10,8]; self.spacing = 4

        with self.canvas.before:
            if v['is_deleted']: Color(1,0.9,0.9,1)
            elif v['voted']: Color(0.88,0.98,0.88,1)
            else: Color(0.96,0.97,0.99,1)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
        self.bind(pos=self.upd, size=self.upd)

        r1 = BoxLayout(size_hint_y=None, height=28)
        dm = "[color=ff0000](विलोपित)[/color] " if v['is_deleted'] else ""
        r1.add_widget(Label(text=f"[b]#{v['sr_no']}[/b] {dm}{v['name']}", markup=True, color=(0,0,0,1), size_hint_x=0.6, halign='left'))
        r1.add_widget(Label(text=v['epic'], font_size='12sp', color=(0.1,0.3,0.7,1), size_hint_x=0.4))
        self.add_widget(r1)

        r2 = BoxLayout(size_hint_y=None, height=24)
        r2.add_widget(Label(text=f"{v['rel_type'][:4]}: {v['rel_name']}", font_size='11sp', color=(0.3,0.3,0.3,1), size_hint_x=0.5))
        r2.add_widget(Label(text=f"म.सं: {v['house']} | आयु: {v['age']} {v['gender'][0]}", font_size='11sp', color=(0.3,0.3,0.3,1), size_hint_x=0.5))
        self.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=28, spacing=4)
        r3.add_widget(Label(text=f"[b]{v['tag']}[/b]", markup=True, font_size='11sp', color=TAG_COLORS.get(v['tag'], (0.5,0.5,0.5,1)), size_hint_x=0.35))
        
        b_fam = Button(text="🏠 परिवार", font_size='11sp', size_hint_x=0.25, background_color=(0.3,0.4,0.6,1))
        b_fam.bind(on_release=lambda x: action_cb('fam', v))
        b_edit = Button(text="✎ एडिट", font_size='11sp', size_hint_x=0.2, background_color=(0.8,0.5,0.1,1))
        b_edit.bind(on_release=lambda x: action_cb('edit', v))
        b_call = Button(text="📞 कॉल", font_size='11sp', size_hint_x=0.2, background_color=(0.1,0.6,0.2,1) if v['mobile'] else (0.6,0.6,0.6,1))
        
        r3.add_widget(b_fam); r3.add_widget(b_edit); r3.add_widget(b_call)
        self.add_widget(r3)

        r4 = BoxLayout(size_hint_y=None, height=36, spacing=6)
        b_slip = Button(text="🖨️ पर्ची/QR", font_size='12sp', background_color=(0.1,0.4,0.8,1))
        b_slip.bind(on_release=lambda x: action_cb('slip', v))
        v_txt = "वोट दिया ✓" if v['voted'] else "वोट बाकी"
        b_vote = Button(text=v_txt, font_size='12sp', background_color=(0.1,0.7,0.3,1) if v['voted'] else (0.6,0.6,0.6,1))
        b_vote.bind(on_release=lambda x: action_cb('vote', v))
        r4.add_widget(b_slip); r4.add_widget(b_vote)
        self.add_widget(r4)

    def upd(self, *args): self.bg.pos, self.bg.size = self.pos, self.size

# ----------------- MAIN APP & SIDEBAR -----------------

class ElectionWarRoomApp(App):
    def build(self):
        # Android Storage Permissions Boot Request
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
            except Exception as e:
                print("Permission request failed:", e)

        init_db()
        self.poster = os.path.join(App.get_running_app().user_data_dir if platform=='android' else ".", "my_photo.png")
        self.exp_dir = get_export_dir()
        
        self.root = BoxLayout(orientation='horizontal')
        self.sidebar_container = BoxLayout(size_hint_x=None, width=0)
        with self.sidebar_container.canvas.before:
            Color(0.08, 0.12, 0.22, 1)
            self.sb_bg = RoundedRectangle(pos=self.sidebar_container.pos, size=self.sidebar_container.size)
        self.sidebar_container.bind(pos=self.update_rects, size=self.update_rects)
        
        sb_scroll = ScrollView(size_hint=(1, 1))
        self.sidebar = BoxLayout(orientation='vertical', padding=[10,20,10,20], spacing=8, size_hint_y=None)
        self.sidebar.bind(minimum_height=self.sidebar.setter('height'))
        sb_scroll.add_widget(self.sidebar)
        self.sidebar_container.add_widget(sb_scroll)
        self.build_sidebar()
        self.root.add_widget(self.sidebar_container)

        self.main = BoxLayout(orientation='vertical', spacing=2)
        tb = BoxLayout(size_hint_y=None, height=55, padding=[6,4], spacing=8)
        with tb.canvas.before:
            Color(0.12, 0.23, 0.53, 1)
            self.tb_bg = RoundedRectangle(pos=tb.pos, size=tb.size)
        tb.bind(pos=self.update_rects, size=self.update_rects)
        
        b_menu = Button(text="☰ मेन्यू", size_hint_x=0.22, background_color=(0.2,0.3,0.6,1))
        b_menu.bind(on_release=self.toggle_sb)
        self.lbl_top = Label(text="इलेक्शन वॉर-रूम", bold=True, font_size='13sp')
        tb.add_widget(b_menu); tb.add_widget(self.lbl_top)
        self.main.add_widget(tb)

        s_box = BoxLayout(size_hint_y=None, height=44, padding=[6,2], spacing=4)
        self.t_search = TextInput(hint_text="नाम, मकान, फोन, EPIC...", multiline=False, font_size='13sp')
        self.t_search.bind(text=self.refresh)
        b_clr = Button(text="X", size_hint_x=0.15, background_color=(0.8,0.2,0.2,1))
        b_clr.bind(on_release=lambda x: setattr(self.t_search, 'text', ''))
        s_box.add_widget(self.t_search); s_box.add_widget(b_clr)
        self.main.add_widget(s_box)

        f1 = BoxLayout(size_hint_y=None, height=36, padding=[4,0], spacing=2)
        self.s_part = Spinner(text="भाग", values=("भाग", "1", "2", "3", "4"), size_hint_x=0.2)
        self.s_tag = Spinner(text="टैग", values=("टैग", "पक्का समर्थक", "विरोधी", "संदेहास्पद", "प्रवासी"), size_hint_x=0.3)
        self.s_vote = Spinner(text="मतदान", values=("मतदान", "वोट बाकी", "वोट दिया"), size_hint_x=0.3)
        self.s_age = Spinner(text="फ़िल्टर", values=("फ़िल्टर", "18-21 (युवा)", "80+ (वाहन)", "नंबर नहीं"), size_hint_x=0.2)
        
        for s in [self.s_part, self.s_tag, self.s_vote, self.s_age]:
            s.font_size = '11sp'; s.bind(text=self.refresh)
            f1.add_widget(s)
        self.main.add_widget(f1)

        self.scr = ScrollView()
        self.list_lyt = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=[6,4])
        self.list_lyt.bind(minimum_height=self.list_lyt.setter('height'))
        self.scr.add_widget(self.list_lyt)
        self.main.add_widget(self.scr)

        self.root.add_widget(self.main)
        self.refresh()
        return self.root

    def update_rects(self, *args):
        self.sb_bg.pos, self.sb_bg.size = self.sidebar_container.pos, self.sidebar_container.size
        self.tb_bg.pos, self.tb_bg.size = self.tb_bg.pos, self.tb_bg.size

    def toggle_sb(self, *args):
        self.sidebar_container.width = 260 if self.sidebar_container.width == 0 else 0

    def build_sidebar(self):
        self.sidebar.add_widget(Label(text="[b]30+ प्रो फीचर्स[/b]", markup=True, font_size='18sp', size_hint_y=None, height=40))
        btns = [
            ("📄 PDF से डेटा लोड करें", self.tool_pdf),
            ("📊 सघन मकान (High Density)", self.tool_density),
            ("⚠️ डुप्लीकेट वोटर स्कैनर", self.tool_dupe),
            ("📈 टर्नआउट/मार्जिन कैलकुलेटर", self.tool_margin),
            ("♿ 80+ व दिव्यांग वाहन लिस्ट", self.tool_80plus),
            ("📱 रिक्त मोबाइल हंटर", self.tool_missing_mob),
            ("🧮 EVM 17C मिलान डायरी", self.tool_evm),
            ("📓 घटना व टेंडर वोट डायरी", self.tool_incident),
            ("🖨️ एक्सेल/A-Z लिस्ट एक्सपोर्ट", self.tool_excel),
            ("🖼️ पर्ची के लिए पोस्टर सेट करें", self.tool_poster)
        ]
        
        for t, f in btns:
            b = Button(text=t, font_size='13sp', size_hint_y=None, height=45, background_color=(0.15,0.4,0.6,1))
            b.bind(on_release=f)
            self.sidebar.add_widget(b)
            
        b_close = Button(text="बंद करें", size_hint_y=None, height=45, background_color=(0.8,0.2,0.2,1))
        b_close.bind(on_release=self.toggle_sb)
        self.sidebar.add_widget(Label(size_hint_y=None, height=20))
        self.sidebar.add_widget(b_close)

    def refresh(self, *args):
        self.list_lyt.clear_widgets()
        conn = sqlite3.connect(get_db_path()); conn.row_factory = sqlite3.Row; c = conn.cursor()
        q, p = "SELECT * FROM voters WHERE 1=1", []

        if self.s_part.text != "भाग": q += " AND part = ?"; p.append(self.s_part.text)
        if self.s_tag.text != "टैग": q += " AND tag = ?"; p.append(self.s_tag.text)
        if self.s_vote.text == "वोट दिया": q += " AND voted=1"
        elif self.s_vote.text == "वोट बाकी": q += " AND voted=0"
        
        if self.s_age.text == "18-21 (युवा)": q += " AND age BETWEEN 18 AND 21"
        elif self.s_age.text == "60+ (वरिष्ठ)": q += " AND age >= 60"
        elif self.s_age.text == "80+ (वाहन)": q += " AND age >= 80"
        elif self.s_age.text == "नंबर नहीं": q += " AND mobile=''"

        st = self.t_search.text.strip()
        if st:
            q += " AND (name LIKE ? OR epic LIKE ? OR house LIKE ? OR mobile LIKE ?)"
            p.extend([f"%{st}%"]*4)

        q += " ORDER BY CAST(house AS INTEGER), sr_no ASC LIMIT 150"
        c.execute(q, p); rows = c.fetchall()

        c.execute("SELECT COUNT(*), SUM(voted) FROM voters")
        t, v = c.fetchone(); v = v or 0
        self.lbl_top.text = f"दिख रहे: {len(rows)} | वोट पड़े: {v}/{t} ({(v/t*100 if t else 0):.1f}%)"

        for r in rows: self.list_lyt.add_widget(VoterCard(dict(r), self.card_action))
        conn.close()

    def card_action(self, action, v):
        if action == 'vote':
            conn = sqlite3.connect(get_db_path())
            conn.execute("UPDATE voters SET voted=? WHERE id=?", (0 if v['voted'] else 1, v['id']))
            conn.commit(); conn.close(); self.refresh()
        elif action == 'fam':
            self.s_part.text, self.t_search.text = v['part'], v['house']
        elif action == 'edit': self.popup_edit(v)
        elif action == 'slip': self.popup_slip(v)

    def popup_edit(self, v):
        b = BoxLayout(orientation='vertical', spacing=8, padding=12)
        b.add_widget(Label(text=f"[b]{v['name']}[/b]", markup=True, size_hint_y=None, height=30))
        i_mob = TextInput(text=v['mobile'], hint_text="मोबाइल", input_filter='int', size_hint_y=None, height=45)
        s_tag = Spinner(text=v['tag'], values=list(TAG_COLORS.keys()), size_hint_y=None, height=45)
        i_note = TextInput(text=v['notes'], hint_text="टिप्पणी / ID Mismatch", size_hint_y=None, height=60)
        
        for w in [i_mob, s_tag, i_note]: b.add_widget(w)
        btn = Button(text="सेव करें", size_hint_y=None, height=45, background_color=(0.1,0.7,0.3,1))
        b.add_widget(btn); p = Popup(title="प्रोफाइल व टैग", content=b, size_hint=(0.85, 0.65))
        
        def save(_):
            conn = sqlite3.connect(get_db_path())
            conn.execute("UPDATE voters SET mobile=?, tag=?, notes=? WHERE id=?", (i_mob.text, s_tag.text, i_note.text, v['id']))
            conn.commit(); conn.close(); p.dismiss(); self.refresh()
        btn.bind(on_release=save); p.open()

    def popup_slip(self, v):
        b = BoxLayout(orientation='vertical', padding=10, spacing=8)
        self.slip_lyt = SlipLayout(size_hint_y=0.7)
        
        if os.path.exists(self.poster): self.slip_lyt.add_widget(Image(source=self.poster, size_hint_y=0.4, allow_stretch=True, keep_ratio=False))
        else: self.slip_lyt.add_widget(Label(text="[पोस्टर यहाँ दिखेगा]", color=(0.4,0.4,0.4,1), size_hint_y=0.4))
            
        qr = f"█▀▀▀▀▀█ ▄ █ █▀▀▀▀▀█\n█ ███ █ ▄ ▄ █ ███ █\n▀▀▀▀▀▀▀ ▀ ▀ ▀▀▀▀▀▀▀\n[ {v['epic']} ]"
        t = f"[b]वार्ड 12 | भाग: {v['part']}[/b]\n──────────────\nक्रम: {v['sr_no']}\nनाम: {v['name']}\n{v['rel_type']}: {v['rel_name']}\nमकान: {v['house']} | आयु: {v['age']} {v['gender']}\n──────────────\n[size=10sp]{qr}[/size]"
        self.slip_lyt.add_widget(Label(text=t, markup=True, color=(0,0,0,1), halign='center'))
        b.add_widget(self.slip_lyt)

        br = BoxLayout(size_hint_y=None, height=45, spacing=6)
        b_png = Button(text="इमेज सेव", background_color=(0.1,0.6,0.3,1))
        b_pdf = Button(text="PDF सेव", background_color=(0.8,0.3,0.2,1))
        b_png.bind(on_release=lambda x: self.exp_slip('png', v))
        b_pdf.bind(on_release=lambda x: self.exp_slip('pdf', v))
        br.add_widget(b_png); br.add_widget(b_pdf)
        b.add_widget(br)
        self.p_slip = Popup(title="डिजिटल पर्ची", content=b, size_hint=(0.95, 0.85))
        self.p_slip.open()

    def exp_slip(self, fmt, v):
        path = os.path.join(self.exp_dir, f"Slip_{v['epic']}.png")
        self.slip_lyt.export_to_png(path)
        def fin(dt):
            if fmt == 'pdf':
                pdf_p = path.replace('.png', '.pdf')
                try:
                    PILImage.open(path).convert('RGB').save(pdf_p)
                    os.remove(path)
                    self.msg("सफल", f"PDF सेव हुई:\n{pdf_p}")
                except Exception as e:
                    self.msg("त्रुटि", str(e))
            else: self.msg("सफल", f"इमेज सेव हुई:\n{path}")
            self.p_slip.dismiss()
        Clock.schedule_once(fin, 0.8)

    # ----------------- PRO TOOLS -----------------
    def tool_pdf(self, *args):
        self.toggle_sb(); b = BoxLayout(orientation='vertical', spacing=8, padding=10)
        sp = Spinner(text="1", values=("1","2","3","4"), size_hint_y=None, height=40)
        fc = FileChooserListView(path=".", filters=["*.pdf"])
        lbl = Label(text="PDF चुनें...", size_hint_y=None, height=30)
        btn = Button(text="एक्सट्रैक्ट करें", size_hint_y=None, height=45, background_color=(0.1,0.6,0.3,1))
        b.add_widget(sp); b.add_widget(fc); b.add_widget(lbl); b.add_widget(btn)
        p = Popup(title="PDF डेटा लोडर", content=b, size_hint=(0.9,0.8))
        def run(_):
            if not fc.selection: return
            lbl.text = "प्रोसेसिंग..."
            def w():
                c = parse_pdf_data(fc.selection[0], sp.text)
                lbl.text = f"सफल! {c} वोटर लोड हुए।"
                self.refresh()
            threading.Thread(target=w).start()
        btn.bind(on_release=run); p.open()

    def tool_density(self, *args):
        self.toggle_sb(); conn = sqlite3.connect(get_db_path()); c = conn.cursor()
        c.execute("SELECT house, COUNT(*) as c FROM voters GROUP BY house ORDER BY c DESC LIMIT 20")
        d = c.fetchall(); conn.close()
        self.msg("सघन मकान (टॉप 20)", "\n".join([f"मकान नं. {x[0]} ➔ {x[1]} वोट" for x in d]))

    def tool_dupe(self, *args):
        self.toggle_sb(); conn = sqlite3.connect(get_db_path()); c = conn.cursor()
        c.execute("SELECT name, rel_name, COUNT(*) as c FROM voters GROUP BY name, rel_name HAVING c>1")
        d = c.fetchall(); conn.close()
        self.msg("क्रॉस-पार्ट डुप्लीकेट", "\n".join([f"• {x[0]} ({x[1]}) - {x[2]} बार" for x in d]) if d else "कोई डुप्लीकेट नहीं।")

    def tool_margin(self, *args):
        self.toggle_sb(); conn = sqlite3.connect(get_db_path()); c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(voted) FROM voters")
        t, v = c.fetchone(); v = v or 0; tgt = int(t * 0.55)
        self.msg("जीत का लक्ष्य (55%)", f"कुल वोट: {t}\nलक्ष्य: {tgt}\nपड़े वोट: {v}\nदूरी: {tgt-v} वोट और चाहिए।")

    def tool_80plus(self, *args):
        self.toggle_sb(); self.s_age.text = "80+ (वाहन)"; self.refresh()

    def tool_missing_mob(self, *args):
        self.toggle_sb(); self.s_age.text = "नंबर नहीं"; self.refresh()

    def tool_evm(self, *args):
        self.toggle_sb(); b = BoxLayout(orientation='vertical', spacing=6, padding=10)
        cu = TextInput(hint_text="CU Number", size_hint_y=None, height=45)
        bu = TextInput(hint_text="BU Number", size_hint_y=None, height=45)
        vpt = TextInput(hint_text="VVPAT Number", size_hint_y=None, height=45)
        mk = TextInput(hint_text="मॉक पोल वोट्स", input_filter='int', size_hint_y=None, height=45)
        for w in [cu,bu,vpt,mk]: b.add_widget(w)
        btn = Button(text="सेव डायरी", size_hint_y=None, height=45, background_color=(0.1,0.6,0.3,1))
        b.add_widget(btn); p = Popup(title="EVM 17C लॉगर", content=b, size_hint=(0.85,0.6))
        def sv(_):
            conn = sqlite3.connect(get_db_path())
            conn.execute("INSERT INTO evm_diary (cu,bu,vvpat,mock_votes) VALUES (?,?,?,?)", (cu.text, bu.text, vpt.text, mk.text))
            conn.commit(); conn.close(); p.dismiss(); self.msg("सफल", "EVM डिटेल्स सेव हो गईं।")
        btn.bind(on_release=sv); p.open()

    def tool_incident(self, *args):
        self.toggle_sb(); b = BoxLayout(orientation='vertical', spacing=6, padding=10)
        dtl = TextInput(hint_text="घटना / टेंडर वोट का विवरण...", size_hint_y=None, height=100)
        b.add_widget(dtl)
        btn = Button(text="लॉग दर्ज करें", size_hint_y=None, height=45, background_color=(0.8,0.2,0.2,1))
        b.add_widget(btn); p = Popup(title="घटना डायरी", content=b, size_hint=(0.85,0.4))
        def sv(_):
            conn = sqlite3.connect(get_db_path())
            conn.execute("INSERT INTO incidents (time,detail) VALUES (?,?)", (str(datetime.now()), dtl.text))
            conn.commit(); conn.close(); p.dismiss(); self.msg("सफल", "घटना रिकॉर्ड हो गई।")
        btn.bind(on_release=sv); p.open()

    def tool_excel(self, *args):
        self.toggle_sb(); fp = os.path.join(self.exp_dir, f"Voters_A_to_Z_{int(time.time())}.xlsx")
        conn = sqlite3.connect(get_db_path())
        df = pd.read_sql_query("SELECT part, sr_no, epic, name, rel_name, house, mobile, tag FROM voters ORDER BY name ASC", conn)
        conn.close(); wb = Workbook(); ws = wb.active
        ws.append(['भाग', 'क्रम', 'EPIC', 'नाम', 'संबंधी', 'मकान', 'मोबाइल', 'टैग'])
        for r in df.values.tolist(): ws.append(r)
        wb.save(fp); self.msg("एक्सेल एक्सपोर्ट", f"A to Z सूची सेव हो गई:\n{fp}")

    def tool_poster(self, *args):
        self.toggle_sb(); b = BoxLayout(orientation='vertical', padding=10)
        fc = FileChooserListView(path=".", filters=["*.png", "*.jpg"])
        b.add_widget(fc)
        btn = Button(text="पोस्टर सेट करें", size_hint_y=None, height=45, background_color=(0.6,0.2,0.8,1))
        b.add_widget(btn); p = Popup(title="पोस्टर चुनें", content=b, size_hint=(0.9,0.8))
        def st(_):
            if fc.selection:
                shutil.copy(fc.selection[0], self.poster)
                p.dismiss(); self.msg("सफल", "पर्ची के लिए आपका पोस्टर सेट हो गया है।")
        btn.bind(on_release=st); p.open()

    def msg(self, title, text):
        b = BoxLayout(orientation='vertical', padding=10, spacing=10)
        b.add_widget(Label(text=text, markup=True, color=(0,0,0,1), halign='left', text_size=(Window.width*0.8, None)))
        btn = Button(text="OK", size_hint_y=None, height=40, background_color=(0.2,0.4,0.7,1))
        b.add_widget(btn); p = Popup(title=title, content=b, size_hint=(0.85,0.6))
        btn.bind(on_release=p.dismiss); p.open()

if __name__ == '__main__':
    ElectionWarRoomApp().run()
