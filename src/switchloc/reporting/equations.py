# -*- coding: utf-8 -*-
"""equations.py — فرمول‌های محاسبات کامل در گزارش Word (درخواست کاربر).

«برای نوشتن فرمول‌ها از قابلیت equation ورد استفاده کن» — هر فرمول به
صورت OMML بومی Word ساخته می‌شود (مثل Insert ▸ Equation خود ورد: کسر
واری genuine، رادیکال genuine، توان genuine) — نه متن ساده و نه تصویر.
هر builder یک رشتهٔ XML معتبر `<m:oMathPara>` برمی‌گرداند؛
`docx_report.append_equation()` آن را داخل یک پاراگراف تزریق می‌کند.

ساخت: رشته‌های XML ایستا (deterministic) — بدون وابستگی جدید؛ اجرای
تست‌ها XML را با ElementTree پارس می‌کند تا معتبربودن تضمین شود.
"""
from __future__ import annotations

from xml.sax.saxutils import escape as _esc

NS = ('xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
      'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')


# ---------------------------------------------------------------------------
# OMML primitives (subset needed by the engineering formulas)
# ---------------------------------------------------------------------------
def _r(t: str) -> str:
    """A plain math run."""
    return f'<m:r><m:t xml:space="preserve">{_esc(t)}</m:t></m:r>'


def _frac(num: str, den: str) -> str:
    """Genuine Word fraction."""
    return f'<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>'


def _sqrt(e: str) -> str:
    """Genuine square root."""
    return ('<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
            f'<m:deg/><m:e>{e}</m:e></m:rad>')


def _sup(base: str, sup: str) -> str:
    """Genuine superscript."""
    return f'<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>'


def _sub(base: str, sub: str) -> str:
    """Genuine subscript."""
    return f'<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>'


def omml(inner: str) -> str:
    """Full `<m:oMathPara>` element (one display equation)."""
    return f'<m:oMathPara {NS}><m:oMath>{inner}</m:oMath></m:oMathPara>'


# ---------------------------------------------------------------------------
# the study's formulas (official anchors in the notes of the section)
# ---------------------------------------------------------------------------
def eq_load_scaling_s_load() -> str:
    """S_load = √(P² + Q²)"""
    p2 = _sup(_r("P"), _r("2"))
    q2 = _sup(_r("Q"), _r("2"))
    return omml(_sub(_r("S"), _r("load")) + _r("=")
                + _sqrt(p2 + _r("+") + q2))


def eq_load_scaling_cos_phi() -> str:
    """φ = arctan(Q / P)  ;  cos φ = P / S_load"""
    return omml(_r("φ=arctan") + _frac(_r("Q"), _r("P"))
                + _r("  ,  ") + _r("cos") + _r("φ=")
                + _frac(_r("P"), _sub(_r("S"), _r("load"))))


def eq_load_scaling_p_rated() -> str:
    """P_rated,i = S_rated,i × cos φ"""
    return omml(_sub(_r("P"), _r("rated,i")) + _r("=")
                + _sub(_r("S"), _r("rated,i")) + _r("×cosφ"))


def eq_load_scaling_k() -> str:
    """K = S_load / Σ S_rated"""
    return omml(_r("K=") + _frac(_sub(_r("S"), _r("load")),
                                 _r("Σ") + _sub(_r("S"), _r("rated"))))


def eq_load_scaling_p_t() -> str:
    """P_T,i = K × S_rated,i × cos φ"""
    return omml(_sub(_r("P"), _r("T,i")) + _r("=") + _r("K")
                + _r("×") + _sub(_r("S"), _r("rated,i")) + _r("×cosφ"))


def eq_lambda_uniform() -> str:
    """λ_i = λ_feeder × L_i / ΣL"""
    return omml(_sub(_r("λ"), _r("i")) + _r("=")
                + _sub(_r("λ"), _r("feeder"))
                + _r("×") + _frac(_sub(_r("L"), _r("i")),
                                  _r("ΣL")))


def eq_u_hours() -> str:
    """U = λ × r / 60   [h/yr]"""
    return omml(_r("U=") + _frac(_r("λ×r"), _r("60")))


