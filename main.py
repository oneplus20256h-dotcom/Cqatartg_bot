# main.py
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, Set, List
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===================== التوكن =====================
BOT_TOKEN = "8246063932:AAEBmYOA9K570eskmXYMa35pSZaNfb6uB9M"

# ===================== Logging =====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ===================== رابط وزارة التربية والتعليم =====================
MOEHE_OFFICIAL_URL = "https://www.edu.gov.qa/En/Pages/HomePage.aspx"

# ===================== Super Admin =====================
SUPER_ADMIN_USERNAME = "QHGPB"  # بدون @
SUPER_ADMIN_ID = 8136678328

# ===================== رابط قروب السجل (للعرض فقط) =====================
LOG_GROUP_INVITE = "https://t.me/+cTN73kcvpqszZTJk"

# ===================== ملفات التخزين =====================
DATA_DIR = Path(".")
USERS_FILE = DATA_DIR / "users.json"
GROUPS_FILE = DATA_DIR / "groups.json"
MODS_FILE = DATA_DIR / "mods.json"
VERIFIED_FILE = DATA_DIR / "verified_users.json"
ATTEMPTS_FILE = DATA_DIR / "attempts.json"
CONFIG_FILE = DATA_DIR / "config.json"


# ===================== أدوات JSON =====================
def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ===================== إعدادات عامة =====================
def load_config() -> Dict[str, Any]:
    data = _load_json(CONFIG_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("log_group_chat_id", None)  # يتم تعيينه عبر /setlog داخل القروب
    data.setdefault("log_group_invite", LOG_GROUP_INVITE)
    return data


def save_config(cfg: Dict[str, Any]) -> None:
    _save_json(CONFIG_FILE, cfg)


CONFIG: Dict[str, Any] = load_config()


def get_log_group_chat_id() -> Optional[int]:
    v = CONFIG.get("log_group_chat_id")
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.lstrip("-").isdigit():
        return int(v)
    return None


# ===================== مستخدمين (للإعلان والإحصاءات) =====================
def load_users() -> Set[int]:
    data = _load_json(USERS_FILE, [])
    try:
        return set(int(x) for x in data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_users(users: Set[int]) -> None:
    _save_json(USERS_FILE, sorted(list(users)))


KNOWN_USERS: Set[int] = load_users()


def remember_user(update: Update) -> None:
    chat = update.effective_chat
    if not chat:
        return
    KNOWN_USERS.add(int(chat.id))
    save_users(KNOWN_USERS)


# ===================== مشرفين =====================
def load_mods() -> Set[int]:
    data = _load_json(MODS_FILE, [])
    try:
        return set(int(x) for x in data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_mods(mods: Set[int]) -> None:
    _save_json(MODS_FILE, sorted(list(mods)))


MODS: Set[int] = load_mods()


def is_super_admin(update: Update) -> bool:
    u = update.effective_user
    if not u:
        return False
    return (u.id == SUPER_ADMIN_ID) or ((u.username or "").lower() == SUPER_ADMIN_USERNAME.lower())


def is_staff(update: Update) -> bool:
    u = update.effective_user
    if not u:
        return False
    return is_super_admin(update) or (int(u.id) in MODS)


# ===================== سجل المحاولات =====================
def load_attempts() -> List[Dict[str, Any]]:
    data = _load_json(ATTEMPTS_FILE, [])
    return data if isinstance(data, list) else []


def save_attempts(items: List[Dict[str, Any]]) -> None:
    _save_json(ATTEMPTS_FILE, items)


ATTEMPTS: List[Dict[str, Any]] = load_attempts()


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_phone(phone: str) -> str:
    return "".join(re.findall(r"\d+", phone or ""))


def is_qatari_phone(phone: str) -> bool:
    d = normalize_phone(phone)
    return d.startswith("974") and len(d) == 11


def mask_phone_digits(phone_digits: str) -> str:
    d = normalize_phone(phone_digits)
    if len(d) <= 4:
        return d
    return ("*" * (len(d) - 4)) + d[-4:]


def get_user_brief(update: Update) -> Dict[str, Any]:
    user = update.effective_user
    chat = update.effective_chat
    return {
        "name": (user.full_name or "").strip() if user else "",
        "username": f"@{user.username}" if user and user.username else "",
        "user_id": int(user.id) if user else None,
        "chat_id": int(chat.id) if chat else None,
    }


def user_brief_text(update: Update) -> str:
    b = get_user_brief(update)
    n = b.get("name") or "(بدون اسم)"
    u = b.get("username") or "(بدون معرف)"
    cid = b.get("chat_id")
    return f"• الاسم: {n}\n• المعرف: {u}\n• chat_id: <code>{cid}</code>"


async def send_to_log_group(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    gid = get_log_group_chat_id()
    if not gid:
        return
    try:
        await context.bot.send_message(chat_id=gid, text=text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


def add_attempt(update: Update, status: str, phone_digits: str = "", reason: str = "") -> Dict[str, Any]:
    b = get_user_brief(update)
    item = {
        "ts": now_ts(),
        "status": status,  # pre_start, pre_begin, accepted, rejected_non_qatari, rejected_not_self
        "reason": reason,
        "name": b.get("name", ""),
        "username": b.get("username", ""),
        "user_id": b.get("user_id"),
        "chat_id": b.get("chat_id"),
        "phone": normalize_phone(phone_digits),
        "phone_masked": mask_phone_digits(phone_digits) if phone_digits else "",
    }
    ATTEMPTS.append(item)
    # حافظ على آخر 3000 سجل
    if len(ATTEMPTS) > 3000:
        del ATTEMPTS[: len(ATTEMPTS) - 3000]
    save_attempts(ATTEMPTS)
    return item


# ===================== التحقق (إجبار مشاركة جهة الاتصال + رقم قطري) =====================
def load_verified() -> Dict[str, Any]:
    data = _load_json(VERIFIED_FILE, {})
    return data if isinstance(data, dict) else {}


def save_verified(data: Dict[str, Any]) -> None:
    _save_json(VERIFIED_FILE, data)


# chat_id -> {"phone":"974xxxxxxxx","ts":"...","name":"...","username":"..."}
VERIFIED_USERS: Dict[str, Any] = load_verified()


def _get_verified_record(chat_id: int) -> Optional[Dict[str, str]]:
    rec = VERIFIED_USERS.get(str(chat_id))
    if rec is None:
        return None
    if isinstance(rec, str):
        return {"phone": rec, "ts": "", "name": "", "username": ""}
    if isinstance(rec, dict):
        return {
            "phone": str(rec.get("phone", "")),
            "ts": str(rec.get("ts", "")),
            "name": str(rec.get("name", "")),
            "username": str(rec.get("username", "")),
        }
    return None


def is_verified_chat(chat_id: int) -> bool:
    return _get_verified_record(chat_id) is not None


def kb_request_contact() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📲 مشاركة رقمي للبوت", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ===================== روابط قروبات الاستفسار لكل جامعة =====================
def load_group_links() -> Dict[str, Dict[str, str]]:
    data = _load_json(GROUPS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_group_links(data: Dict[str, Dict[str, str]]) -> None:
    _save_json(GROUPS_FILE, data)


GROUP_LINKS: Dict[str, Dict[str, str]] = load_group_links()


def get_uni_links(uni_name: str) -> Dict[str, str]:
    return GROUP_LINKS.get(uni_name, {"whatsapp": "", "telegram": ""})


def set_uni_link(uni_name: str, kind: str, value: str) -> None:
    GROUP_LINKS.setdefault(uni_name, {"whatsapp": "", "telegram": ""})
    GROUP_LINKS[uni_name][kind] = value
    save_group_links(GROUP_LINKS)


def clear_uni_link(uni_name: str, kind: str) -> None:
    GROUP_LINKS.setdefault(uni_name, {"whatsapp": "", "telegram": ""})
    GROUP_LINKS[uni_name][kind] = ""
    save_group_links(GROUP_LINKS)


# ===================== بيانات الجامعات =====================
UNI_INTERNATIONAL = "🌍 فروع جامعات دولية (المدينة التعليمية)"

UNIS: Dict[str, Dict[str, Any]] = {
    "جامعة قطر (QU)": {
        "website": "https://www.qu.edu.qa/",
        "about": "الجامعة الوطنية في قطر، وتضم كليات وبرامج متنوعة.",
        "requirements": (
            "• شهادة الثانوية أو ما يعادلها.\n"
            "• متطلبات اللغة/الرياضيات لبعض الكليات.\n"
            "• بعض البرامج تنافسية والحد الأدنى لا يضمن القبول.\n"
            "• قد تُطلب اختبارات/معايير إضافية حسب البرنامج."
        ),
        "college_min_default": "يختلف حسب الكلية",
        "colleges": [
            "كلية الآداب والعلوم",
            "كلية الإدارة والاقتصاد",
            "كلية التربية",
            "كلية الهندسة",
            "كلية القانون",
            "كلية العلوم الصحية",
            "كلية الصيدلة",
            "كلية الطب",
            "كلية التمريض",
            "كلية طب الأسنان",
            "كلية الشريعة والدراسات الإسلامية",
            "كلية علوم الرياضة",
        ],
    },
    "جامعة حمد بن خليفة (HBKU)": {
        "website": "https://www.hbku.edu.qa/",
        "about": "جامعة ضمن مؤسسة قطر، وتقدم برامج متخصصة حسب الكلية/البرنامج.",
        "requirements": (
            "• القبول حسب البرنامج.\n"
            "• غالبًا متطلبات لغة (IELTS/TOEFL) حسب البرنامج.\n"
            "• قد تُطلب مقابلة/سيرة ذاتية/خطاب نوايا حسب التخصص."
        ),
        "college_min_default": "حسب البرنامج",
        "colleges": [
            "كلية الدراسات الإسلامية (CIS)",
            "كلية العلوم الإنسانية والاجتماعية (CHSS)",
            "كلية العلوم والهندسة (CSE)",
            "كلية القانون (CL)",
            "كلية علوم الصحة والحياة (CHLS)",
            "كلية السياسات العامة (CPP)",
            "كلية/مدرسة الاقتصاد والإدارة (SEM)",
        ],
    },
    "جامعة الدوحة للعلوم والتكنولوجيا (UDST)": {
        "website": "https://www.udst.edu.qa/",
        "about": "جامعة تطبيقية تركّز على البرامج التقنية والمهنية.",
        "requirements": (
            "• شهادة الثانوية أو ما يعادلها.\n"
            "• حد أدنى عام شائع: 60% (قد يختلف حسب البرنامج).\n"
            "• قد توجد متطلبات مواد/مسار أو لغة حسب البرنامج."
        ),
        "college_min_default": "60%",
        "colleges": [
            "كلية الأعمال",
            "كلية الحوسبة وتقنية المعلومات",
            "كلية الهندسة والتكنولوجيا",
            "كلية العلوم الصحية",
            "كلية التعليم العام",
        ],
    },
    "جامعة لوسيل (LU)": {
        "website": "https://www.lu.edu.qa/",
        "about": "جامعة تقدم برامج بكالوريوس بعدة كليات.",
        "requirements": (
            "• شهادة الثانوية أو ما يعادلها.\n"
            "• حد أدنى عام شائع: 65% (قد توجد استثناءات حسب المسار).\n"
            "• قد تُطلب متطلبات إضافية حسب البرنامج."
        ),
        "college_min_default": "65%",
        "colleges": [
            "كلية التجارة والأعمال",
            "كلية التربية والآداب",
            "كلية القانون",
            "كلية تكنولوجيا المعلومات",
        ],
    },
    "معهد الدوحة للدراسات العليا (DI)": {
        "website": "https://www.dohainstitute.edu.qa/",
        "about": "مؤسسة تركز على الدراسات العليا (ماجستير/دكتوراه).",
        "requirements": (
            "• القبول حسب البرنامج (معدلات جامعية + مستندات).\n"
            "• قد تُطلب سيرة ذاتية/خطاب نوايا/مقابلة.\n"
            "• أمثلة قد تختلف حسب البرنامج."
        ),
        "college_min_default": "حسب البرنامج",
        "colleges": [
            "كلية العلوم الاجتماعية والإنسانية",
            "كلية الاقتصاد والإدارة والسياسات العامة",
        ],
    },
    UNI_INTERNATIONAL: {
        "website": "https://www.qf.org.qa/education/higher-education",
        "about": "فروع جامعات دولية داخل قطر (المدينة التعليمية)، شروطها تختلف حسب الفرع.",
        "requirements": (
            "• لا يوجد حد موحد.\n"
            "• كل فرع له شروطه: لغة/اختبارات/مقابلات/ملف...\n"
            "• راجع موقع الفرع للتفاصيل."
        ),
        "college_min_default": "حسب الجامعة/البرنامج",
        "colleges": [
            "VCUarts Qatar (فن وتصميم)",
            "Weill Cornell Medicine-Qatar (طب)",
            "Texas A&M University at Qatar (هندسة)",
            "Carnegie Mellon University in Qatar",
            "Georgetown University in Qatar",
            "Northwestern University in Qatar",
            "HEC Paris in Qatar",
        ],
    },
}

UNI_MAIN_LIST = [
    "جامعة قطر (QU)",
    "جامعة حمد بن خليفة (HBKU)",
    "جامعة الدوحة للعلوم والتكنولوجيا (UDST)",
    "جامعة لوسيل (LU)",
    "معهد الدوحة للدراسات العليا (DI)",
    UNI_INTERNATIONAL,
]

# ===================== نسب القبول (حسب السابق) =====================
QU_COLLEGE_MIN = {
    "كلية الآداب والعلوم": "70%",
    "كلية الإدارة والاقتصاد": "70%",
    "كلية التربية": "70%",
    "كلية الهندسة": "70%",
    "كلية القانون": "70%",
    "كلية الشريعة والدراسات الإسلامية": "70%",
    "كلية علوم الرياضة": "70%",
    "كلية العلوم الصحية": "70% + متطلبات إنجليزي/رياضيات",
    "كلية التمريض": "70% + متطلبات إنجليزي/رياضيات",
    "كلية الصيدلة": "80% + متطلبات إنجليزي/رياضيات",
    "كلية الطب": "85% + متطلبات إنجليزي/رياضيات",
    "كلية طب الأسنان": "85% + متطلبات إنجليزي/رياضيات",
}

# ===================== تعريفات الكليات =====================
COLLEGE_ABOUTS: Dict[str, Dict[str, str]] = {
    "جامعة قطر (QU)": {
        "كلية الآداب والعلوم": "تركّز على العلوم الأساسية والإنسانية والبحث العلمي.",
        "كلية الإدارة والاقتصاد": "تخصصات إدارة الأعمال والاقتصاد والمحاسبة والتمويل وغيرها.",
        "كلية التربية": "إعداد المعلمين والتخصصات التربوية وعلوم التعليم.",
        "كلية الهندسة": "برامج الهندسة المختلفة والتطبيقات التقنية.",
        "كلية القانون": "دراسة القانون والتشريعات وتخصصاتها.",
        "كلية العلوم الصحية": "تخصصات صحية تطبيقية مرتبطة بالممارسات الصحية.",
        "كلية الصيدلة": "علوم الأدوية والصيدلة السريرية والممارسة الصيدلانية.",
        "كلية الطب": "برنامج الطب البشري والتدريب السريري.",
        "كلية التمريض": "إعداد كوادر تمريضية مؤهلة مع تدريب عملي.",
        "كلية طب الأسنان": "برنامج طب الأسنان والتدريب السريري.",
        "كلية الشريعة والدراسات الإسلامية": "علوم الشريعة والفقه والدراسات الإسلامية.",
        "كلية علوم الرياضة": "علوم الرياضة والتدريب والصحة البدنية.",
    },
    "جامعة الدوحة للعلوم والتكنولوجيا (UDST)": {
        "كلية الأعمال": "برامج إدارة وأعمال تطبيقية مرتبطة بسوق العمل.",
        "كلية الحوسبة وتقنية المعلومات": "تخصصات تقنية وبرمجية وأمن معلومات وشبكات.",
        "كلية الهندسة والتكنولوجيا": "برامج هندسية وتقنية تطبيقية.",
        "كلية العلوم الصحية": "برامج صحية تطبيقية وتدريب عملي.",
        "كلية التعليم العام": "مواد تأسيسية ومهارات عامة داعمة للتخصصات.",
    },
    "جامعة لوسيل (LU)": {
        "كلية التجارة والأعمال": "تخصصات الإدارة وريادة الأعمال والتمويل.",
        "كلية التربية والآداب": "تخصصات تربوية وأدبية/إنسانية.",
        "كلية القانون": "برنامج القانون وتفرعاته.",
        "كلية تكنولوجيا المعلومات": "برامج تقنية حسب الخطة الدراسية.",
    },
    "جامعة حمد بن خليفة (HBKU)": {
        "كلية الدراسات الإسلامية (CIS)": "برامج في الدراسات الإسلامية المتخصصة.",
        "كلية العلوم الإنسانية والاجتماعية (CHSS)": "برامج إنسانية واجتماعية وبحوث.",
        "كلية العلوم والهندسة (CSE)": "برامج هندسية/علوم وابتكار.",
        "كلية القانون (CL)": "برامج قانونية متقدمة.",
        "كلية علوم الصحة والحياة (CHLS)": "برامج صحة/حياة وبحوث.",
        "كلية السياسات العامة (CPP)": "برامج سياسات عامة وإدارة.",
        "كلية/مدرسة الاقتصاد والإدارة (SEM)": "برامج اقتصاد وإدارة متقدمة.",
    },
    "معهد الدوحة للدراسات العليا (DI)": {
        "كلية العلوم الاجتماعية والإنسانية": "برامج ماجستير/دكتوراه في مجالات إنسانية واجتماعية.",
        "كلية الاقتصاد والإدارة والسياسات العامة": "برامج اقتصاد وإدارة وسياسات عامة.",
    },
    UNI_INTERNATIONAL: {
        "VCUarts Qatar (فن وتصميم)": "برامج فنون وتصميم احترافية.",
        "Weill Cornell Medicine-Qatar (طب)": "برنامج طب بشري.",
        "Texas A&M University at Qatar (هندسة)": "برامج هندسة متقدمة.",
        "Carnegie Mellon University in Qatar": "برامج متنوعة حسب الفرع.",
        "Georgetown University in Qatar": "برامج علاقات دولية وعلوم سياسية.",
        "Northwestern University in Qatar": "برامج إعلام واتصال وصحافة.",
        "HEC Paris in Qatar": "برامج إدارة وتنفيذي.",
    },
}


def get_college_about(uni_name: str, college: str) -> str:
    return COLLEGE_ABOUTS.get(uni_name, {}).get(college, "تعريف مختصر غير متوفر حاليًا.")


def get_college_min_acceptance(uni_name: str, college: str) -> str:
    if uni_name == "جامعة قطر (QU)":
        return QU_COLLEGE_MIN.get(college, "غير محدد")
    return UNIS.get(uni_name, {}).get("college_min_default", "حسب البرنامج")


# ===================== نصوص =====================
BOT_INTRO = (
    "<b>مرحبًا 👋</b>\n"
    "أنا <b>المرشد الأكاديمي</b> لخريجي الثانوية العامة في قطر.\n"
    "أساعدك في معرفة الجامعات والكليات وتعريفاتها ونِسَب القبول وروابط قروب الاستفسارات.\n\n"
    f"🌐 وزارة التربية والتعليم والتعليم العالي:\n{MOEHE_OFFICIAL_URL}"
)

START_CONFIRM = (
    "✅ <b>تأكيد الهوية</b>\n"
    "للتأكد أن هويتك <b>قطرية</b>، فضلاً شارك رقمك.\n\n"
    "هذا يساعدنا على تقديم خدمات أفضل لك مستقبلاً.\n"
    "اضغط زر <b>📲 مشاركة رقمي للبوت</b> بالأسفل."
)

HELP = (
    "<b>مساعدة</b>\n"
    "• اختر الجامعة → (🏫 الكليات) → اختر الكلية لعرض تعريفها ونسبة القبول.\n"
    "• زر (📝 متطلبات التسجيل) يعرض متطلبات التسجيل وموقع الجامعة.\n"
)

SUMMARY_ADMISSION = (
    "<b>ملخص نسب القبول (حسب السابق)</b>\n\n"
    "<b>جامعة قطر</b>\n"
    "• أغلب الكليات: 70%\n"
    "• الصيدلة: 80%\n"
    "• الطب وطب الأسنان: 85%\n"
    "• العلوم الصحية/التمريض: 70% + متطلبات\n\n"
    "<b>جامعة لوسيل</b> • غالبًا 65%\n"
    "<b>UDST</b> • غالبًا 60%\n"
    "<b>HBKU</b> • حسب البرنامج\n"
    "<b>معهد الدوحة</b> • حسب البرنامج\n"
    "<b>الفروع الدولية</b> • حسب الجامعة/البرنامج"
)

NOT_QATARI_MSG = (
    "❌ عذرًا، هذا البوت متاح فقط للأرقام القطرية (+974).\n"
    "تم تسجيل المحاولة وإرسالها لقروب السجل."
)

# ===================== أزرار =====================
BTN_BEGIN = "▶️ ابدأ"
BTN_SETTINGS = "⚙️ إعدادات البوت"
BTN_MOEHE = "🌐 وزارة التربية والتعليم"

# Settings
BTN_STATS = "📊 إحصائيات"
BTN_EXPORT_USERS = "📥 تصدير المستخدمين"
BTN_SUCCESS_REQUESTS = "✅ جهات اتصال نجحت بالانضمام"
BTN_FAILED_REQUESTS = "🚫 جهات اتصال مرفوضة"
BTN_PRE_ATTEMPTS = "🟡 محاولات قبل مشاركة الرقم"
BTN_EXPORT_PHONES = "📞 عرض الأرقام كاملة (سوبر أدمن)"
BTN_ANNOUNCE = "📢 إعلان"
BTN_CANCEL_ANN = "❌ إلغاء الإعلان"
BTN_GROUPS_ADMIN = "👥 إدارة القروبات"
BTN_MODS_ADMIN = "👤 إدارة المشرفين"
BTN_BACK_SETTINGS = "⬅️ رجوع من الإعدادات"

# Mods
BTN_ADD_MOD = "➕ إضافة مشرف"
BTN_REMOVE_MOD = "➖ حذف مشرف"
BTN_LIST_MODS = "📋 قائمة المشرفين"
BTN_CANCEL_MOD = "❌ إلغاء"
BTN_BACK_MODS = "⬅️ رجوع من إدارة المشرفين"

# Group admin
BTN_VIEW_LINKS = "📎 عرض الروابط الحالية"
BTN_EDIT_WA = "✏️ تعديل واتساب"
BTN_EDIT_TG = "✏️ تعديل تليجرام"
BTN_DEL_WA = "🗑️ حذف واتساب"
BTN_DEL_TG = "🗑️ حذف تليجرام"
BTN_BACK_GROUP_MENU = "⬅️ رجوع لقائمة القروب"

# Uni menu
BTN_COLLEGES = "🏫 الكليات"
BTN_REQUIREMENTS = "📝 متطلبات التسجيل"
BTN_UNI_ABOUT = "📌 معلومات عن الجامعة"
BTN_GROUPS = "👥 قروب الاستفسارات"
BTN_BACK_UNIS = "⬅️ رجوع للجامعات"
BTN_HOME = "🏠 الرئيسية"
BTN_BACK = "⬅️ رجوع"

# Group view
BTN_GROUP_WA = "🔗 رابط قروب واتساب"
BTN_GROUP_TG = "🔗 رابط قروب تليجرام"
BTN_EDIT_GROUP_LINKS = "🛠️ تعديل روابط القروب"


def chunk_buttons(items, per_row=2):
    rows, row = [], []
    for it in items:
        row.append(it)
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def kb_start_screen(update: Update) -> ReplyKeyboardMarkup:
    rows = [[BTN_BEGIN], [BTN_MOEHE]]
    if is_staff(update):
        rows.append([BTN_SETTINGS])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_home(update: Update) -> ReplyKeyboardMarkup:
    rows = [
        ["📚 الجامعات في قطر", "🏫 الكليات في الجامعات"],
        ["✅ ملخص القبول", "ℹ️ مساعدة"],
        [BTN_MOEHE],
    ]
    if is_staff(update):
        rows.append([BTN_SETTINGS])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_universities() -> ReplyKeyboardMarkup:
    rows = chunk_buttons(UNI_MAIN_LIST, per_row=2)
    rows.append(["⬅️ رجوع للرئيسية"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_uni_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_COLLEGES, BTN_REQUIREMENTS],
            [BTN_UNI_ABOUT],
            [BTN_GROUPS],
            [BTN_BACK_UNIS, BTN_HOME],
        ],
        resize_keyboard=True,
    )


def kb_colleges_list(uni_name: str) -> ReplyKeyboardMarkup:
    cols = UNIS[uni_name]["colleges"]
    rows = chunk_buttons(cols, per_row=2)
    rows.append(["⬅️ رجوع للجامعة", BTN_HOME])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_group_menu(update: Update) -> ReplyKeyboardMarkup:
    rows = [[BTN_GROUP_WA, BTN_GROUP_TG]]
    if is_staff(update):
        rows.append([BTN_EDIT_GROUP_LINKS])
    rows.append([BTN_BACK, "⬅️ رجوع للجامعة", BTN_HOME])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_group_admin_edit() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_VIEW_LINKS],
            [BTN_EDIT_WA, BTN_EDIT_TG],
            [BTN_DEL_WA, BTN_DEL_TG],
            [BTN_BACK_GROUP_MENU, BTN_HOME],
        ],
        resize_keyboard=True,
    )


def kb_settings_menu(update: Update) -> ReplyKeyboardMarkup:
    rows = [
        [BTN_STATS, BTN_EXPORT_USERS],
        [BTN_SUCCESS_REQUESTS, BTN_FAILED_REQUESTS],
        [BTN_PRE_ATTEMPTS],
        [BTN_ANNOUNCE],
        [BTN_GROUPS_ADMIN],
    ]
    if is_super_admin(update):
        rows.append([BTN_EXPORT_PHONES])
        rows.append([BTN_MODS_ADMIN])
    rows.append([BTN_BACK_SETTINGS, BTN_HOME])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_announce_wait() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_CANCEL_ANN], [BTN_BACK_SETTINGS, BTN_HOME]],
        resize_keyboard=True,
    )


