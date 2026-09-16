# AI 降重 · 研究笔记

面向**中文学术写作降低 AIGC 检测率**的前期研究记录：拆解现有开源方案的原理，
交叉验证 AI 写作特征，收敛出可实施的架构。

目前阶段：**调研完成，待实现**。

---

## 运行

```bash
python3 -m pip install -r requirements.txt
python3 web/server.py            # 默认 8765
```

不配 LLM 也能跑，只是「两层改写」会禁用，规则层照常工作。要开第二层：

```bash
export LLM_BASE_URL="https://..."  LLM_API_KEY="sk-..."  LLM_MODEL="..."
```

界面支持三种输入：粘贴文本、上传 `.docx`、上传 `.pdf`。

- **docx**：诊断 → 修复 → **导出 docx**。导出用段落下标替换，只改文字命中的段落，
  字体、样式、图表、页眉页脚全部保留。
- **pdf**：只做诊断，不提供导出——PDF 存的是字形坐标而不是段落，没有可靠的回写路径。
  定位到问题后回原始 Word 文件修改。

## 结论速览

- **五份资料，零个实现了度量。** 所有现存方案都知道该看句长方差、困惑度、词汇多样性，
  但没有一个真的去算——全部靠 LLM 目测或人工手感。这是当前的空位。
- **病根是"回归均值"**：LLM 输出趋向统计上最普适的表达，把罕见的具体事实
  抹成常见的笼统褒扬，于是文本同时变得**更不具体**且**更夸张**。
- **推论**：最有效且最鲁棒的手段是**恢复具体性**，而非换同义词；
  而具体信息只能来自作者，不能由模型生成 → 必须做成人机交互。
- **目标函数不是 minimize，是 match distribution**：把 AI 特征清到 0 会造成
  新的均质化异常，需要保留"噪声预算"。

---

## 笔记索引

| 文件 | 内容 |
|---|---|
| [00-降AI率-原理与思路.md](研究笔记/00-降AI率-原理与思路.md) | **主文档**：检测器工作原理、三个杠杆、LLM 改写悖论、架构与实施顺序 |
| [00-原理与架构总纲.md](研究笔记/00-原理与架构总纲.md) | 早期总纲，含"降查重 vs 降 AI 率"的目标冲突分析 |
| [01-维基-AI写作特征.md](研究笔记/01-维基-AI写作特征.md) | Wikipedia《Signs of AI writing》拆解：特征学、人类写作正向特征、无效指标 |
| [02-BypassAIGC-原理拆解.md](研究笔记/02-BypassAIGC-原理拆解.md) | 分段两遍 LLM 改写流水线；中文 AI 腔黑名单；自激风险 |
| [03-thesis-optimizer-原理拆解.md](研究笔记/03-thesis-optimizer-原理拆解.md) | 两层文档工作流；6 大类 30+ 模式分类学；结构性 AI 味 |
| [04-AIGC-Detector-Pro-原理拆解.md](研究笔记/04-AIGC-Detector-Pro-原理拆解.md) | 检测技术分类；5 维加权评分；**首批可计算阈值** |
| [05-humanizer-zh-academic-原理拆解.md](研究笔记/05-humanizer-zh-academic-原理拆解.md) | **噪声预算**（原创洞察）；数值化硬约束；确定性段落打分法 |

---

## 研究对象

以下项目**未包含在本仓库**（各自是独立的 git 仓库），需自行 clone 到本目录：

```bash
git clone https://github.com/chi111i/BypassAIGC.git
git clone https://github.com/Haimbeau1o/thesis-optimizer.git
git clone https://github.com/free-revalution/AIGC-Detector-Pro.git
git clone https://github.com/redbaronyyyyy-eng/humanizer-zh-academic.git
```

维基指南原文快照（笔记 01 的分析对象）可用以下命令重新抓取：

```bash
curl -sL "https://en.wikipedia.org/wiki/Special:Export/Wikipedia:Signs_of_AI_writing" \
  -o 研究笔记/signs-of-ai-writing.xml
```

---

## 信源独立性说明

做交叉验证时需注意：**humanizer-zh-academic 与 thesis-optimizer 都二次引用了维基指南**，
它们命中的多数特征并非独立确认。真正相互独立的信源是三个：

1. **Wikipedia: Signs of AI writing** —— 英文语料的长期人工观察
2. **BypassAIGC** —— 中文场景的工程实践
3. **AIGC-Detector-Pro** —— 检测技术文献综述

---

## 下一步

1. 合并两套规格（AIGC-Detector-Pro 的统计阈值 + humanizer-zh-academic 的规则上限）
   为一份可执行指标清单
2. 实现诊断引擎（规则层 + 统计层，先不含 LLM）
3. 采集 2022-11 之前的中文论文语料作为人类正样本，标定阈值
4. 本地小模型计算困惑度
5. 改写层（代码优先，LLM 兜底）+ 验证闭环

---

## 声明

- 本仓库为技术研究记录，不含可运行的改写工具。
- 对第三方项目的分析基于其公开源码，指出的问题仅针对技术方案本身。
- 研究立场：**内容（事实、数据、文献、主观判断）应由作者提供，模型只做识别、
  提示与结构改写**，不生成未经作者确认的研究内容。
