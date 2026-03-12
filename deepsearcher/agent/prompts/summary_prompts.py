
class SummaryPrompts:

    CHANNEL_SUMMARY_ZH = """
请根据以下文章列表，生成一篇总结性文章，文章的目标是：{query}。要求内容包括：

1. 栏目科研的主题都有哪些
2. 核心文章所阐述的研究内容和科研成果
3. 最新的研究进展
4. 整体研究价值和重要意义
5. 引用文章时，使用格式[X]，X为文章列表中的article_id

语言要求：中文
字数要求：{min_words}-{max_words}字

文章列表：
{articles_info}

请直接生成总结文本，不要包含任何额外的说明或格式。 """
    CHANNEL_SUMMARY_EN= """
Based on the following list of articles, please generate a summary article with the goal of: {query}. The content should include:

1. What are the main themes of scientific research in the column?
2. What are the research contents and scientific achievements of the core articles?
3. What are the latest research developments?
4. What is the overall research value and significance?
5. When citing articles, use the format [X], where X is the article_id in the article list

Language requirement: English
Word count requirement: {min_words}-{max_words} words

Article list:
{articles_info}

Please generate the summary text directly, without any additional explanations or formats. """

    CHANNEL_QUESTION_ZH = """
本栏目是关于{query}的内容，并且包含了以下文章，请以一个思考并提出用户可能会关心的{question_count}个科普性问题。
科普性问题不宜过长，10-20个字为宜。目标是让用户对栏目内容有一个初步的了解，不需要太深入。

文章列表：
{articles_info}

{user_history}

语言要求：中文

请直接生成{question_count}个科研问题，问题内容的前面无需编写序号，不要包含任何额外的说明或格式。"""

    CHANNEL_QUESTION_EN = """
The column is about {query} content, and includes the following articles, please think of and propose {question_count} popular science questions that users might be interested in.
The popular science questions should not be too long, 10-20 words is appropriate. The goal is to give users a preliminary understanding of the column content, not too deep.

Article list:
{articles_info}

{user_history}

Language requirement: English

Please generate {question_count} scientific research questions, without any additional explanations or formats. """

    CHANNEL_POPULAR_ZH = """
你是一位专业的科普作家。请根据用户关注的"核心问题"和提供的"参考文章"，创作一篇"通俗易懂的科普短文"。

核心问题: {query}

文章要求:
1. 深入浅出地解释核心问题的基础概念。
2. 内容力求简洁明了，确保读者轻松理解。
3. 在必要时，巧妙运用生活化类比，帮助读者构建具象认知。
4. 准确引用参考文章，格式为：[X]（X为文章列表中的article_id），遇到参考文章ID请无论在任何位置都使用这种格式，不要直接陈列文章ID。

语言要求：中文
字数要求：{min_words}-{max_words}字

参考文章列表：
{articles_info}

请直接生成科普性短文，不要包含任何额外的说明或格式。 """

    CHANNEL_PPT_ZH = """
你是一位专业的演示文稿设计师，擅长将复杂信息转化为清晰、有条理的PPT结构。

请根据用户关注的"核心主题"和提供的"参考文章"，创作一份"详细的PPT提纲"。

核心主题: {query}

提纲要求:
1. 结构完整：提纲需包含PPT的标题和主要内容点。
2. 逻辑清晰：内容点之间应有明确的逻辑关系，便于演示和理解。
3. 内容提炼：从参考文章中提取关键信息，确保每页内容简洁有力。
4. 准确引用参考文章，格式为：[X]（X为文章列表中的article_id），遇到参考文章ID请无论在任何位置都使用这种格式，不要直接陈列文章ID。

语言要求：中文

文章列表：
{articles_info}

请请直接生成PPT提纲，不要包含任何额外的说明或格式。 """

    CHANNEL_FOOTAGE_ZH = """
你是一位经验丰富的短视频内容创作者，擅长将科普知识转化为生动有趣的视频脚本。

请根据用户关注的"核心主题"和提供的"参考文章"，创作一份"详细的短视频脚本"。

核心主题: {query}

脚本要求:
1. 完整性：脚本需包含视频标题、开场白、主体内容（分段落或场景）、关键视觉建议和结尾呼吁/总结。
2. 吸引力：内容应具备短视频的特点，如节奏明快、语言口语化、易于理解和传播。
3. 视觉化：在内容描述中融入对画面的想象和建议，帮助理解和制作。
4. 信息提炼：从参考文章中提取核心观点和关键信息，确保内容的准确性和精炼性。
5. 准确引用参考文章，格式为：[X]（X为文章列表中的article_id），遇到参考文章ID请无论在任何位置都使用这种格式，不要直接陈列文章ID。

语言要求：中文

文章列表：
{articles_info}

请直接生成短视频脚本，不要包含任何额外的说明或格式。 """

    CHANNEL_OPPORTUNITY_ZH = """
你是一位资深的商业分析师和市场洞察专家，擅长从科研发现中识别潜在的商业价值。

请根据用户关注的"核心科研问题"和提供的"参考文章"，创作一篇"深入分析潜在商业机会的短文"。

核心科研问题: {query}

分析要求:
1. 洞察商机：详细分析文章中提及的科研问题可能催生哪些具体的商业机会（如产品、服务、技术解决方案、市场空白等）。
2. 潜在价值：阐述这些商机的潜在市场规模、商业模式可能性或颠覆性潜力。
3. 关键要素：指出实现这些商机可能需要考虑的技术成熟度、市场需求、竞争格局或合作机会等关键要素。
4. 准确引用参考文章，格式为：[X]（X为文章列表中的article_id），遇到参考文章ID请无论在任何位置都使用这种格式，不要直接陈列文章ID。

语言要求：中文
字数要求：{min_words}-{max_words}字

文章列表：
{articles_info}

请直接生成科普性短文，不要包含任何额外的说明或格式。 """

    PROMPT_ROUTER_PROMPT = """请根据以下信息，选择最合适的提示词模板：
用户查询内容：{query}
目标语言：{target_lang}

可用的模板列表：
{templates_info}

请仔细分析用户查询内容和目标语言，选择最匹配的模板ID。只需要返回模板ID，不需要其他解释。
"""