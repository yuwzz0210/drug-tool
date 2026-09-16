# -*- coding: utf-8 -*-
"""病种/治疗领域分类规则（v1，可审计、可扩展）。

设计原则：
- **只依据既有文本**（说明书适应症 / 目录适应症短句），不引入外部推测；
- 规则命中即给出 治疗领域 + 病种 + 亚型，并标明命中关键词与置信度；
- 亚型（sub_disease）只在国内已上市说明书可判定的维度上标注；
- 规则表与前端 DISEASE_TREE 的领域/病种命名保持一致，便于联动筛选。

置信度口径：
- 高：命中药监/企业官方说明书适应症原文（drug_leaflet.indications）
- 中：仅命中结构化适应症短句（drug_indication.indication_text）
- 低：仅命中治疗领域级关键词（无法定位具体病种）
"""
import re

from normalize import norm_roman, to_half_width

RULES_VERSION = "规则:适应症关键词 v1"

# 亚型规则：与病种绑定，(标签, 正则)
SUB_RULES = {
    "肺癌": (
        ("EGFR突变", r"EGFR|外显子\s*19|外显子\s*21|L858R|T790M|19del"),
        ("ALK融合", r"ALK"),
        ("ROS1融合", r"ROS1"),
        ("KRAS突变", r"KRAS"),
        ("鳞癌", r"鳞癌|肺鳞"),
        ("腺癌", r"腺癌|肺腺"),
        ("小细胞肺癌", r"(?<!非)小细胞肺癌|(?<!N)SCLC"),
    ),
    "乳腺癌": (
        ("HER2阳性", r"HER2|ERBB2"),
        ("三阴性乳腺癌", r"三阴性|TNBC"),
        ("HR阳性/HER2阴性", r"激素受体阳性|HR阳性"),
        ("BRCA突变", r"BRCA"),
    ),
    "结直肠癌": (
        ("MSI-H/dMMR", r"MSI-?H|dMMR|错配修复"),
        ("RAS/BRAF突变", r"\bRAS\b|BRAF|KRAS"),
        ("HER2扩增", r"HER2"),
    ),
    "胃癌": (
        ("HER2阳性", r"HER2"),
        ("PD-L1阳性(CPS≥1)", r"PD-?L1|CPS"),
        ("CLDN18.2阳性", r"CLDN18"),
        ("MSI-H", r"MSI-?H|dMMR"),
    ),
    "肝癌": (
        ("HBV相关", r"乙型肝炎|HBV|乙肝"),
        ("非病毒性", r"非病毒"),
    ),
    "食管癌": (
        ("鳞癌", r"鳞癌"),
        ("腺癌", r"腺癌"),
    ),
    "白血病": (
        ("慢粒CML", r"CML|慢性髓|慢性粒"),
        ("急淋ALL", r"\bALL\b|急性淋巴"),
        ("急髓AML", r"\bAML\b|急性髓"),
        ("慢淋CLL", r"CLL|慢性淋巴"),
    ),
    "淋巴瘤": (
        ("霍奇金淋巴瘤", r"霍奇金"),
        ("B细胞淋巴瘤", r"B细胞|弥漫大B|DLBCL"),
        ("T细胞淋巴瘤", r"T细胞"),
    ),
    "前列腺癌": (
        ("去势抵抗性", r"去势抵抗|CRPC"),
        ("激素敏感性", r"激素敏感|mHSPC"),
    ),
    "甲状腺癌": (
        ("髓样癌", r"髓样癌|MTC"),
        ("乳头状癌", r"乳头状癌|PTC"),
        ("未分化癌", r"未分化癌|ATC"),
    ),
    "肾细胞癌": (
        ("透明细胞型", r"透明细胞"),
        ("非透明细胞型", r"非透明细胞"),
    ),
    "2型糖尿病": (
        ("伴心肾获益证据", r"心血管|心衰|肾脏|慢性肾脏病"),
        ("胰岛素联合治疗", r"胰岛素"),
    ),
    "肥胖症": (
        ("伴代谢综合征", r"代谢综合征|代谢异常"),
        ("单纯性肥胖", r"单纯性肥胖"),
    ),
    "慢性肾脏病": (
        ("糖尿病肾病", r"糖尿病肾病"),
        ("IgA肾病", r"IgA肾病"),
        ("高血压肾病", r"高血压肾病"),
    ),
    "类风湿关节炎": (
        ("中重度活动性", r"中重度|中度至重度|活动性"),
    ),
    "银屑病": (
        ("中重度斑块状银屑病", r"中重度|中度至重度|斑块"),
        ("银屑病关节炎", r"银屑病关节炎"),
    ),
    "强直性脊柱炎": (
        ("活动性", r"活动性"),
    ),
    "炎症性肠病": (
        ("克罗恩病", r"克罗恩"),
        ("溃疡性结肠炎", r"溃疡性结肠炎"),
    ),
    "特应性皮炎": (
        ("中重度", r"中重度|中度至重度"),
    ),
    "血友病A": (
        ("伴抑制物", r"抑制物"),
        ("不伴抑制物", r"不伴抑制物"),
    ),
    "脊髓性肌萎缩症(SMA)": (
        ("婴儿型", r"婴儿型|I型|1型"),
        ("迟发型", r"迟发型|II型|III型|2型|3型"),
    ),
    "阵发性睡眠性血红蛋白尿症(PNH)": (
        ("未接受过补体抑制剂", r"未接受过补体抑制剂"),
        ("经治", r"经治|既往接受"),
    ),
    "多发性硬化": (
        ("复发缓解型", r"复发缓解|RRMS"),
        ("继发进展型", r"继发进展|SPMS"),
    ),
}