def kb_settings_groups_choose_uni(update: Update) -> ReplyKeyboardMarkup:
    rows = chunk_buttons(UNI_MAIN_LIST, per_row=2)
    rows.append([BTN_BACK_SETTINGS, BTN_HOME])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_mods_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_ADD_MOD, BTN_REMOVE_MOD],
            [BTN_LIST_MODS],
            [BTN_BACK_MODS, BTN_HOME],
        ],
        resize_keyboard=True,
    )


def kb_mods_wait() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_CANCEL_MOD], [BTN_BACK_MODS, BTN_HOME]],
        resize_keyboard=True,
    )


def sanitize_link(s: str) -> str:
    return (s or "").strip()


def is_valid_url(s: str) -> bool:
    s = sanitize_link(s)
    return s.startswith("http://") or s.startswith("https://")


def parse_possible_user_id(text: str) -> Optional[int]:
    t = (text or "").strip()
    if t.isdigit():
        try:
            return int(t)
        except Exception:
            return None
    return None


async def ensure_verified_or_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # السوبر أدمن/المشرفين يدخلون بدون مشاركة جهة الاتصال
    if is_staff(update):
        return True

    chat = update.effective_chat
    if not chat:
        return False

    if is_verified_chat(int(chat.id)):
        return True

    await update.message.reply_text(START_CONFIRM, parse_mode=ParseMode.HTML, reply_markup=kb_request_contact())
    return False


