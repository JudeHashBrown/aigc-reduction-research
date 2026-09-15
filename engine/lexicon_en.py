"""英文学术 AI 高频词表。

主要来源：Wikipedia《Signs of AI writing》的 AI vocabulary 分代词表
（该页是英文语料的长期人工观察，是五份资料里英文侧最权威的一份），
补以 AIGC-Detector-Pro 的 English AI Characteristics 一节。

维基强调的一条必须遵守：**要按字面理解，某词被 AI 滥用不代表其同义词也被滥用。**
所以这里只收录被明确观察到的词，不做同义扩展。
"""

# T1：跨时代稳定的强标记
T1 = [
    "delve", "delves", "delved", "delving", "tapestry", "testament", "underscore", "underscores",
    "underscoring", "underscored", "pivotal", "showcase", "showcases",
    "showcasing", "showcased", "boasts", "meticulous", "meticulously", "intricate",
    "intricacies", "vibrant", "bolster", "bolstered", "garner", "garnered",
    "interplay", "realm", "myriad", "paradigm shift", "groundbreaking",
    "indelible", "unwavering", "profound implications", "ever-evolving",
    "at the forefront", "plays a crucial role", "plays a vital role",
    "plays a pivotal role", "is a testament to", "stands as a testament",
    "navigating the complexities", "in today's fast-paced",
]

# T2：AI 明显更密，但人类也用
T2 = [
    "crucial", "enduring", "leverage", "leveraging", "robust", "nuanced",
    "comprehensive", "novel", "paramount", "facilitate", "facilitates",
    "utilize", "utilizing", "utilization", "demonstrate", "demonstrates",
    "significantly", "effectively", "enhance", "enhances", "enhancing",
    "foster", "fosters", "fostering", "align with", "aligns with",
    "aligned with", "highlight", "highlights", "highlighting",
    "emphasize", "emphasizes", "emphasizing", "landscape", "valuable insights",
    "additionally", "furthermore", "moreover", "notably", "consequently",
    "in conclusion", "overall", "it is worth noting", "it is important to note",
    "it should be emphasized", "it could be argued that",
]

# T3：正常词，仅在密度异常时计分
T3 = [
    "however", "therefore", "thus", "hence", "while", "although",
    "various", "numerous", "several", "key", "essential", "significant",
    "approach", "framework", "mechanism", "perspective", "dimension",
]

# 对冲词（AIGC-Detector-Pro：密度 >6% 可疑，人类 <3%）
HEDGES = [
    "arguably", "to some extent", "may suggest", "might suggest",
    "could potentially", "it is possible that", "relatively", "somewhat",
    "generally speaking", "in some cases", "to a certain degree",
    "appears to", "seems to", "tends to",
]

WEIGHTS = {"T1": 3.0, "T2": 1.5, "T3": 0.3}
T3_DENSITY_FLOOR = 0.35
PARA_VOCAB_LIMIT = 2

# 维基 §Signs of human writing：人类更常用朴素动词，AI 偏好文绉绉的同义词
SUGGEST = {
    "utilize": "use", "utilizing": "using", "utilization": "use",
    "facilitate": "help", "facilitates": "helps",
    "demonstrate": "show", "demonstrates": "shows",
    "leverage": "use", "leveraging": "using",
    "commence": "start", "endeavor": "try", "authored": "wrote",
    "relocated": "moved", "attempted": "tried", "obtained": "got",
    "delve": "look at", "delving": "looking at",
    "showcase": "show", "showcases": "shows",
    "underscore": "show", "underscores": "shows",
    "delves": "looks at", "delved": "looked at",
    "showcasing": "showing", "showcased": "showed",
    "underscoring": "showing", "underscored": "showed",
    "boasts": "has", "garner": "get", "garnered": "got",
    "bolster": "support", "bolstered": "supported",
    "foster": "support", "fosters": "supports", "fostering": "supporting",
    "enhance": "improve", "enhances": "improves", "enhancing": "improving",
    "highlight": "show", "highlights": "shows", "highlighting": "showing",
    "emphasize": "stress", "emphasizes": "stresses", "emphasizing": "stressing",
    "align with": "match", "aligns with": "matches", "aligned with": "matched",
    "meticulous": "careful", "meticulously": "carefully",
    "intricate": "complex", "intricacies": "details",
    "pivotal": "key", "crucial": "key", "paramount": "central",
    "robust": "reliable", "nuanced": "detailed", "comprehensive": "broad",
    "vibrant": "active", "enduring": "lasting", "myriad": "many",
    "realm": "area", "landscape": "field", "interplay": "interaction",
    "groundbreaking": "new", "novel": "new", "tapestry": "mix",
    "significantly": "clearly", "effectively": "well",
    "plays a crucial role": "matters", "plays a vital role": "matters",
    "plays a pivotal role": "matters", "is a testament to": "shows",
    "stands as a testament": "shows",
    "additionally": None, "furthermore": None, "moreover": None,
    "in conclusion": None, "it is worth noting": None,
    "it is important to note": None, "notably": None,
}

# 只有这些是「删掉不伤语法」的：句首过渡词、可有可无的副词。
# 其余一律走替换——英文删掉动词或分词会直接把句子弄断，
# 而语法错误本身就是另一种可检测的异常，比原来的 AI 味更糟。
DELETABLE = {
    "additionally", "furthermore", "moreover", "notably", "consequently",
    "in conclusion", "overall", "it is worth noting", "it is important to note",
    "it should be emphasized", "it could be argued that", "arguably",
    "valuable insights", "in today's fast-paced", "at the forefront",
}

_T1 = {w.lower() for w in T1}
_T2 = {w.lower() for w in T2}
ALL_TERMS = T1 + T2 + T3


def tier_of(word: str) -> str:
    w = word.lower()
    if w in _T1:
        return "T1"
    if w in _T2:
        return "T2"
    return "T3"