# 病种规则：顺序即优先级；正则不区分大小写、对 ASCII 已转大写后再匹配
DISEASE_RULES = (
    # ---------- 肿瘤 ----------
    ("肿瘤", "肺癌",
     r"非小细胞肺癌|NSCLC|小细胞肺癌|SCLC|肺腺癌|肺鳞癌|肺癌"),
    ("肿瘤", "乳腺癌", r"乳腺癌|乳腺恶性肿瘤"),
    ("肿瘤", "结直肠癌", r"结直肠癌|结肠癌|直肠癌|大肠癌"),
    ("肿瘤", "胃癌", r"胃癌|胃腺癌|胃食管结合部|胃食管交界"),
    ("肿瘤", "肝癌", r"肝癌|肝细胞癌|HCC"),
    ("肿瘤", "食管癌", r"食管癌|食管鳞癌"),
    ("肿瘤", "宫颈癌", r"宫颈癌"),
    ("肿瘤", "卵巢癌", r"卵巢癌|输卵管癌|腹膜癌"),
    ("肿瘤", "甲状腺癌", r"甲状腺癌"),
    ("肿瘤", "前列腺癌", r"前列腺癌"),
    ("肿瘤", "肾细胞癌", r"肾细胞癌|肾癌"),
    ("肿瘤", "胰腺癌", r"胰腺癌|胰腺神经内分泌"),
    ("肿瘤", "膀胱癌", r"尿路上皮癌|膀胱癌"),
    ("肿瘤", "淋巴瘤", r"(?:^|[^性])淋巴瘤"),
    ("肿瘤", "白血病", r"白血病"),
    ("肿瘤", "多发性骨髓瘤", r"多发性骨髓瘤|骨髓瘤"),
    ("肿瘤", "黑色素瘤", r"黑色素瘤"),
    ("肿瘤", "头颈部鳞癌", r"头颈部鳞癌|鼻咽癌"),
    ("肿瘤", "神经胶质瘤", r"胶质瘤|胶质母细胞瘤|GBM"),
    # ---------- 代谢 / 内分泌 ----------
    ("代谢", "2型糖尿病",
     r"2\s*型糖尿病|II\s*型糖尿病|非胰岛素依赖型糖尿病"),
    ("代谢", "1型糖尿病", r"1\s*型糖尿病|I\s*型糖尿病"),
    ("代谢", "肥胖症", r"肥胖|体重管理|减重"),
    ("心血管", "高胆固醇血症", r"高胆固醇血症|高脂血症|血脂异常|LDL-?C"),
    ("心血管", "高血压", r"高血压"),
    ("心血管", "心力衰竭", r"心力衰竭|心衰|HFrEF|HFpEF"),
    ("心血管", "冠心病", r"冠心病|心绞痛|急性冠脉综合征"),
    ("代谢", "慢性肾脏病", r"慢性肾脏病|糖尿病肾病|IgA肾病|肾功能不全"),
    ("代谢", "高尿酸血症/痛风", r"痛风|高尿酸"),
    ("代谢", "骨质疏松", r"骨质疏松"),
    # ---------- 自免疫 ----------
    ("自免疫", "类风湿关节炎", r"类风湿关节炎|\bRA\b"),
    ("自免疫", "银屑病", r"银屑病|斑块状"),
    ("自免疫", "强直性脊柱炎", r"强直性脊柱炎"),
    ("自免疫", "炎症性肠病", r"克罗恩|溃疡性结肠炎|炎症性肠病"),
    ("自免疫", "系统性红斑狼疮", r"系统性红斑狼疮|\bSLE\b"),
    ("自免疫", "特应性皮炎", r"特应性皮炎"),
    ("自免疫", "幼年特发性关节炎", r"幼年特发性关节炎|\bJIA\b"),
    ("自免疫", "重症肌无力", r"重症肌无力"),
    # ---------- 罕见病 ----------
    ("罕见病", "脊髓性肌萎缩症(SMA)", r"SMA|脊髓性肌萎缩|5Q"),
    ("罕见病", "血友病A", r"血友病|凝血因子VIII|凝血因子Ⅷ"),
    ("罕见病", "阵发性睡眠性血红蛋白尿症(PNH)",
     r"阵发性睡眠性血红蛋白尿|\bPNH\b"),
    ("罕见病", "非典型溶血尿毒症综合征", r"非典型溶血尿毒症|AHUS"),
    ("罕见病", "Wilson病(肝豆状核变性)", r"WILSON|肝豆状核变性"),
    ("罕见病", "多发性硬化", r"多发性硬化"),
    ("罕见病", "法布雷病", r"法布雷"),
    ("罕见病", "戈谢病", r"戈谢"),
    # ---------- 感染 ----------
    ("感染", "COVID-19", r"COVID|新型冠状病毒|新冠"),
    ("感染", "细菌感染", r"细菌感染|抗菌|革兰"),
    ("感染", "真菌感染", r"真菌感染|念珠菌|曲霉"),
    ("感染", "病毒感染", r"病毒感染|抗病毒|乙型肝炎|丙型肝炎"),
    # ---------- 其他系统 ----------
    ("呼吸", "哮喘", r"哮喘"),
    ("呼吸", "慢性阻塞性肺疾病", r"慢性阻塞性肺疾病|COPD"),
    ("消化", "消化性溃疡", r"消化性溃疡|胃溃疡|十二指肠溃疡"),
    ("消化", "胃食管反流病", r"胃食管反流|反流性食管炎"),
    ("消化", "幽门螺杆菌感染", r"幽门螺杆菌|H\.?\s*PYLORI"),
    ("神经", "癫痫", r"癫痫"),
    ("神经", "阿尔茨海默病", r"阿尔茨海默"),
    ("神经", "帕金森病", r"帕金森"),
    ("精神", "抑郁症", r"抑郁"),
    ("精神", "精神分裂症", r"精神分裂"),
    ("泌尿", "良性前列腺增生", r"前列腺增生"),
    ("皮肤", "荨麻疹", r"荨麻疹"),
    ("眼科", "黄斑变性", r"黄斑变性|AMD"),
)

