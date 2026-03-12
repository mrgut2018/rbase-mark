from deepsearcher.agent.classifier_value_process import markdown_table_tr
from deepsearcher.rbase.ai_models import Classifier, ClassifierValue

GENERAL_VALUE_CLASSIFIER_PROMPT = """
你正在做一个对学术文章的{classify_name}进行分类的工作，分类可以{purpose}。

做这个分类的目标在于{target}。

执行分类时需要注意的原则：{principle}。

执行分类时的规范：{criterion}。

分类的取值表及每个取值的说明如下：
{value_table}


==============================================================
你正在对文章{article_title}进行分类处理，请根据文章的内容，给出分类结果。

文章标题：{article_title}

发表期刊：{article_journal_name}

文章摘要：{article_summary}

文章关键词：{article_keywords}

{article_full_text}

==============================================================

{output_requirement}
"""

GENERAL_VALUE_MERGED_CLASSIFIER_PROMPT = """
你正在做一个对学术文章的进行分类的工作，需要完成以下几项分类工作：
{classifier_descriptions}

==============================================================
你正在对下面的文章进行分类处理，请根据文章的内容，给出分类结果。

文章标题：{article_title}

发表期刊：{article_journal_name}

文章摘要：{article_summary}

文章关键词：{article_keywords}

{article_full_text}

==============================================================

{output_requirement}
"""

GENERAL_VALUE_DESC_PROMPT = """
{seq}. 分类器名称: {classifier_name}, classifier_alias: {classifier_alias} {prerequisite}。 
分类器用于{purpose}，做这个分类的目标在于{target}, {principle}, {criterion}。 {multiple_result_requirement}，分类的取值表及每个取值的说明如下：
{value_table}

"""

NAMED_ENTITY_CLASSIFIER_PROMPT = """
{purpose}

{target}

{criterion}

{principle}

==============================================================

Now, read the literature and output ONLY the structured metadata and Self-Correction Log. Begin immediately.

Article Title: {article_title}

Article Abstract: {article_summary}

Article Keywords: {article_keywords}

{article_full_text}

==============================================================

{output_requirement}
"""

NAMED_ENTITY_RECHECK_CLASSIFIER_PROMPT = """
对于命名实体{value}，得到了1个或多个实体名称返回的结果，有些结果是相同的，但实体名称的分类路径可能不同，具体实体名称及其分类路径如下：

| classsifier_value_id | 实体名称(entity_name) | 分类路径(route_path) |
| :--- | :--- | :--- |
{value_route_table}

请根据文章内容返回与文章相关的实体名称及分类路径做以下判断：
1. 实体名称是否在文章中有出现，并且是否属于重要的研究对象，具体的原则：
  A. 角色判断 (Role-Based Judgment)：必须判断实体在研究中扮演的角色。
    -- “主角” (Subject of Study): 实体是研究的主要对象。例如：论文研究“阿司匹林对结肠癌的预防作用”，则阿司匹林和结肠癌是主角）。
    -- “工具” (Tool/Medium): 实体仅用于实现研究过程。例如：实验使用“葡聚糖硫酸钠”作为结肠炎动物模型造模的诱导药物，此时葡聚糖硫酸钠是工具，而非主角。
    -- “背景” (Background): 实体仅用于提供上下文。例如：引言中提到“阿司匹林是常用的抗炎药，而我们研究的是XX”，此时阿司匹林是背景。
    
    **提取策略：只提取扮演“主角”角色的实体。**
  B. 位置优先 (Location Priority)
    -- 高优先级：论文 标题 (Title) 、 摘要 (Abstract)（尤其是摘要的结论部分）和 论文自带关键词（Keywords）中提到的实体，几乎总是核心实体。必须不能遗漏。
    -- 中优先级：结论 (Conclusion) 和 结果 (Results) 部分（如图表标题、关键结果描述）中用于描述主要发现的实体。
    -- 低优先级：引言 (Introduction) 中用于阐明“本文研究...”或“研究目的...”的实体。
    
    **提取策略：符合上述三个优先级的实体都应提取。**
    通常应舍弃: 仅在 方法 (Methods) 部分作为工具、试剂、缓冲液或标准流程提到的实体（例如，用于染色的“DAPI”、缓冲液“PBS”）。
    通常应舍弃: 仅在 讨论 (Discussion) 部分用于“与...研究相比”的背景比较实体。
2. 找出列表中在符合上述两个原则的实体名称所对应的classifier_value_id，如有多项均符合则返回所有符合项。

**输出格式要求**：
1. **仅**返回一个JSON数组。不要包含任何额外的解释或文字。
2. 数组中的每个对象必须包含且仅包含以下三个键：
   - "classifier_value_id": 分类路径的classifier_value_id。
   - "entity_name": 实体名称。
   - "route_path": 分类路径。

期望输出JSON：
[
  {{
    "classifier_value_id": 1,
    "entity_name": "Child A",
    "route_path": "Parent A -> Child A"
  }},
  {{
    "classifier_value_id": 2,
    "entity_name": "Child C",
    "route_path": "Parent B -> Child B -> Child C"
  }}
]

==============================================================

请开始对文章{article_title}进行命名实体重新审查处理，请根据文章的标题、摘要、关键词、正文（如果用户提供全文）等内容，给出命名实体重新审查结果。

文章标题：{article_title}

文章摘要：{article_summary}

文章关键词：{article_keywords}

{article_full_text}

==============================================================

请以严格的上面提供的JSON格式返回结果，不要返回任何辅助性文字。
"""

