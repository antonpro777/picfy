import os, re, secrets, smtplib, mimetypes, uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from flask import Flask, request, session, redirect, url_for, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from psycopg2.extras import RealDictCursor
import psycopg2
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")), MAX_CONTENT_LENGTH=20*1024*1024)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "uploads")

def db():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require", connect_timeout=10)

@contextmanager
def database():
    conn = db()
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def send_code(address, code):
    host,user,password = os.environ.get("SMTP_HOST"),os.environ.get("SMTP_USER"),os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or user
    if not all([host,user,password,sender]): raise RuntimeError("SMTP is not configured")
    msg=EmailMessage(); msg["Subject"]="Код подтверждения Pixel"; msg["From"]=sender; msg["To"]=address
    msg.set_content("Ваш код подтверждения Pixel: "+code+"\nКод действует 10 минут.")
    port=int(os.environ.get("SMTP_PORT","465"))
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=15) as s: s.login(user,password); s.send_message(msg)
    else:
        with smtplib.SMTP(host,port,timeout=15) as s: s.starttls(); s.login(user,password); s.send_message(msg)

def me(): return session.get("user")
def err(message,status=400): return jsonify(error=message),status

@app.get("/health")
def health():
    try:
        with database() as c, c.cursor() as q: q.execute("select 1")
        return jsonify(status="ok",database="ok",app="Pixel")
    except Exception:
        app.logger.exception("health"); return jsonify(status="unavailable"),503

@app.get("/")
def home():
    if not me(): return redirect(url_for("login"))
    with database() as c,c.cursor() as q:
        q.execute("""SELECT p.id,p.author_id,p.caption,p.media_url,p.media_type,p.created_at,
          u.username,u.name,u.avatar_url,
          (SELECT count(*) FROM pixel_likes l WHERE l.post_id=p.id) likes_count,
          (SELECT count(*) FROM pixel_comments x WHERE x.post_id=p.id) comments_count,
          EXISTS(SELECT 1 FROM pixel_likes l WHERE l.post_id=p.id AND l.user_id=%s) liked
          FROM pixel_posts p JOIN users u ON u.id=p.author_id
          WHERE p.author_id=%s OR p.author_id IN (SELECT following_id FROM pixel_follows WHERE follower_id=%s)
          ORDER BY p.created_at DESC LIMIT 60""",(me()["id"],me()["id"],me()["id"]))
        posts=q.fetchall()
        q.execute("SELECT count(*) n FROM pixel_follows WHERE following_id=%s",(me()["id"],)); followers=q.fetchone()["n"]
        q.execute("SELECT count(*) n FROM pixel_follows WHERE follower_id=%s",(me()["id"],)); following=q.fetchone()["n"]
    return render_template("pixel.html",user=me(),posts=posts,followers=followers,following=following)

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="GET": return render_template("pixel_auth.html",mode="register",error=None)
    name=request.form.get("name","").strip()[:60]; username=request.form.get("username","").strip().lower()
    email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
    if not re.fullmatch(r"[a-z0-9_]{3,24}",username): return render_template("pixel_auth.html",mode="register",error="Юзернейм: 3–24 символа, латиница, цифры и _")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email) or len(password)<10:
        return render_template("pixel_auth.html",mode="register",error="Проверь email. Пароль — минимум 10 символов.")
    code=f"{secrets.randbelow(1000000):06d}"
    try:
        with database() as c, c.cursor() as q:
            q.execute("SELECT 1 FROM users WHERE username=%s OR lower(email)=lower(%s)",(username,email))
            if q.fetchone(): return render_template("pixel_auth.html",mode="register",error="Этот username или email уже занят.")
            q.execute("INSERT INTO users(username,name,password_hash,email,email_verified) VALUES(%s,%s,%s,%s,false) RETURNING id",
                      (username,name,generate_password_hash(password),email)); uid=q.fetchone()["id"]
            q.execute("INSERT INTO pixel_email_codes(user_id,email,code_hash,expires_at) VALUES(%s,%s,%s,%s)",
                      (uid,email,generate_password_hash(code),datetime.now(timezone.utc)+timedelta(minutes=10)))
        send_code(email,code); session["pending_user_id"]=uid; return redirect(url_for("verify_email"))
    except Exception:
        app.logger.exception("registration"); return render_template("pixel_auth.html",mode="register",error="Не удалось отправить письмо. Проверь SMTP-настройки.")