# 治疗领域级兜底规则（无法定位病种时使用）
AREA_RULES = (
    ("肿瘤", r"肿瘤|癌|瘤|白血病|淋巴瘤|化疗|抗肿瘤"),
    ("代谢", r"糖尿病|血糖|代谢|肥胖|尿酸"),
    ("心血管", r"血压|血脂|胆固醇|心血管|心脏"),
    ("自免疫", r"免疫|风湿|关节炎|炎症"),
    ("罕见病", r"罕见病|孤儿药"),
    ("感染", r"感染|抗菌|抗生素|病毒|细菌|真菌"),
    ("呼吸", r"呼吸|哮喘|肺气肿|支气管"),
    ("消化", r"胃|肠|肝|消化|腹泻|便秘|食管"),
    ("神经", r"神经|癫痫|痴呆|帕金森|头痛|偏头痛"),
    ("精神", r"精神|抑郁|焦虑|分裂"),
    ("泌尿", r"泌尿|前列腺|膀胱|肾"),
    ("血液", r"贫血|血小板|凝血|血友病"),
    ("眼科", r"眼|视网膜|青光眼|结膜"),
    ("皮肤", r"皮肤|皮炎|湿疹|银屑病|痤疮"),
)

# 药名词干（INN stem）推定规则：中文通用名命名规范中的固定词干，
# 仅在无可用适应症文本时使用，置信度固定为「低」，来源标记 inn_stem。
INN_STEM_RULES = (
    ("代谢", "2型糖尿病", r"二甲双胍|格列本脲|格列齐特|格列吡嗪|格列美脲|"
                          r"格列喹酮|列汀|列净|瑞格列奈|那格列奈"),
    ("代谢", "2型糖尿病", r"胰岛素|德谷|甘精|门冬|赖脯|利司那肽|度拉糖肽|"
                          r"司美格鲁肽|利拉鲁肽|替尔泊肽|贝那鲁肽"),
    ("心血管", "高胆固醇血症", r"他汀|依折麦布|贝特类?"),
    ("心血管", "高血压", r"氨氯地平|硝苯地平|缬沙坦|氯沙坦|厄贝沙坦|"
                          r"培哚普利|依那普利|美托洛尔|比索洛尔"),
    ("罕见病", "血友病A", r"凝血因子"),
)