def eq_ens() -> str:
    """ENS = Σ_i (λ_i / 60) · (r·P_shed,i + s·P_restored,i)   [kWh/yr]"""
    inner = (_frac(_sub(_r("λ"), _r("i")), _r("60")) + _r("·(")
             + _r("r·") + _sub(_r("P"), _r("shed,i")) + _r("+")
             + _r("s·") + _sub(_r("P"), _r("restored,i")) + _r(")"))
    return omml(_r("ENS=") + _r("Σ") + _sub(_r(""), _r("i")) + _r("(")
                + inner + _r(")"))


def eq_ep_tl() -> str:
    """EP = 100·max_i(P_shed,i)/ΣP  ;  TL = 100·max_i(P_restored,i)/ΣP"""
    return omml(_r("EP=100×")
                + _frac(_r("max") + _sub(_r(""), _r("i"))
                        + _sub(_r("P"), _r("shed,i")), _r("ΣP"))
                + _r("  ,  ") + _r("TL=100×")
                + _frac(_r("max") + _sub(_r(""), _r("i"))
                        + _sub(_r("P"), _r("restored,i")), _r("ΣP")))


def eq_rank_score() -> str:
    """Score = Σ_k w_k × x_k ,  w = (1,2,2,3,1,1)  (فرمول ۱ / جدول ۱۶)"""
    wk = _sub(_r("w"), _r("k"))
    xk = _sub(_r("x"), _r("k"))
    return omml(_r("Score=") + _r("Σ") + _sub(_r(""), _r("k"))
                + wk + _r("×") + xk + _r(" , w=(1,2,2,3,1,1)"))


def eq_ce_cn() -> str:
    """CE = 1000 × (E2 − E1)  ;  انتخاب طرح: بیشینه CE/CN"""
    return omml(_r("CE=1000×(") + _sub(_r("E"), _r("2")) + _r("−")
                + _sub(_r("E"), _r("1")) + _r(")")
                + _r("  ,  CN=") + _sub(_r("C"), _r("switches"))
                + _r("  ;  طرح: max")
                + _frac(_r("CE"), _r("CN")))


def eq_delta_ens_percent() -> str:
    """ΔENS% = 100 × (E2 − E1) / E2"""
    return omml(_r("ΔENS%=") + _r("100×")
                + _frac(_sub(_r("E"), _r("2")) + _r("−")
                        + _sub(_r("E"), _r("1")),
                        _sub(_r("E"), _r("2"))))