NAMED_ENTITY_RECHECK_WITH_CONTEXT_PROMPT = """
对于从文章中提取的命名实体"{entity_name}"，在词库中找到了以下可能匹配的候选词条：

| classifier_value_id | 词条名称 | 分类路径 | 语义相似度距离 |
| :--- | :--- | :--- | :--- |
{candidates_table}

该实体在文章中出现的上下文如下：
---
{entity_contexts}
---

文章基本信息：
- 标题：{article_title}
- 关键词：{article_keywords}

请根据上下文判断：
1. 上述哪些候选词条与文章中提到的"{entity_name}"语义相符并且表达的是完全或及其接近的概念，例如：可能是一个概念的两种名称，或者一个概念的两种写法，或者一个概念的两种翻译；对于语义相近，但表达含义或概念范围仍有差异的情况，请不要返回；
2. 该实体是否是文章在上下文中确实提及，并作为主要陈述内容，而非与其他词的组合而产生；
3. 语义相似度距离只代表向量库计算得到的距离结果，不能作为判断的主要依据，距离值越大表示其与文章中提到的"{entity_name}"语义越不相符，越小表示越相符，判断过程应以实体在上下文中的所表达的实际含义为准。

**输出格式要求**：
1. **仅**返回一个JSON数组。不要包含任何额外的解释或文字。
2. 数组中的每个对象必须包含且仅包含以下三个键：
   - "classifier_value_id": 词条的classifier_value_id。
   - "entity_name": 词条名称。
   - "route_path": 分类路径。
3. 如果没有任何候选词条符合条件，返回空数组 []

期望输出JSON：
[
  {{
    "classifier_value_id": 1,
    "entity_name": "词条A",
    "route_path": "父级 -> 词条A"
  }}
]

请以严格的JSON格式返回结果，不要返回任何辅助性文字。
"""