_INN_RE = tuple(
    (area, disease, re.compile(pat, re.I)) for area, disease, pat in INN_STEM_RULES
)

_SUB_RE = {
    disease: tuple((label, re.compile(pat, re.I)) for label, pat in rules)
    for disease, rules in SUB_RULES.items()
}
_DISEASE_RE = tuple(
    (area, disease, re.compile(pat, re.I))
    for area, disease, pat in DISEASE_RULES
)
_AREA_RE = tuple(
    (area, re.compile(pat, re.I)) for area, pat in AREA_RULES
)

# 否定语境：命中位置前若干字符出现下列词时，该次命中不计入
NEGATION_WORDS = ("不适用于", "不用于", "不推荐", "不宜用于", "不适用",
                  "禁用", "不适合", "不可用于", "除外", "尚未", "未获批")
NEGATION_WINDOW = 10


def normalize_text(text):
    """规则匹配前的文本归一：全角→半角、罗马数字统一、压缩空白、ASCII 大写。"""
    if not text:
        return ""
    t = norm_roman(to_half_width(str(text)))
    t = re.sub(r"[\s\u3000]+", " ", t)
    return t.upper()


def _is_negated(text, start):
    """命中位置前 NEGATION_WINDOW 字符内是否出现否定词。"""
    left = text[max(0, start - NEGATION_WINDOW):start]
    return any(word in left for word in NEGATION_WORDS)