#: the full ordered list rendered in the report's «محاسبات کامل» section
ALL_EQUATIONS: list[tuple[str, str, str]] = [
    ("بار فیدر به روش Load Scaling — بار ظاهری",
     eq_load_scaling_s_load(),
     "S_load = √(P² + Q²)",
     "ورودی کاربر: P و Q هر فیدر (مثلاً پیک تابستان)."),
    ("ضریب توان فیدر",
     eq_load_scaling_cos_phi(),
     "φ = arctan(Q/P) ; cos φ = P / S_load",
     "φ = arctan(Q/P) و cos φ = P/S_load — هر دو هم‌ارز هستند."),
    ("ظرفیت مؤثر هر ترانس",
     eq_load_scaling_p_rated(),
     "P_rated,i = S_rated,i × cos φ",
     "ظرفیت نامی هر ترانس در ضریب توان فیدر ضرب می‌شود."),
    ("ضریب مقیاس فیدر",
     eq_load_scaling_k(),
     "K = S_load / Σ S_rated",
     "بار فیدر به نسبت ظرفیت نامی بین ترانس‌های همان فیدر تقسیم می‌شود."),
    ("بار اکتیو هر ترانس",
     eq_load_scaling_p_t(),
     "P_T,i = K × S_rated,i × cos φ",
     "جمع P_T,i روی ترانس‌های فیدر دقیقاً برابر P واردشده است."),
    ("نرخ خرابی هر قطعه",
     eq_lambda_uniform(),
     "λ_i = λ_feeder × L_i / ΣL",
     "فرض نرخ یکنواخت رابطه (۹) — آیین‌نامه TAV122-02/00."),
    ("نرخ خاموشی سالانه",
     eq_u_hours(),
     "U = λ × r / 60  [h/yr]",
     "U = λ×r/60 [ساعت در سال]."),
    ("انرژی توزیع‌نشده (ENS)",
     eq_ens(),
     "ENS = Σ_i (λ_i/60)·(r·P_shed,i + s·P_restored,i)  [kWh/yr]",
     "رابطه (۸) با بسط انتقال رابطه (۱۱): قطعه‌های قابل انتقال فقط زمان "
     "سوئیچینگ s خارج می‌شوند."),
    ("شاخص‌های EP و TL (جدول ۱۴)",
     eq_ep_tl(),
     "EP = 100×max_i(P_shed,i)/ΣP ; TL = 100×max_i(P_restored,i)/ΣP",
     "بدترین خطای تک‌زونه — معیار n-1 روش سطح اول."),
    ("امتیاز رتبه‌بندی فیدرها (فرمول ۱ / جدول ۱۶)",
     eq_rank_score(),
     "Score = Σ_k w_k × x_k , w = (1,2,2,3,1,1)",
     "وزن‌های رسمی جدول ۱۶."),
    ("مقایسه اقتصادی طرح‌ها (جدول ۱۸)",
     eq_ce_cn(),
     "CE = 1000×(E2 − E1) ; CN = هزینه کلیدها ; طرح: max(CE/CN)",
     "CE = 1000×(E2−E1)؛ E2 انرژی قبل و E1 انرژی بعد از کلیدگذاری."),
    ("درصد کاهش انرژی توزیع‌نشده",
     eq_delta_ens_percent(),
     "ΔENS% = 100×(E2 − E1) / E2",
     "معیار پذیرش طرح (نیاز ۱۰)."),
]


# ---------------------------------------------------------------------------
# فرمول‌های مطالعهٔ جایابی کلید / EENS (v1.15) — همان‌هایی که موتور اجرا می‌کند
# ---------------------------------------------------------------------------
def eq_lambda_segment() -> str:
    """λ_i = λ_feeder × L_i / ΣL"""
    return omml(_sub(_r("λ"), _r("i")) + _r("=") + _sub(_r("λ"), _r("fid"))
                + _r("×") + _frac(_sub(_r("L"), _r("i")), _r("ΣL")))


def eq_eens_uniform() -> str:
    """EENS = Σ_i (λ_i/60)·[ r·P_i + s·min(P_ok,i, C) + r·(P_ok,i − min(…)) ]"""
    inner = (_frac(_sub(_r("λ"), _r("i")), _r("60")) + _r("·[")
             + _r("r·") + _sub(_r("P"), _r("i")) + _r("+")
             + _r("s·min(") + _sub(_r("P"), _r("ok,i")) + _r(",C)+")
             + _r("r·(") + _sub(_r("P"), _r("ok,i")) + _r("−min(")
             + _sub(_r("P"), _r("ok,i")) + _r(",C))]"))
    return omml(_r("EENS=") + _r("Σ") + _sub(_r(""), _r("i")) + _r("(")
                + inner + _r(")"))


def eq_eens_directional() -> str:
    """EENS = Σ_i (λ_i/60)·[ r·P_i + s·min(P_down,i, C) + r·(P_down,i − min(…)) ]"""
    inner = (_frac(_sub(_r("λ"), _r("i")), _r("60")) + _r("·[")
             + _r("r·") + _sub(_r("P"), _r("i")) + _r("+")
             + _r("s·min(") + _sub(_r("P"), _r("down,i")) + _r(",C)+")
             + _r("r·(") + _sub(_r("P"), _r("down,i")) + _r("−min(")
             + _sub(_r("P"), _r("down,i")) + _r(",C))]"))
    return omml(_r("EENS=") + _r("Σ") + _sub(_r(""), _r("i")) + _r("(")
                + inner + _r(")"))