NER_OUTPUT_REQUIREMENT = """
**Output Format Requirements — MANDATORY**

You MUST return ONLY a valid JSON array. No markdown, no headings, no explanation, no code fences.

Each object in the array must have these fields:
- "entity_name": string — the extracted entity. If format is "Full Name (Abbrev)", use the abbreviation.
- "entity_type": string — the category/subcategory. Use the most specific subcategory when available (e.g. "Models" not "Materials & Subjects").
- "entity_full_name": string — full name if an abbreviation exists, otherwise "".
- "language": string — language code, default "en".
- "location": integer — 8=title, 4=abstract, 1=body. Sum if multiple (e.g. title+abstract=12). For Core Keywords default to 13.
- "metadata": object (optional) — only for Interventions & Exposures type, with "seq" (row number) and "parts" (one of "Measure", "Indication", "Method", "Result").

**Filtering rules:**
- Exclude items with values like "None", "N/A", "Not mentioned", "不适用".
- Remove any markdown formatting (bold, italic, links) from entity names.
- Ignore Self-Correction Log sections entirely.

**Interventions & Exposures handling:**
- Each row splits into 4 entities: Measure, Indication, Method, Result.
- [Measure/Exposure] → parts="Measure"; [Disease/Phenotype] → parts="Indication"; [Outcome] → parts="Result".
- Result values must be one of: "Positive", "Negative", "No Effect".

**Multi-value handling:**
- If a subcategory has comma-separated values (e.g. "Organs: Eyes, Nasal tissue"), split into separate entities.

Example output:
[
  {"entity_name": "SYN-53", "entity_type": "Core Keywords", "entity_full_name": "", "language": "en", "location": 13},
  {"entity_name": "AEC", "entity_type": "Methods", "entity_full_name": "Allergen Exposure Chamber", "language": "en", "location": 1},
  {"entity_name": "SYN-53", "entity_type": "Interventions & Exposures", "entity_full_name": "", "language": "en", "location": 1, "metadata": {"seq": 1, "parts": "Measure"}}
]

Return ONLY the JSON array. No other text.
"""


def candidates_to_markdown_table(candidates: list, value_routes: list) -> str:
    """
    将候选列表转换为Markdown表格行。

    Args:
        candidates: 候选列表 [(ClassifierValue, score, is_exact), ...]
        value_routes: 对应的路径列表 [List[ClassifierValue], ...]

    Returns:
        str: Markdown表格行字符串
    """
    rows = []
    for i, (cv, score, is_exact) in enumerate(candidates):
        if i < len(value_routes):
            route_values = [v.value for v in value_routes[i]]
            route_path = " -> ".join(route_values)
        else:
            route_path = cv.value
        rows.append(markdown_table_tr([str(cv.id), cv.value, route_path, f"{score:.3f}"]))
    return "\n".join(rows)

def classifer_output_requirement(classifier: Classifier) -> str:
    prompt = """请以JSON格式直接返回分类器取值的结果，包括取值ID和取值，不要返回任何辅助性文字。
{multi_choice_requirement}
{other_choice_requirement}

示例返回结果：

{output_sample}
    """
    output_sample = r"[{\"value_id\": 1, \"value\": 分类1}]"
    multi_sample = r"[{\"value_id\": 1, \"value\": 分类1}, {\"value_id\": 2, \"value\": 分类2}]"
    empty_array_sample = "\n或者\n[]"
    if classifier.is_multi:
        output_sample = multi_sample
        multi_choice_requirement = "文章符合的分类可能有多个，"
        other_choice_requirement = "如果分类表中提供的取值没有任何一个适合文章的分类，请返回取值ID=0，取值=other"
        if classifier.multi_limit_min or classifier.multi_limit_max:
            multi_choice_requirement += f"请返回至少{classifier.multi_limit_min}个，最多{classifier.multi_limit_max}个符合的分类。"
            if not classifier.is_allow_other_value:
                if classifier.multi_limit_min <= 0:
                    other_choice_requirement = "如果没有任何一个取值是符合的，那么请返回空数组。"
                    output_sample += empty_array_sample
                else:
                    other_choice_requirement = f"如果没有任何一个取值是符合的，那么请返回最为贴近的{classifier.multi_limit_min}个分类。"
        else:
            multi_choice_requirement += "请返回所有符合的分类。"
            if not classifier.is_allow_other_value:
                other_choice_requirement = "如果没有任何一个取值是符合的，那么请返回空数组。"
                output_sample += empty_array_sample
    else:
        multi_choice_requirement = "文章符合的分类有且只有1个。"
        if not classifier.is_allow_other_value:
            other_choice_requirement = "请返回最为贴近的分类结果，即使你认为没有适合的结果，也从所有分类取值中选择一个最有可能的结果。"

    return prompt.format(
        multi_choice_requirement=multi_choice_requirement, 
        other_choice_requirement=other_choice_requirement, 
        output_sample=output_sample)