@app.route("/verify",methods=["GET","POST"])
def verify_email():
    uid=session.get("pending_user_id")
    if not uid: return redirect(url_for("register"))
    if request.method=="POST":
        with database() as c, c.cursor() as q:
            q.execute("SELECT id,code_hash FROM pixel_email_codes WHERE user_id=%s AND expires_at>now() ORDER BY created_at DESC LIMIT 1",(uid,))
            row=q.fetchone()
            if not row or not check_password_hash(row["code_hash"],request.form.get("code","").strip()):
                return render_template("pixel_auth.html",mode="verify",error="Неверный или просроченный код.")
            q.execute("UPDATE users SET email_verified=true WHERE id=%s",(uid,))
            q.execute("DELETE FROM pixel_email_codes WHERE user_id=%s",(uid,))
            q.execute("SELECT id,username,name,avatar_url FROM users WHERE id=%s",(uid,)); user=q.fetchone()
        session.pop("pending_user_id",None); session["user"]=dict(user); return redirect(url_for("home"))
    return render_template("pixel_auth.html",mode="verify",error=None)

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="GET": return render_template("pixel_auth.html",mode="login",error=None)
    identity=request.form.get("identity","").strip().lower()
    with database() as c, c.cursor() as q:
        q.execute("SELECT id,username,name,password_hash,email_verified,avatar_url FROM users WHERE lower(username)=%s OR lower(email)=%s",(identity,identity)); u=q.fetchone()
    if not u or not u["password_hash"] or not check_password_hash(u["password_hash"],request.form.get("password","")):
        return render_template("pixel_auth.html",mode="login",error="Неверный логин или пароль.")
    if not u["email_verified"]: session["pending_user_id"]=u["id"]; return redirect(url_for("verify_email"))
    session["user"]={k:u[k] for k in ("id","username","name","avatar_url")}; return redirect(url_for("home"))