# ===================== Commands =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    remember_user(update)
    context.user_data.clear()

    # سجل محاولة دخول مباشرة عند /start
    if not is_staff(update):
        chat = update.effective_chat
        if chat and not is_verified_chat(int(chat.id)):
            add_attempt(update, status="pre_start", reason="دخل /start قبل مشاركة الرقم")
            await send_to_log_group(
                context,
                "🟡 <b>محاولة دخول (قبل مشاركة الرقم)</b>\n"
                f"{user_brief_text(update)}\n"
                f"• السبب: دخل /start\n"
                f"• قروب السجل: {LOG_GROUP_INVITE}",
            )

    await update.message.reply_text(BOT_INTRO, parse_mode=ParseMode.HTML, reply_markup=kb_start_screen(update))


async def setlog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # تعيين قروب السجل (داخل القروب فقط) بواسطة السوبر أدمن
    if not is_super_admin(update):
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("استخدم الأمر داخل القروب فقط.")
        return
    CONFIG["log_group_chat_id"] = int(chat.id)
    CONFIG["log_group_invite"] = LOG_GROUP_INVITE
    save_config(CONFIG)
    await update.message.reply_text("✅ تم تعيين قروب السجل بنجاح.")


# ===================== Contact Handler =====================
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    remember_user(update)

    msg = update.message
    if not msg or not msg.contact:
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    phone_raw = msg.contact.phone_number or ""
    phone_digits = normalize_phone(phone_raw)
    masked = mask_phone_digits(phone_digits)

    # لازم يشارك رقم نفسه (إذا توفر user_id)
    if msg.contact.user_id and msg.contact.user_id != user.id:
        add_attempt(update, status="rejected_not_self", phone_digits=phone_digits, reason="شارك رقم ليس لنفسه")
        await send_to_log_group(
            context,
            "⚠️ <b>محاولة مشاركة رقم ليس لنفس المستخدم</b>\n"
            f"{user_brief_text(update)}\n"
            f"• الرقم (مموّه): <code>+{masked}</code>\n"
            f"• قروب السجل: {LOG_GROUP_INVITE}",
        )
        await msg.reply_text("❌ لازم تشارك رقمك أنت من الزر (📲 مشاركة رقمي للبوت).", reply_markup=kb_request_contact())
        return

    # قبول/رفض + تسجيل للقروب
    if is_qatari_phone(phone_raw):
        VERIFIED_USERS[str(chat.id)] = {
            "phone": phone_digits,
            "ts": now_ts(),
            "name": (user.full_name or "").strip(),
            "username": f"@{user.username}" if user.username else "",
        }
        save_verified(VERIFIED_USERS)

        add_attempt(update, status="accepted", phone_digits=phone_digits, reason="رقم قطري")

        await send_to_log_group(
            context,
            "✅ <b>طلب انضمام ناجح (رقم قطري)</b>\n"
            f"{user_brief_text(update)}\n"
            f"• الرقم (مموّه): <code>+{masked}</code>\n"
            f"• قروب السجل: {LOG_GROUP_INVITE}",
        )

        await msg.reply_text("✅ تم التحقق بنجاح! أهلاً بك 👋", reply_markup=kb_home(update))
        await msg.reply_text(BOT_INTRO, parse_mode=ParseMode.HTML, reply_markup=kb_home(update))
        return

    add_attempt(update, status="rejected_non_qatari", phone_digits=phone_digits, reason="رقم غير قطري")

    await send_to_log_group(
        context,
        "🚫 <b>محاولة دخول مرفوضة (رقم غير قطري)</b>\n"
        f"{user_brief_text(update)}\n"
        f"• الرقم (مموّه): <code>+{masked}</code>\n"
        f"• قروب السجل: {LOG_GROUP_INVITE}",
    )
    await msg.reply_text(NOT_QATARI_MSG, reply_markup=kb_request_contact())