def _effective_matches(text, pattern):
    """返回未被否定语境排除的命中位置列表。"""
    return [m.start() for m in pattern.finditer(text)
            if not _is_negated(text, m.start())]


# 说明书「适应症」段落可用性判定：部分 PDF 抽取到的是不良反应/注意事项段落，
# 这类文本会带来系统性误判，直接弃用并回退到目录适应症短句。
_INDICATION_MARKERS = re.compile(r"适应症|适用于|用于")
_NON_INDICATION_MARKERS = re.compile(
    r"不良反应|上市后报告|临床试验经验|警告和注意|禁忌|药物过量|"
    r"药理毒理|药代动力学|贮藏")


def is_indication_section(text):
    """判断一段说明书文本是否为可用的「适应症」段落。"""
    if not text or len(text.strip()) < 6:
        return False
    t = normalize_text(text)
    if _NON_INDICATION_MARKERS.search(t):
        return False
    return bool(_INDICATION_MARKERS.search(t))


def is_clean_text(text):
    """判断一段文本是否不含整段错抽的段落标记（适用于结构化适应症短句）。

    部分 drug_indication 记录实际存入了说明书的不良反应/注意事项段落，
    这类文本一律不参与分类。
    """
    if not text:
        return False
    return not _NON_INDICATION_MARKERS.search(normalize_text(text))


def classify_by_name(generic_name):
    """无可用适应症文本时，按药名词干（命名规范）推定领域/病种，置信度固定为低。"""
    t = normalize_text(generic_name)
    if not t:
        return {"area": "", "disease": "", "sub_disease": "",
                "confidence": "", "hits": [], "version": RULES_VERSION}
    for area, disease, pattern in _INN_RE:
        if pattern.search(t):
            return {"area": area, "disease": disease, "sub_disease": "",
                    "confidence": "低", "hits": [pattern.pattern],
                    "version": RULES_VERSION}
    return {"area": "", "disease": "", "sub_disease": "",
            "confidence": "", "hits": [], "version": RULES_VERSION}


# 国家医保药品编码内嵌 ATC：形如 XB05BAZ109B...，第 2 位起为 ATC 码（B05BA）。
# 这里把 ATC 前 3~4 位映射到本项目的治疗领域命名，用于没有说明书文本的品种。
ATC_L1_AREA = {
    "A": "代谢",   # 消化道和代谢（A10 糖尿病用药为主，细分见下）
    "B": "血液",   # 血液和血液形成器官
    "C": "心血管",  # 心血管系统
    "D": "皮肤",   # 皮肤病用药
    "G": "泌尿",   # 泌尿生殖系统及性激素
    "H": "代谢",   # 系统用激素制剂（不含性激素）
    "J": "感染",   # 全身用抗感染药
    "L": "肿瘤",   # 抗肿瘤药及免疫调节剂
    "M": "肌肉骨骼",  # 肌肉骨骼系统
    "N": "神经",   # 神经系统
    "P": "感染",   # 抗寄生虫药
    "R": "呼吸",   # 呼吸系统
    "S": "眼科",   # 感觉器官
    "V": "其他",
}

# 更细的二级覆盖（ATC 前 4 位 = L1+L2）
ATC_L2_AREA = {
    "A02": "消化", "A03": "消化", "A04": "消化", "A06": "消化",
    "A07": "消化", "A09": "消化", "A16": "消化",
    "A10": "代谢", "A11": "其他", "A12": "其他",
    "C01": "心血管", "C02": "心血管", "C03": "心血管", "C07": "心血管",
    "C08": "心血管", "C09": "心血管", "C10": "心血管",
    "D01": "皮肤", "D02": "皮肤", "D03": "皮肤", "D04": "皮肤",
    "D05": "皮肤", "D06": "皮肤", "D07": "皮肤", "D10": "皮肤", "D11": "皮肤",
    "G01": "泌尿", "G02": "泌尿", "G03": "代谢", "G04": "泌尿",
    "J01": "感染", "J02": "感染", "J04": "感染", "J05": "感染",
    "J06": "感染", "J07": "感染",
    "L01": "肿瘤", "L02": "肿瘤", "L03": "肿瘤", "L04": "自免疫",
    "M01": "肌肉骨骼", "M02": "肌肉骨骼", "M03": "肌肉骨骼",
    "M04": "代谢", "M05": "代谢",
    "N01": "神经", "N02": "神经", "N03": "神经", "N04": "神经",
    "N05": "精神", "N06": "精神", "N07": "神经",
    "R01": "呼吸", "R02": "呼吸", "R03": "呼吸", "R05": "呼吸",
    "R06": "呼吸", "R07": "呼吸",
    "S01": "眼科", "S02": "眼科", "S03": "眼科",
    "B01": "血液", "B02": "血液", "B03": "血液", "B05": "代谢",
}


