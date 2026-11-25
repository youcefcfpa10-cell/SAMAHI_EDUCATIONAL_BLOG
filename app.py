# -*- coding: utf-8 -*-
"""سماحي يوسف – مدونتي التعليمية | Flask + لوحة تحكم إدارية"""
from __future__ import annotations
import json, os, re, secrets, sqlite3, hashlib, hmac, html
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort

BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / "content"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DATA_DIR = BASE_DIR / "instance"
DB_PATH = DATA_DIR / "blog.db"
for folder in (CONTENT_DIR, UPLOAD_DIR, DATA_DIR):
    folder.mkdir(parents=True, exist_ok=True)

def persistent_secret():
    configured = os.environ.get("SECRET_KEY")
    if configured:
        return configured
    secret_path = DATA_DIR / "secret_key"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    secret_path.write_text(value, encoding="utf-8")
    try: secret_path.chmod(0o600)
    except OSError: pass
    return value

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=persistent_secret(),
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)
CONTENT_FILES = {"lessons":"lessons.json","articles":"articles.json","files":"files.json","courses":"courses.json"}
CONTENT_LABELS = {"lessons":"الدروس","articles":"المقالات","files":"الملفات","courses":"الدورات"}
ALLOWED_UPLOADS = {"pdf","doc","docx","xls","xlsx","png","jpg","jpeg","gif","webp"}
ALLOWED_IMAGES = {"png","jpg","jpeg","gif","webp"}

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return salt.hex() + "$" + digest.hex()

def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310000)
        return hmac.compare_digest(test.hex(), digest_hex)
    except Exception:
        return False

def now_local():
    return datetime.now().astimezone().replace(tzinfo=None)

def parse_datetime(value):
    if not value: return None
    try: return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError: return None