# ===================== Text Handler =====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    remember_user(update)
    text = (update.message.text or "").strip()

    # شاشة البداية: زر ابدأ
    if text == BTN_BEGIN:
        # السوبر أدمن/المشرفين يدخلون فورًا
        if is_staff(update):
            await update.message.reply_text("تم الدخول ✅", reply_markup=kb_home(update))
            return

        chat = update.effective_chat
        if chat and is_verified_chat(int(chat.id)):
            await update.message.reply_text("مرحبًا بك ✅", reply_markup=kb_home(update))
            return

        add_attempt(update, status="pre_begin", reason="ضغط زر ابدأ قبل مشاركة الرقم")
        await send_to_log_group(
            context,
            "🟡 <b>محاولة دخول (ضغط زر ابدأ قبل مشاركة الرقم)</b>\n"
            f"{user_brief_text(update)}\n"
            f"• قروب السجل: {LOG_GROUP_INVITE}",
        )
        await update.message.reply_text(START_CONFIRM, parse_mode=ParseMode.HTML, reply_markup=kb_request_contact())
        return

    # لازم يكون موثق (إلا المشرفين)
    if not await ensure_verified_or_ask(update, context):
        return

    # ================== إعلان ==================
    if context.user_data.get("awaiting_announcement"):
        if not is_staff(update):
            context.user_data.pop("awaiting_announcement", None)
            await update.message.reply_text("غير مسموح.", reply_markup=kb_start_screen(update))
            return

        if text == BTN_CANCEL_ANN:
            context.user_data.pop("awaiting_announcement", None)
            await update.message.reply_text("تم الإلغاء ✅", reply_markup=kb_settings_menu(update))
            return

        announcement = text.strip()
        if not announcement:
            await update.message.reply_text("اكتب نص الإعلان فقط.", reply_markup=kb_announce_wait())
            return

        ok, fail = 0, 0
        for chat_id in list(KNOWN_USERS):
            try:
                await context.bot.send_message(chat_id=chat_id, text=announcement)
                ok += 1
            except Exception:
                fail += 1

        context.user_data.pop("awaiting_announcement", None)
        await update.message.reply_text(
            f"تم إرسال الإعلان ✅\nنجح: {ok}\nفشل: {fail}",
            reply_markup=kb_settings_menu(update),
        )
        return

    # ================== تعديل روابط القروب ==================
    awaiting_link = context.user_data.get("awaiting_link")
    if awaiting_link:
        if not is_staff(update):
            context.user_data.pop("awaiting_link", None)
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return

        uni_name = context.user_data.get("selected_uni")
        if not uni_name:
            context.user_data.pop("awaiting_link", None)
            await update.message.reply_text("اختر جامعة أولًا.", reply_markup=kb_universities())
            return

        new_link = sanitize_link(text)
        if not is_valid_url(new_link):
            await update.message.reply_text("الرابط غير صحيح. أرسل رابط يبدأ بـ https://", reply_markup=kb_group_admin_edit())
            return

        set_uni_link(uni_name, awaiting_link, new_link)
        context.user_data.pop("awaiting_link", None)
        await update.message.reply_text("تم حفظ الرابط ✅", reply_markup=kb_group_admin_edit())
        return

    # ================== إدارة المشرفين ==================
    if context.user_data.get("awaiting_mod_add"):
        if not is_super_admin(update):
            context.user_data.pop("awaiting_mod_add", None)
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return

        if text == BTN_CANCEL_MOD:
            context.user_data.pop("awaiting_mod_add", None)
            await update.message.reply_text("تم الإلغاء ✅", reply_markup=kb_mods_menu())
            return

        fwd_user = getattr(update.message, "forward_from", None)
        new_id = int(fwd_user.id) if fwd_user else parse_possible_user_id(text)

        if not new_id:
            await update.message.reply_text(
                "أرسل ID بالأرقام أو اعمل Forward لرسالة من الشخص.\nمثال: 123456789",
                reply_markup=kb_mods_wait(),
            )
            return

        if new_id == SUPER_ADMIN_ID:
            context.user_data.pop("awaiting_mod_add", None)
            await update.message.reply_text("هذا هو السوبر أدمن أصلًا ✅", reply_markup=kb_mods_menu())
            return

        MODS.add(int(new_id))
        save_mods(MODS)
        context.user_data.pop("awaiting_mod_add", None)
        await update.message.reply_text(f"تمت إضافة المشرف ✅\nID: {new_id}", reply_markup=kb_mods_menu())
        return

    if context.user_data.get("awaiting_mod_remove"):
        if not is_super_admin(update):
            context.user_data.pop("awaiting_mod_remove", None)
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return

        if text == BTN_CANCEL_MOD:
            context.user_data.pop("awaiting_mod_remove", None)
            await update.message.reply_text("تم الإلغاء ✅", reply_markup=kb_mods_menu())
            return

        fwd_user = getattr(update.message, "forward_from", None)
        rem_id = int(fwd_user.id) if fwd_user else parse_possible_user_id(text)

        if not rem_id:
            await update.message.reply_text("أرسل ID بالأرقام أو Forward لرسالة منه.", reply_markup=kb_mods_wait())
            return

        if int(rem_id) in MODS:
            MODS.remove(int(rem_id))
            save_mods(MODS)
            await update.message.reply_text(f"تم حذف المشرف ✅\nID: {rem_id}", reply_markup=kb_mods_menu())
        else:
            await update.message.reply_text("هذا الـ ID غير موجود ضمن المشرفين.", reply_markup=kb_mods_menu())

        context.user_data.pop("awaiting_mod_remove", None)
        return

    # ================== تنقل عام ==================
    if text == BTN_HOME or text == "⬅️ رجوع للرئيسية":
        context.user_data.clear()
        await update.message.reply_text("رجعناك للرئيسية ✅", reply_markup=kb_home(update))
        return

    if text == BTN_MOEHE:
        await update.message.reply_text(
            f"🌐 وزارة التربية والتعليم والتعليم العالي:\n{MOEHE_OFFICIAL_URL}",
            reply_markup=kb_home(update),
        )
        return

    # ================== الرئيسية ==================
    if text == "📚 الجامعات في قطر":
        await update.message.reply_text("<b>اختر الجامعة:</b>", parse_mode=ParseMode.HTML, reply_markup=kb_universities())
        return

    if text == "🏫 الكليات في الجامعات":
        await update.message.reply_text("<b>اختر الجامعة ثم اضغط (🏫 الكليات):</b>", parse_mode=ParseMode.HTML, reply_markup=kb_universities())
        return

    if text == "✅ ملخص القبول":
        await update.message.reply_text(SUMMARY_ADMISSION, parse_mode=ParseMode.HTML, reply_markup=kb_home(update))
        return

    if text == "ℹ️ مساعدة":
        await update.message.reply_text(HELP, parse_mode=ParseMode.HTML, reply_markup=kb_home(update))
        return

    # ================== إعدادات ==================
    if text == BTN_SETTINGS:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        context.user_data["mode"] = "settings"
        await update.message.reply_text("⚙️ <b>إعدادات البوت</b>", parse_mode=ParseMode.HTML, reply_markup=kb_settings_menu(update))
        return

    if text == BTN_BACK_SETTINGS:
        context.user_data.pop("mode", None)
        await update.message.reply_text("تم الرجوع ✅", reply_markup=kb_home(update))
        return

    if text == BTN_STATS:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        total_attempts = len(ATTEMPTS)
        accepted = sum(1 for x in ATTEMPTS if x.get("status") == "accepted")
        rejected = sum(1 for x in ATTEMPTS if x.get("status", "").startswith("rejected"))
        pre = sum(1 for x in ATTEMPTS if x.get("status", "").startswith("pre_"))
        await update.message.reply_text(
            "📊 <b>إحصائيات</b>\n\n"
            f"• عدد المستخدمين الذين تفاعلوا مع البوت: <b>{len(KNOWN_USERS)}</b>\n"
            f"• عدد المشرفين (غير السوبر أدمن): <b>{len(MODS)}</b>\n"
            f"• عدد المنضمين (أرقام قطرية موثقة): <b>{len(VERIFIED_USERS)}</b>\n\n"
            f"• إجمالي محاولات الدخول: <b>{total_attempts}</b>\n"
            f"• محاولات قبل مشاركة الرقم: <b>{pre}</b>\n"
            f"• طلبات ناجحة: <b>{accepted}</b>\n"
            f"• طلبات مرفوضة: <b>{rejected}</b>\n\n"
            f"• قروب السجل: {LOG_GROUP_INVITE}\n",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_settings_menu(update),
        )
        return

    if text == BTN_EXPORT_USERS:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        ids = "\n".join(str(x) for x in sorted(KNOWN_USERS))
        msg = "📥 <b>قائمة المستخدمين (chat_id)</b>\n\n" + (ids if ids else "لا يوجد مستخدمون بعد.")
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb_settings_menu(update))
        return

    def _render_attempts(items: List[Dict[str, Any]], title: str, limit: int = 60) -> str:
        items = items[-limit:]
        items = list(reversed(items))  # الأحدث أولاً
        lines = []
        for it in items:
            ts = it.get("ts", "-")
            name = it.get("name") or "(بدون اسم)"
            username = it.get("username") or "(بدون معرف)"
            chat_id = it.get("chat_id")
            m = it.get("phone_masked") or ""
            reason = it.get("reason") or ""
            phone_part = f" | +{m}" if m else ""
            lines.append(f"• {ts} | {name} | {username} | chat_id:{chat_id}{phone_part} | {reason}")
        body = "\n".join(lines) if lines else "لا يوجد سجلات."
        return f"<b>{title}</b>\n\n{body}"

    if text == BTN_SUCCESS_REQUESTS:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        items = [x for x in ATTEMPTS if x.get("status") == "accepted"]
        await update.message.reply_text(
            _render_attempts(items, "✅ جهات الاتصال التي نجحت بالانضمام (آخر السجلات)"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb_settings_menu(update),
        )
        return

    if text == BTN_FAILED_REQUESTS:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        items = [x for x in ATTEMPTS if str(x.get("status", "")).startswith("rejected")]
        await update.message.reply_text(
            _render_attempts(items, "🚫 جهات الاتصال المرفوضة (آخر السجلات)"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb_settings_menu(update),
        )
        return

    if text == BTN_PRE_ATTEMPTS:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        items = [x for x in ATTEMPTS if str(x.get("status", "")).startswith("pre_")]
        await update.message.reply_text(
            _render_attempts(items, "🟡 محاولات قبل مشاركة الرقم (آخر السجلات)"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb_settings_menu(update),
        )
        return

    if text == BTN_EXPORT_PHONES:
        if not is_super_admin(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_settings_menu(update))
            return
        # السوبر أدمن فقط: عرض الأرقام كاملة (في الخاص)
        lines = []
        for chat_id_str, rec in VERIFIED_USERS.items():
            if isinstance(rec, str):
                phone = rec
                ts = ""
                name = ""
                username = ""
            else:
                phone = str(rec.get("phone", ""))
                ts = str(rec.get("ts", ""))
                name = str(rec.get("name", ""))
                username = str(rec.get("username", ""))
            lines.append(f"{ts} | {name} | {username} | chat_id:{chat_id_str} => +{phone}")
        out = "\n".join(lines) if lines else "لا يوجد أرقام موثقة بعد."
        await update.message.reply_text(
            "📞 <b>الأرقام الكاملة (سوبر أدمن فقط)</b>\n\n" + out,
            parse_mode=ParseMode.HTML,
            reply_markup=kb_settings_menu(update),
        )
        return

    if text == BTN_ANNOUNCE:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        context.user_data["awaiting_announcement"] = True
        await update.message.reply_text(
            "📢 اكتب نص الإعلان الآن وسأرسله لكل المستخدمين.\nللإلغاء اضغط: ❌ إلغاء الإعلان",
            reply_markup=kb_announce_wait(),
        )
        return

    if text == BTN_GROUPS_ADMIN:
        if not is_staff(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
            return
        context.user_data["mode"] = "settings_groups"
        await update.message.reply_text(
            "👥 اختر الجامعة لإدارة روابط قروب الاستفسارات:",
            reply_markup=kb_settings_groups_choose_uni(update),
        )
        return

    if text == BTN_MODS_ADMIN:
        if not is_super_admin(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_settings_menu(update))
            return
        context.user_data["mode"] = "mods_menu"
        await update.message.reply_text("👤 <b>إدارة المشرفين</b>", parse_mode=ParseMode.HTML, reply_markup=kb_mods_menu())
        return

    if text == BTN_BACK_MODS:
        context.user_data.pop("mode", None)
        await update.message.reply_text("تم الرجوع ✅", reply_markup=kb_settings_menu(update))
        return

    if text == BTN_LIST_MODS:
        if not is_super_admin(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_settings_menu(update))
            return
        mods_list = "\n".join(str(x) for x in sorted(MODS)) or "لا يوجد مشرفون بعد."
        await update.message.reply_text("📋 <b>قائمة المشرفين (IDs)</b>\n\n" + mods_list, parse_mode=ParseMode.HTML, reply_markup=kb_mods_menu())
        return

    if text == BTN_ADD_MOD:
        if not is_super_admin(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_settings_menu(update))
            return
        context.user_data["awaiting_mod_add"] = True
        await update.message.reply_text(
            "➕ لإضافة مشرف:\n"
            "• اعمل Forward لرسالة من الشخص\n"
            "أو\n"
            "• اكتب الـ ID بالأرقام.\n\n"
            "للإلغاء اضغط: ❌ إلغاء",
            reply_markup=kb_mods_wait(),
        )
        return

    if text == BTN_REMOVE_MOD:
        if not is_super_admin(update):
            await update.message.reply_text("غير مسموح.", reply_markup=kb_settings_menu(update))
            return
        context.user_data["awaiting_mod_remove"] = True
        await update.message.reply_text(
            "➖ لحذف مشرف:\n"
            "• Forward لرسالة من المشرف\n"
            "أو\n"
            "• اكتب الـ ID بالأرقام.\n\n"
            "للإلغاء اضغط: ❌ إلغاء",
            reply_markup=kb_mods_wait(),
        )
        return

    # ================== اختيار جامعة ==================
    if text in UNIS:
        context.user_data["selected_uni"] = text

        if context.user_data.get("mode") == "settings_groups":
            if not is_staff(update):
                await update.message.reply_text("غير مسموح.", reply_markup=kb_home(update))
                return
            await update.message.reply_text(
                f"<b>{text}</b>\n🛠️ إدارة روابط قروب الاستفسارات:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_group_admin_edit(),
            )
            return

        context.user_data["mode"] = "uni_menu"
        await update.message.reply_text(
            f"<b>{text}</b>\nاختر ماذا تريد:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_uni_menu(),
        )
        return

    if text == BTN_BACK_UNIS:
        context.user_data.pop("selected_uni", None)
        context.user_data.pop("mode", None)
        await update.message.reply_text("<b>اختر الجامعة:</b>", parse_mode=ParseMode.HTML, reply_markup=kb_universities())
        return

    # ================== داخل جامعة ==================
    uni_name = context.user_data.get("selected_uni")
    if uni_name and uni_name in UNIS:
        uni = UNIS[uni_name]
        mode = context.user_data.get("mode")

        if text == "⬅️ رجوع للجامعة" or text == BTN_BACK:
            context.user_data["mode"] = "uni_menu"
            await update.message.reply_text(
                f"<b>{uni_name}</b>\nاختر ماذا تريد:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_uni_menu(),
            )
            return

        if text == BTN_UNI_ABOUT:
            msg = (
                f"<b>{uni_name}</b>\n\n"
                f"{uni['about']}\n\n"
                f"🌐 الموقع الإلكتروني:\n{uni['website']}"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb_uni_menu())
            return

        if text == BTN_REQUIREMENTS:
            msg = (
                f"<b>{uni_name}</b>\n"
                f"🌐 الموقع الإلكتروني:\n{uni['website']}\n\n"
                f"<b>التعريف المختصر:</b>\n{uni['about']}\n\n"
                f"<b>متطلبات التسجيل:</b>\n{uni['requirements']}\n\n"
                "✅ <b>ملاحظة:</b>\n"
                "نِسَب القبول تظهر عند اختيار الكلية (خصوصًا جامعة قطر)."
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb_uni_menu())
            return

        if text == BTN_COLLEGES:
            context.user_data["mode"] = "college_list"
            await update.message.reply_text(
                f"<b>{uni_name}</b>\nاختر الكلية:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_colleges_list(uni_name),
            )
            return

        if text == BTN_GROUPS:
            context.user_data["mode"] = "group_menu"
            await update.message.reply_text(
                f"<b>{uni_name}</b>\nاختر رابط قروب الاستفسارات:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_group_menu(update),
            )
            return

        # ================== قروب الاستفسارات + إدارة الروابط ==================
        if mode in ("group_menu", "group_admin_edit"):
            links = get_uni_links(uni_name)

            if text == BTN_GROUP_WA:
                w = (links.get("whatsapp") or "").strip()
                await update.message.reply_text(w if w else "لا يوجد رابط واتساب لقروب الاستفسارات حاليًا.", reply_markup=kb_group_menu(update))
                return

            if text == BTN_GROUP_TG:
                t = (links.get("telegram") or "").strip()
                await update.message.reply_text(t if t else "لا يوجد رابط تليجرام لقروب الاستفسارات حاليًا.", reply_markup=kb_group_menu(update))
                return

            if text == BTN_EDIT_GROUP_LINKS:
                if not is_staff(update):
                    await update.message.reply_text("هذه الميزة للمشرفين فقط.", reply_markup=kb_group_menu(update))
                    return
                context.user_data["mode"] = "group_admin_edit"
                await update.message.reply_text("🛠️ إدارة روابط قروب الاستفسارات:", reply_markup=kb_group_admin_edit())
                return

            if text == BTN_BACK_GROUP_MENU:
                context.user_data["mode"] = "group_menu"
                await update.message.reply_text(
                    f"<b>{uni_name}</b>\nاختر رابط قروب الاستفسارات:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb_group_menu(update),
                )
                return

            if text == BTN_VIEW_LINKS:
                if not is_staff(update):
                    await update.message.reply_text("غير مسموح.", reply_markup=kb_group_menu(update))
                    return
                w = (links.get("whatsapp") or "").strip()
                t = (links.get("telegram") or "").strip()
                msg = (
                    f"<b>{uni_name}</b>\n\n"
                    f"📎 <b>روابط قروب الاستفسارات الحالية:</b>\n"
                    f"• واتساب: {w if w else 'غير موجود'}\n"
                    f"• تليجرام: {t if t else 'غير موجود'}"
                )
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb_group_admin_edit())
                return

            if text == BTN_EDIT_WA:
                if not is_staff(update):
                    await update.message.reply_text("غير مسموح.", reply_markup=kb_group_menu(update))
                    return
                context.user_data["awaiting_link"] = "whatsapp"
                await update.message.reply_text("أرسل رابط واتساب لقروب الاستفسارات (https://...):", reply_markup=kb_group_admin_edit())
                return

            if text == BTN_EDIT_TG:
                if not is_staff(update):
                    await update.message.reply_text("غير مسموح.", reply_markup=kb_group_menu(update))
                    return
                context.user_data["awaiting_link"] = "telegram"
                await update.message.reply_text("أرسل رابط تليجرام لقروب الاستفسارات (https://...):", reply_markup=kb_group_admin_edit())
                return

            if text == BTN_DEL_WA:
                if not is_staff(update):
                    await update.message.reply_text("غير مسموح.", reply_markup=kb_group_menu(update))
                    return
                clear_uni_link(uni_name, "whatsapp")
                await update.message.reply_text("تم حذف رابط واتساب ✅", reply_markup=kb_group_admin_edit())
                return

            if text == BTN_DEL_TG:
                if not is_staff(update):
                    await update.message.reply_text("غير مسموح.", reply_markup=kb_group_menu(update))
                    return
                clear_uni_link(uni_name, "telegram")
                await update.message.reply_text("تم حذف رابط تليجرام ✅", reply_markup=kb_group_admin_edit())
                return

        # ================== اختيار كلية ==================
        if mode == "college_list" and text in uni["colleges"]:
            college = text
            about = get_college_about(uni_name, college)
            min_req = get_college_min_acceptance(uni_name, college)

            msg = (
                f"<b>{uni_name}</b>\n"
                f"<b>الكلية:</b> {college}\n\n"
                f"<b>تعريف مختصر:</b>\n{about}\n\n"
                f"<b>نسبة/حد القبول (حسب السابق):</b>\n{min_req}\n\n"
                "• ملاحظة: بعض البرامج تنافسية والحد الأدنى لا يضمن القبول النهائي.\n"
                "• التفاصيل الدقيقة دائمًا في موقع الجامعة."
            )

            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb_colleges_list(uni_name))
            return

    await update.message.reply_text("اختار من الأزرار الموجودة 👇", reply_markup=kb_home(update))


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        raise RuntimeError("BOT_TOKEN فارغ. ضع توكن البوت في BOT_TOKEN.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setlog", setlog))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