def atc_from_drug_code(code):
    """从国家医保药品编码中取 ATC 码（如 XB05BAZ109B... → B05BA）。"""
    if not code:
        return ""
    t = re.sub(r"[\s\u3000]+", "", str(code)).upper()
    if len(t) < 6:
        return ""
    # 统一编码以 X 开头（X + ATC + 剂型/规格编码）
    body = t[1:] if t.startswith("X") else t
    if not re.match(r"^[A-Z]\d{2}[A-Z]{2}", body):
        return ""
    return body[:5]


def area_from_drug_code(code):
    """按医保编码内嵌 ATC 推断治疗领域；无法判定返回空串。"""
    atc = atc_from_drug_code(code)
    if not atc:
        return "", ""
    area = ATC_L2_AREA.get(atc[:3]) or ATC_L1_AREA.get(atc[0], "")
    return area, atc


def classify(text, official=False):
    """按规则识别治疗领域/病种/亚型。

    排序口径：**首个适应症优先**（说明书适应症按 1/2/3 编号，首条为主适应症），
    同位置时按命中次数多少排序；否定/限制语境中的命中（如"不适用于1型糖尿病"）
    直接剔除。

    Args:
        text: 适应症文本（说明书适应症或目录适应症短句，可多段拼接）。
        official: True 表示文本来自官方说明书适应症原文（置信度更高）。

    Returns:
        dict: area / disease / sub_disease / confidence / hits / version；
        无任何命中时 area、disease 为空字符串。
    """
    t = normalize_text(text)
    if not t:
        return {"area": "", "disease": "", "sub_disease": "",
                "confidence": "", "hits": [], "version": RULES_VERSION}

    hit_counts = []
    for area, disease, pattern in _DISEASE_RE:
        positions = _effective_matches(t, pattern)
        if positions:
            hit_counts.append((min(positions), len(positions), area, disease))
    hits = [d for _, _, _, d in sorted(hit_counts,
                                       key=lambda x: (x[0], -x[1]))]

    if hit_counts:
        hit_counts.sort(key=lambda x: (x[0], -x[1]))
        first_pos, _, area, disease = hit_counts[0]
        sub = ""
        for label, pattern in _SUB_RE.get(disease, ()):
            positions = _effective_matches(t, pattern)
            # 亚型需与主病种同一语境（就近 ±120 字符），避免跨适应症误挂
            if any(abs(p - first_pos) <= 120 for p in positions):
                sub = label
                break
        confidence = "高" if official else "中"
        # 多病种命中时保留主病种，其余记入 hits 供审计
        return {"area": area, "disease": disease, "sub_disease": sub,
                "confidence": confidence, "hits": hits,
                "version": RULES_VERSION}

    for area, pattern in _AREA_RE:
        if _effective_matches(t, pattern):
            return {"area": area, "disease": "", "sub_disease": "",
                    "confidence": "低", "hits": [area],
                    "version": RULES_VERSION}

    return {"area": "", "disease": "", "sub_disease": "",
            "confidence": "", "hits": [], "version": RULES_VERSION}