def merged_classifer_output_requirement() -> str:
    prompt = """请以JSON格式直接返回分类器取值的结果，包括取值ID和取值，不要返回任何辅助性文字。

示例返回结果：

{output_sample}

如果没有任何一个取值是符合的，那么请返回空数组[]。
    """
    output_sample = r"[{\"classifier_alias\": \"some_alias\", \"value_id\": 1, \"value\": 分类1}, {\"classifier_alias\": \"some_alias_2\", \"value_id\": 2, \"value\": 分类2}]"

    return prompt.format(output_sample=output_sample)


def value_route_table_to_markdown_table_tr(value_route_table: list[ClassifierValue]) -> str:
  values = []
  for value in value_route_table:
    values.append(value.value)
  route = " -> ".join(values)
  return markdown_table_tr([str(value_route_table[-1].id), value_route_table[-1].value, route])

def classifier_prerequisite_in_short(classifier: Classifier, pre_seperator: str = ", ") -> str:
  """
  将classifier的prerequisite从JSON格式转换为一句话描述。

  Args:
    classifier: 分类器对象
    pre_seperator: 前缀分隔符，默认为", "

  Returns:
    str: 转换后的一句话描述，如果prerequisite为空或格式不符则返回空字符串

  Example:
    Input prerequisite: [{"value_in": ["Article", "Short Article"], "classifier_alias": "article_type"}]
    Output: ", 文章article_type取值为以下之一：Article, Short Article"
  """
  # 如果prerequisite为None或空，返回空字符串
  if not classifier.prerequisite:
    return ""

  try:
    # 获取prerequisite列表
    prerequisite_list = classifier.prerequisite

    # 检查是否为列表且至少有一个元素
    if not isinstance(prerequisite_list, list) or len(prerequisite_list) == 0:
      return ""

    # 收集所有有效的描述
    descriptions = []

    # 处理每一个prerequisite项
    for prereq in prerequisite_list:
      # 检查是否为字典且包含必需的字段
      if not isinstance(prereq, dict) or 'value_in' not in prereq or 'classifier_alias' not in prereq:
        continue

      # 获取value_in和classifier_alias
      value_in = prereq.get('value_in', [])
      classifier_alias = prereq.get('classifier_alias', '')

      # 检查value_in是否为列表且有元素
      if not isinstance(value_in, list) or len(value_in) == 0:
        continue

      # 构建描述字符串
      values_str = ", ".join(value_in)
      desc = f"进行该项分类的前提条件是：文章的{classifier_alias}取值为以下之一：{values_str}，如不满足该条件，请跳过该项分类。"
      descriptions.append(desc)

    # 如果没有有效的描述，返回空字符串
    if not descriptions:
      return ""

    # 将所有描述用分号连接
    result = "；".join(descriptions)

    # 如果结果不为空，则添加前缀分隔符
    return pre_seperator + result

  except Exception:
    # 对于其他格式的数据，返回空字符串
    return ""