def eq_restoration_clamp() -> str:
    """s = min(t_restore, r)"""
    return omml(_r("s=min(") + _sub(_r("t"), _r("restore")) + _r(",")
                + _r("r)"))


def eq_eens_transient() -> str:
    """EENS_tr = Σ_i (λ_tr,i/60)·[(ΣP−P_prot)·t_tr + P_prot·(t_rec+(1−p)·t_tr)]"""
    inner = (_frac(_sub(_r("λ"), _r("tr,i")), _r("60")) + _r("·[(")
             + _r("ΣP−") + _sub(_r("P"), _r("prot")) + _r(")·")
             + _sub(_r("t"), _r("tr")) + _r("+") + _sub(_r("P"), _r("prot"))
             + _r("·(") + _sub(_r("t"), _r("rec")) + _r("+(1−p)·")
             + _sub(_r("t"), _r("tr")) + _r(")]"))
    return omml(_r("EENS") + _sub(_r(""), _r("tr")) + _r("=") + _r("Σ")
                + _sub(_r(""), _r("i")) + _r("(") + inner + _r(")"))


def eq_eens_gain() -> str:
    """ΔEENS% = 100·(EENS_base − EENS_best)/EENS_base"""
    return omml(_r("ΔEENS%=100×")
                + _frac(_sub(_r("EENS"), _r("base")) + _r("−")
                        + _sub(_r("EENS"), _r("best")),
                        _sub(_r("EENS"), _r("base"))))


def eq_outage_lambda_r() -> str:
    """λ = N_random / سال‌های پوشش ;  r = Σ t_restore / N"""
    return omml(_r("λ=") + _frac(_sub(_r("N"), _r("random")),
                                 _sub(_r("Y"), _r("covered")))
                + _r("  ,  r=") + _frac(_r("Σ") + _sub(_r("t"), _r("restore")),
                                        _sub(_r("N"), _r("events"))))


def _alleens():
    return [
        ("نرخ خرابی و زمان تعمیر از ماتریس خاموشی واقعی",
         eq_outage_lambda_r(),
         "λ = N_random / Y_covered ,  r = Σt_restore / N_events",
         "منبع: ماتریس λ/r فاز ۳ (رخدادهای تصادفی همان فیدر)."),
        ("توزیع λ بین قطعه‌ها متناسب طول",
         eq_lambda_segment(), "λ_i = λ_fid × L_i / ΣL", ""),
        ("زمان بازیابی بار سالم (clamp)",
         eq_restoration_clamp(), "s = min(t_restore, r)",
         "بار سالم هرگز دیرتر از پایان تعمیر برنمی‌گردد."),
        ("EENS — مدل یکنواخت (هم‌ارز کد مرجع)",
         eq_eens_uniform(),
         "EENS = Σ_i (λ_i/60)·[ r·P_i + s·min(P_ok,i,C) + r·(P_ok,i − min(P_ok,i,C)) ]",
         "P_ok,i = ΣP − P_i ؛ C = ظرفیت پشتیبان (نامحدود اگر وارد نشود)."),
        ("EENS — مدل جهت‌دار (فقط پایین‌دست)",
         eq_eens_directional(),
         "EENS = Σ_i (λ_i/60)·[ r·P_i + s·min(P_down,i,C) + r·(P_down,i − min(P_down,i,C)) ]",
         "بار بالادست قطعهٔ معیوب بی‌برق نمی‌شود."),
        ("EENS خطاهای گذرا (ریکلوزر)",
         eq_eens_transient(),
         "EENS_tr = Σ_i (λ_tr,i/60)·[(ΣP−P_prot)·t_tr + P_prot·(t_rec+(1−p)·t_tr)]",
         "t_rec زمان وصل مجدد و p احتمال موفقیت آن است."),
        ("کاهش EENS نسبت به حالت پایه",
         eq_eens_gain(), "ΔEENS% = 100·(EENS_base − EENS_best)/EENS_base", ""),
    ]


#: فرمول‌های مطالعهٔ EENS (عنوان، OMML، متن، یادداشت)
EENS_EQUATIONS: list[tuple[str, str, str, str]] = _alleens()