def slugify(value):
    value = re.sub(r"[^\w\-]+", "-", value.strip(), flags=re.UNICODE).strip("-")
    return (value[:90] or secrets.token_hex(5)).lower()

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            must_change INTEGER NOT NULL DEFAULT 1)""")
        con.execute("""CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT, section TEXT NOT NULL, title TEXT NOT NULL,
            slug TEXT NOT NULL, description TEXT DEFAULT '', content TEXT DEFAULT '',
            category TEXT DEFAULT '', image TEXT DEFAULT '', download TEXT DEFAULT '',
            attachments TEXT DEFAULT '[]', author TEXT DEFAULT 'سماحي يوسف',
            created_at TEXT NOT NULL, publish_at TEXT, status TEXT NOT NULL DEFAULT 'draft',
            UNIQUE(section, slug))""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_content_section_status ON content(section,status)")
        if not con.execute("SELECT id FROM users LIMIT 1").fetchone():
            username = os.environ.get("ADMIN_USERNAME", "admin")
            password = os.environ.get("ADMIN_PASSWORD", "%D#wEqvFhNJF7_n77wCfsr")
            con.execute("INSERT INTO users(username,password_hash,must_change) VALUES(?,?,1)",
                        (username, hash_password(password)))
        # استيراد المحتوى القديم مرة واحدة دون المساس بملفات JSON.
        for section, filename in CONTENT_FILES.items():
            if con.execute("SELECT COUNT(*) FROM content WHERE section=?", (section,)).fetchone()[0]:
                continue
            path = CONTENT_DIR / filename
            try:
                old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            except Exception:
                old = []
            if isinstance(old, list):
                for item in old:
                    if not isinstance(item, dict) or not item.get("title"): continue
                    slug = slugify(str(item.get("slug") or item["title"]))
                    con.execute("""INSERT OR IGNORE INTO content
                    (section,title,slug,description,content,category,image,download,attachments,author,created_at,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (section, str(item["title"]), slug, str(item.get("description","")),
                     str(item.get("content",item.get("body",""))), str(item.get("category","")),
                     str(item.get("image","")), str(item.get("download","")),
                     json.dumps(item.get("attachments",[]),ensure_ascii=False),
                     str(item.get("author","سماحي يوسف")), str(item.get("date") or now_local().isoformat(timespec="minutes")),
                     "published"))

init_db()

def publish_due():
    with db() as con:
        con.execute("UPDATE content SET status='published' WHERE status='scheduled' AND publish_at IS NOT NULL AND publish_at<=?",
                    (now_local().isoformat(timespec="minutes"),))

def content_rows(section=None, include_unpublished=False):
    publish_due()
    with db() as con:
        sql = "SELECT * FROM content"
        clauses, args = [], []
        if section: clauses.append("section=?"); args.append(section)
        if not include_unpublished: clauses.append("status='published'")
        if clauses: sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY COALESCE(publish_at,created_at) DESC, id DESC"
        rows = con.execute(sql,args).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        try: item["attachments"]=json.loads(item.get("attachments") or "[]")
        except Exception: item["attachments"]=[]
        item["date"]=(item.get("publish_at") or item.get("created_at") or "")[:10]
        result.append(item)
    return result

def find_content(section, slug):
    for item in content_rows(section):
        if item["slug"] == slug: return item
    abort(404)

@app.before_request
def ensure_db_and_publish():
    publish_due()

@app.context_processor
def inject_global_data():
    return {"site_name":"سماحي يوسف – مدونتي التعليمية",
            "site_description":"فضاء تعليمي للطلبة والأساتذة في قطاع التكوين المهني"}

def csrf_token():
    if "_csrf" not in session: session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]
app.jinja_env.globals["csrf_token"] = csrf_token

def check_csrf():
    token = request.form.get("_csrf","")
    if not token or not hmac.compare_digest(token, session.get("_csrf","")):
        abort(400, description="انتهت صلاحية النموذج. أعد تحميل الصفحة وحاول مجدداً.")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def home():
    return render_template("home.html",
        latest_lessons=content_rows("lessons")[:6],
        latest_articles=content_rows("articles")[:6],
        latest_files=content_rows("files")[:6],
        latest_courses=content_rows("courses")[:4])

def listing(section, title, description):
    return render_template("listing.html", title=title, description=description,
                           items=content_rows(section), section=section)
@app.route("/lessons/")
def lessons(): return listing("lessons","الدروس التعليمية","دروس وموارد تعليمية في مختلف تخصصات التكوين المهني")
@app.route("/articles/")
def articles(): return listing("articles","المقالات التعليمية","مقالات تربوية وتقنية ومهنية")
@app.route("/files/")
def files(): return listing("files","المكتبة والملفات","ملفات وموارد قابلة للتحميل والاستفادة")
@app.route("/courses/")
def courses(): return listing("courses","الدورات التدريبية","دورات تعليمية مجانية ومدفوعة")

def detail(section, slug, title, kind):
    return render_template("detail.html", item=find_content(section,slug), section=section,
                           section_title=title, detail_type=kind)
@app.route("/lessons/<slug>/")
def lesson_detail(slug): return detail("lessons",slug,"الدروس التعليمية","درس تعليمي")
@app.route("/articles/<slug>/")
def article_detail(slug): return detail("articles",slug,"المقالات التعليمية","مقال")
@app.route("/files/<slug>/")
def file_detail(slug): return detail("files",slug,"المكتبة والملفات","ملف تعليمي")
@app.route("/courses/<slug>/")
def course_detail(slug): return detail("courses",slug,"الدورات التدريبية","دورة تدريبية")

@app.route("/about/")
def about(): return render_template("about.html")
@app.route("/contact/")
def contact(): return render_template("contact.html")
@app.route("/privacy/")
def privacy(): return render_template("privacy.html")
@app.route("/terms/")
def terms(): return render_template("terms.html")

@app.route("/admin/login/", methods=["GET","POST"])
def admin_login():
    if session.get("admin_id"): return redirect(url_for("admin_dashboard"))
    if request.method=="POST":
        check_csrf()
        username=request.form.get("username","").strip()
        password=request.form.get("password","")
        with db() as con: user=con.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
        if user and verify_password(password,user["password_hash"]):
            session.clear(); session["admin_id"]=user["id"]; session["admin_username"]=user["username"]; csrf_token()
            if user["must_change"]: return redirect(url_for("admin_password"))
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة.","error")
    return render_template("admin/login.html")

@app.route("/admin/logout/", methods=["POST"])
@login_required
def admin_logout():
    check_csrf(); session.clear(); flash("تم تسجيل الخروج.","success")
    return redirect(url_for("admin_login"))

@app.route("/admin/")
@login_required
def admin_dashboard():
    publish_due()
    with db() as con:
        counts={s:con.execute("SELECT COUNT(*) FROM content WHERE section=?",(s,)).fetchone()[0] for s in CONTENT_FILES}
        statuses={s:con.execute("SELECT COUNT(*) FROM content WHERE status=?",(s,)).fetchone()[0] for s in ("draft","scheduled","published")}
        rows=con.execute("SELECT * FROM content ORDER BY id DESC LIMIT 30").fetchall()
    return render_template("admin/dashboard.html", counts=counts, statuses=statuses, items=[dict(r) for r in rows], labels=CONTENT_LABELS)

def save_upload(field, image_only=False):
    f=request.files.get(field)
    if not f or not f.filename: return ""
    ext=Path(f.filename).suffix.lower().lstrip(".")
    allowed=ALLOWED_IMAGES if image_only else ALLOWED_UPLOADS
    if ext not in allowed: raise ValueError("نوع الملف غير مسموح به.")
    name=secure_filename(Path(f.filename).stem)[:45] or "upload"
    filename=f"{secrets.token_hex(8)}_{name}.{ext}"
    f.save(UPLOAD_DIR/filename)
    return "/static/uploads/"+filename

def safe_html(value):
    # السماح بعناصر التنسيق الأساسية فقط؛ إزالة السكربتات والخصائص الخطرة.
    allowed_tags={"p","br","strong","b","em","i","u","ul","ol","li","h2","h3","h4","blockquote","a","img","hr"}
    allowed_attrs={"a":{"href","title","target","rel"},"img":{"src","alt","title","width"}}
    try:
        import bleach
        return bleach.clean(value or "", tags=allowed_tags, attributes=allowed_attrs,
                            protocols={"http","https","mailto"}, strip=True)
    except ImportError:
        # وضع آمن احتياطي: المحتوى النصي فقط عند عدم تثبيت bleach.
        return "<p>"+html.escape(re.sub(r"<[^>]*>"," ",value or ""))+"</p>"

@app.route("/admin/content/new/", methods=["GET","POST"])
@app.route("/admin/content/<int:item_id>/edit/", methods=["GET","POST"])
@login_required
def admin_editor(item_id=None):
    item=None
    if item_id:
        with db() as con: row=con.execute("SELECT * FROM content WHERE id=?",(item_id,)).fetchone()
        if not row: abort(404)
        item=dict(row)
    if request.method=="POST":
        check_csrf()
        section=request.form.get("section","")
        if section not in CONTENT_FILES: abort(400)
        title=request.form.get("title","").strip()
        if not title:
            flash("يرجى إدخال عنوان المحتوى.","error")
            return redirect(request.url)
        slug=slugify(request.form.get("slug","").strip() or title)
        description=request.form.get("description","").strip()
        body=safe_html(request.form.get("content",""))
        category=request.form.get("category","").strip()
        status=request.form.get("status","draft")
        if status not in {"draft","published","scheduled"}: status="draft"
        publish_at=request.form.get("publish_at","").strip() or None
        if status=="scheduled" and (not publish_at or not parse_datetime(publish_at)):
            flash("حدد تاريخاً ووقتاً صحيحين للجدولة.","error"); return redirect(request.url)
        if status=="published": publish_at=now_local().isoformat(timespec="minutes")
        image=request.form.get("existing_image","")
        download=request.form.get("existing_download","")
        try:
            uploaded_image=save_upload("image",True)
            uploaded_file=save_upload("download",False)
            if uploaded_image: image=uploaded_image
            if uploaded_file: download=uploaded_file
            if image and not image.startswith("/static/"): image=""
            if download and not download.startswith("/static/"): download=""
            created=(item or {}).get("created_at") or now_local().isoformat(timespec="minutes")
            author=request.form.get("author","سماحي يوسف").strip() or "سماحي يوسف"
            with db() as con:
                if item_id:
                    con.execute("""UPDATE content SET section=?,title=?,slug=?,description=?,content=?,category=?,image=?,download=?,author=?,publish_at=?,status=? WHERE id=?""",
                    (section,title,slug,description,body,category,image,download,author, publish_at,status,item_id))
                else:
                    con.execute("""INSERT INTO content(section,title,slug,description,content,category,image,download,author,created_at,publish_at,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (section,title,slug,description,body,category,image,download,author,created,publish_at,status))
            flash("تم حفظ المحتوى بنجاح.","success")
            return redirect(url_for("admin_dashboard"))
        except (ValueError, sqlite3.IntegrityError) as exc:
            flash("تعذر الحفظ: "+str(exc),"error")
    return render_template("admin/editor.html", item=item, labels=CONTENT_LABELS)

@app.route("/admin/content/<int:item_id>/delete/", methods=["POST"])
@login_required
def admin_delete(item_id):
    check_csrf()
    with db() as con: con.execute("DELETE FROM content WHERE id=?",(item_id,))
    flash("تم حذف المحتوى.","success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/password/", methods=["GET","POST"])
@login_required
def admin_password():
    if request.method=="POST":
        check_csrf()
        old=request.form.get("old_password","")
        new=request.form.get("new_password","")
        confirm=request.form.get("confirm_password","")
        with db() as con: user=con.execute("SELECT * FROM users WHERE id=?",(session["admin_id"],)).fetchone()
        if not user or not verify_password(old,user["password_hash"]): flash("كلمة المرور الحالية غير صحيحة.","error")
        elif len(new)<12 or not re.search(r"[A-Z]",new) or not re.search(r"[a-z]",new) or not re.search(r"\d",new):
            flash("اجعل كلمة المرور 12 رمزاً على الأقل، وتضم حرفاً كبيراً وصغيراً ورقماً.","error")
        elif new!=confirm: flash("تأكيد كلمة المرور غير مطابق.","error")
        else:
            with db() as con: con.execute("UPDATE users SET password_hash=?,must_change=0 WHERE id=?",(hash_password(new),session["admin_id"]))
            flash("تم تغيير كلمة المرور بنجاح.","success")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin/password.html")

@app.errorhandler(404)
def page_not_found(error): return render_template("404.html"),404

@app.errorhandler(413)
def too_large(error): return "حجم الملف أكبر من الحد المسموح (32 ميغابايت).",413

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5000")),
            debug=os.environ.get("FLASK_DEBUG","0")=="1")