# 命名实体提取结果文本转JSON提示词
TEXT_TO_JSON_CONVERSION_PROMPT = """你是一个专业的数据格式转换助手。你的任务是将命名实体提取的文本结果转换为标准的JSON格式。

【输入文本格式说明】
输入文本是命名实体提取的结果，包含以下几种可能的格式：

1. 章节标题 + 实体列表（如"# Core Keywords"后跟关键词列表）
2. 章节标题 + 子标题 + 实体（如"Materials & Subjects:" 下有 "Models: Human"）
3. 带编号的列表（如"1. xxx, 2. yyy"）
4. 普通文本描述
5. 可能包含自检报告（Self-Correction Log）部分，需要忽略

**需要过滤的内容**：
- 值为"None"、"无"、"N/A"的项
- 表达"未获得该项"、"未提及"、"不适用"、"未发现"等含义的项
- 提取出的实体如果包含markdown格式（如加粗、斜体、链接、图片等），需要去除markdown格式，仅保留纯文本内容
- 自检报告（Self-Correction Log）或自检日志部分

**子标题处理规则**：
- 如果内容格式为"主标题: 子标题: 值"（如"Materials & Subjects: Models: Human"），则entity_type使用子标题（Models）
- 如果值包含逗号分隔的多个项，每个项单独作为一个实体，entity_type都使用该子标题

【特殊处理规则 - Interventions & Exposures类型】
对于"Interventions"或"Interventions & Exposures"章节下的内容，每一行的格式为：
[Measure], [Indication], [Method], [Result]

对[Mesure]的说明：有时候提取结果会判断第一个元素为[Measure/Exposure]或者[Exposure]，我们在处理的时候都应认为其类别名称是[Measure]
对[Indication]的说明：有时候提取结果会判断第二个元素为[Disease]或者[Phenotype]，我们在处理的时候都应认为其类别名称是[Indication]
对[Result]的说明，有时候提取结果会判断第四个元素为[Outcome]，我们在处理的时候应认为其类别名称为Result。并且Result只有3中结果：有益（Positive），有害（Negative）,无效（No Effect），如果提取结果不是这3种，请根据语义含义映射为这3种之一。

需要将每行拆分为4个独立的实体，每个实体包含metadata字段：
- Measure部分：metadata = {{"seq": 行号, "parts": "Measure"}}
- Indication部分：metadata = {{"seq": 行号, "parts": "Indication"}}
- Method部分：metadata = {{"seq": 行号, "parts": "Method"}}
- Result部分：metadata = {{"seq": 行号, "parts": "Result"}}

【输出JSON格式要求】
返回一个JSON数组，每个对象包含以下字段：
- "entity_name": 提取的实体内容（字符串）
  * 如果格式为"全称 (缩写)"或"全称(缩写)"，entity_name使用缩写部分（括号内的内容）
  * 如果只有全称没有缩写，entity_name使用完整内容
- "entity_type": 实体类型（字符串）
  * 如果有子标题，使用子标题作为entity_type（如"Models"、"Organs"、"Methods"等）
  * 如果只有主标题，使用主标题（如"Core Keywords"、"Interventions & Exposures"等）
- "entity_full_name": 实体全称（字符串）
  * 如果原文格式为"全称 (缩写)"或"全称(缩写)"，entity_full_name填写全称部分（括号外的内容，去除首尾空格）
  * 如果没有缩写，entity_full_name为空字符串
- "language": 语言代码（默认"en"）
- "location": 位置编码（整数，如果没有明确说明位置则对于Core Keywords类型为13，其他类型为1）
- "metadata": 元数据对象（可选，仅Interventions & Exposures类型需要，包含seq和parts字段）

【位置编码规则】
- 8: 标题
- 4: 摘要  
- 1: 正文
- 如果出现在多个位置，返回位置之和（如标题+摘要=12）
- 如果文本中没有明确说明位置，默认使用1

【示例1：普通实体】
输入：
# Core Keywords
- SYN-53
- Allergic rhinoconjunctivitis
- *Bifidobacterium*

输出：
[
  {{
    "entity_name": "SYN-53",
    "entity_type": "Core Keywords",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }},
  {{
    "entity_name": "Allergic rhinoconjunctivitis",
    "entity_type": "Core Keywords",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }},
  {{
    "entity_name": "Bifidobacterium",
    "entity_type": "Core Keywords",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }}
]

【示例2：缩写和全称处理】
输入：
# Methods
- Allergen Exposure Chamber (AEC)
- Total Symptom Score (TSS)
- Randomized Controlled Trial

输出：
[
  {{
    "entity_name": "AEC",
    "entity_type": "Methods",
    "entity_full_name": "Allergen Exposure Chamber",
    "language": "en",
    "location": 1
  }},
  {{
    "entity_name": "TSS",
    "entity_type": "Methods",
    "entity_full_name": "Total Symptom Score",
    "language": "en",
    "location": 1
  }},
  {{
    "entity_name": "Randomized Controlled Trial",
    "entity_type": "Methods",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }}
]

说明：
1. "Allergen Exposure Chamber (AEC)" → entity_name: "AEC", entity_full_name: "Allergen Exposure Chamber"
2. "Total Symptom Score (TSS)" → entity_name: "TSS", entity_full_name: "Total Symptom Score"
3. "Randomized Controlled Trial" 没有缩写 → entity_name: "Randomized Controlled Trial", entity_full_name: ""

【示例3：Interventions & Exposures类型】
输入：
# Interventions & Exposures
1. SYN-53, Allergic rhinoconjunctivitis, Randomized Double-Blind Controlled Trial, Positive
2. [Measure/Exposure]: Galacto-oligosaccharides (GOS)
   [Disease/Phenotype]: Iron deficiency anaemia
   [Method]: RCT
   [Result]: Beneficial

输出：
[
  {{
    "entity_name": "SYN-53",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 1, "parts": "Measure"}}
  }},
  {{
    "entity_name": "Allergic rhinoconjunctivitis",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 1, "parts": "Indication"}}
  }},
  {{
    "entity_name": "Randomized Double-Blind Controlled Trial",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 1, "parts": "Method"}}
  }},
  {{
    "entity_name": "Positive",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 1, "parts": "Result"}}
  }},
  {{
    "entity_name": "GOS",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "Galacto-oligosaccharides",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 2, "parts": "Measure"}}
  }},
  {{
    "entity_name": "Iron deficiency anaemia",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 2, "parts": "Indication"}}
  }},
  {{
    "entity_name": "RCT",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 2, "parts": "Method"}}
  }},
  {{
    "entity_name": "Positive",
    "entity_type": "Interventions & Exposures",
    "entity_full_name": "",
    "language": "en",
    "location": 1,
    "metadata": {{"seq": 2, "parts": "Result"}}
  }}
]

【示例4：子标题处理、多值拆分和过滤无效内容】
输入：
# Materials & Subjects
Models: Human
Organs: Eyes, Nasal tissue
Cells: None
Microbes: Not mentioned
Cohorts: N/A

# Self-Correction Log
Coverage: 100% of core entities extracted...

输出：
[
  {{
    "entity_name": "Human",
    "entity_type": "Models",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }},
  {{
    "entity_name": "Eyes",
    "entity_type": "Organs",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }},
  {{
    "entity_name": "Nasal tissue",
    "entity_type": "Organs",
    "entity_full_name": "",
    "language": "en",
    "location": 1
  }}
]

说明：
1. entity_type使用子标题（Models、Organs）而不是主标题（Materials & Subjects）
2. "Eyes, Nasal tissue"被拆分为两个独立的实体，都使用"Organs"作为entity_type
3. Cells、Microbes、Cohorts的值为None/Not mentioned/N/A，被过滤掉
4. Self-Correction Log部分被忽略

【重要提示】
1. 只返回JSON数组，不要包含任何其他文字、解释或markdown代码块标记
2. 确保JSON格式正确，可以被直接解析
3. 所有字符串值都要用双引号包裹
4. 注意转义特殊字符
5. **缩写和全称分离**：如果原文格式为"全称 (缩写)"或"全称(缩写)"（如"Total Symptom Score (TSS)"），必须将缩写提取到entity_name，全称提取到entity_full_name
6. 对于Interventions类型，必须严格按照[Measure], [Indication], [Method], [Result]的顺序拆分
7. **过滤无效内容**：如果某项内容为"None"、"无"、"N/A"或表达"未获得该项"、"未提及"、"不适用"等含义，则不要输出该项
8. **忽略自检报告**：文本中的自检报告部分（Self-Correction Log、自检日志等）无需处理，直接跳过
9. **子标题优先**：当格式为"主标题: 子标题: 值"时，entity_type必须使用子标题而非主标题
10. **多值拆分**：如果一个子标题后有逗号分隔的多个值（如"Organs: Eyes, Nasal tissue"），必须拆分为多个独立的实体，每个实体使用相同的entity_type

现在，请将以下文本转换为JSON格式：

{text_content}"""