@app.get("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.get("/api/search")
def search():
    if not me(): return err("Нужно войти",401)
    term=request.args.get("q","").strip().lstrip("@")[:40]
    if len(term)<2: return jsonify(users=[])
    with database() as c, c.cursor() as q:
        q.execute("SELECT id,username,name,avatar_url FROM users WHERE username ILIKE %s AND id<>%s AND email_verified=true ORDER BY username LIMIT 15",(term+"%",me()["id"]))
        return jsonify(users=q.fetchall())

@app.get("/profile/<username>")
def profile(username):
    if not me(): return redirect(url_for("login"))
    with database() as c, c.cursor() as q:
        q.execute("SELECT id,username,name,bio,avatar_url FROM users WHERE username=%s AND email_verified=true",(username.lower(),)); u=q.fetchone()
        if not u: return "Профиль не найден",404
        q.execute("SELECT count(*) n FROM pixel_follows WHERE following_id=%s",(u["id"],)); followers=q.fetchone()["n"]
        q.execute("SELECT count(*) n FROM pixel_follows WHERE follower_id=%s",(u["id"],)); following=q.fetchone()["n"]
        q.execute("SELECT EXISTS(SELECT 1 FROM pixel_follows WHERE follower_id=%s AND following_id=%s) yes",(me()["id"],u["id"])); is_following=q.fetchone()["yes"]
        q.execute("""SELECT p.*,u.username,u.name,u.avatar_url,
          (SELECT count(*) FROM pixel_likes l WHERE l.post_id=p.id) likes_count,
          (SELECT count(*) FROM pixel_comments x WHERE x.post_id=p.id) comments_count
          FROM pixel_posts p JOIN users u ON u.id=p.author_id WHERE p.author_id=%s ORDER BY p.created_at DESC""",(u["id"],)); posts=q.fetchall()
    return render_template("pixel.html",user=me(),posts=posts,followers=followers,following=following,profile_user=u,is_following=is_following)

@app.post("/api/follow/<int:target>")
def follow(target):
    if not me(): return err("Нужно войти",401)
    if target==me()["id"]: return err("Нельзя подписаться на себя")
    with database() as c, c.cursor() as q:
        q.execute("DELETE FROM pixel_follows WHERE follower_id=%s AND following_id=%s RETURNING id",(me()["id"],target)); removed=q.fetchone()
        if not removed: q.execute("INSERT INTO pixel_follows(follower_id,following_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(me()["id"],target))
    return jsonify(following=not bool(removed))

@app.post("/api/posts")
def create_post():
    if not me(): return err("Нужно войти",401)
    d=request.get_json(silent=True) or {}; caption=str(d.get("caption","")).strip()[:3000]
    media_url=str(d.get("media_url","")).strip()[:1000]; kind=d.get("media_type","text")
    if kind not in ("text","image","video","short"): return err("Неверный тип публикации")
    if not caption and not media_url: return err("Добавь текст или медиа")
    with database() as c, c.cursor() as q:
        q.execute("INSERT INTO pixel_posts(author_id,caption,media_url,media_type) VALUES(%s,%s,%s,%s) RETURNING id",(me()["id"],caption,media_url,kind)); pid=q.fetchone()["id"]
    return jsonify(ok=True,post_id=pid)

@app.post("/api/posts/<int:pid>/like")
def like(pid):
    if not me(): return err("Нужно войти",401)
    with database() as c, c.cursor() as q:
        q.execute("DELETE FROM pixel_likes WHERE post_id=%s AND user_id=%s RETURNING id",(pid,me()["id"])); removed=q.fetchone()
        if not removed: q.execute("INSERT INTO pixel_likes(post_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(pid,me()["id"]))
        q.execute("SELECT count(*) n FROM pixel_likes WHERE post_id=%s",(pid,)); count=q.fetchone()["n"]
    return jsonify(liked=not bool(removed),likes=count)

@app.route("/api/posts/<int:pid>/comments",methods=["GET","POST"])
def comments(pid):
    if not me(): return err("Нужно войти",401)
    with database() as c, c.cursor() as q:
        if request.method=="POST":
            body=str((request.get_json(silent=True) or {}).get("body","")).strip()[:1500]
            if not body: return err("Пустой комментарий")
            q.execute("INSERT INTO pixel_comments(post_id,user_id,body) VALUES(%s,%s,%s)",(pid,me()["id"],body))
        q.execute("SELECT x.id,x.body,x.created_at,u.username FROM pixel_comments x JOIN users u ON u.id=x.user_id WHERE x.post_id=%s ORDER BY x.created_at LIMIT 100",(pid,))
        return jsonify(comments=q.fetchall())

@app.get("/api/chat/users")
def chat_users():
    if not me(): return err("Нужно войти",401)
    term=request.args.get("q","").strip().lstrip("@")[:40]
    with database() as c, c.cursor() as q:
        q.execute("SELECT id,username,name,avatar_url FROM users WHERE email_verified=true AND id<>%s AND (%s='' OR username ILIKE %s) ORDER BY username LIMIT 30",(me()["id"],term,term+"%"))
        return jsonify(users=q.fetchall())

@app.get("/api/chat/<int:other>")
def chat_messages(other):
    if not me(): return err("Нужно войти",401)
    with database() as c, c.cursor() as q:
        q.execute("""SELECT id,sender_id,recipient_id,content,file_url,file_type,created_at FROM messages
          WHERE (sender_id=%s AND recipient_id=%s) OR (sender_id=%s AND recipient_id=%s) ORDER BY id DESC LIMIT 100""",(me()["id"],other,other,me()["id"]))
        return jsonify(messages=list(reversed(q.fetchall())))

@app.post("/api/chat/send")
def chat_send():
    if not me(): return err("Нужно войти",401)
    d=request.get_json(silent=True) or {}; recipient=d.get("recipient_id")
    content=str(d.get("content","")).strip()[:4000]; file_url=str(d.get("file_url","")).strip()[:1200]
    file_type=d.get("file_type","text")
    if not recipient or (not content and not file_url): return err("Пустое сообщение")
    if file_type not in ("text","audio","image","video","sticker"): return err("Неверный тип вложения")
    with database() as c, c.cursor() as q:
        q.execute("INSERT INTO messages(sender_id,recipient_id,content,file_url,file_type) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                  (me()["id"],int(recipient),content,file_url,file_type)); mid=q.fetchone()["id"]
    return jsonify(ok=True,id=mid)

@app.post("/api/upload-ticket")
def upload_ticket():
    if not me(): return err("Нужно войти",401)
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY: return err("Не настроено хранилище",503)
    d=request.get_json(silent=True) or {}; filename=secure_filename(str(d.get("filename","file")))[:100]
    mime=str(d.get("content_type","application/octet-stream"))[:120]
    if not mime.startswith(("image/","video/","audio/")): return err("Неверный тип файла")
    from supabase import create_client
    ext=os.path.splitext(filename)[1][:12]; path=f"pixel/{me()['id']}/{uuid.uuid4().hex}{ext}"
    try:
        client=create_client(SUPABASE_URL,SUPABASE_SERVICE_ROLE_KEY)
        signed=client.storage.from_(BUCKET).create_signed_upload_url(path)
        token=signed.get("token") or signed.get("data",{}).get("token")
        if not token: raise RuntimeError("Storage did not return signed upload token")
        url=client.storage.from_(BUCKET).get_public_url(path)
        kind="audio" if mime.startswith("audio/") else ("video" if mime.startswith("video/") else "image")
        return jsonify(path=path,token=token,url=url,media_type=kind,mime=mime,endpoint=SUPABASE_URL.replace(".supabase.co",".storage.supabase.co")+"/storage/v1/upload/resumable",bucket=BUCKET)
    except Exception:
        app.logger.exception("upload ticket"); return err("Не удалось подготовить загрузку в Storage.",500)

@app.errorhandler(413)
def too_large(_): return err("Файл слишком большой (лимит 20 МБ).",413)

if __name__=="__main__": app.run(debug=True)
