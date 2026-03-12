#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复concept数据的脚本。

该脚本的执行流程：
1. 从数据库读取concept数据
2. 使用Concept模型的is_complete方法验证完整性
3. 对不完整的concept逐项修正：
   - name为空则报错失败
   - cname为空则翻译
   - concept_term_id为空则查找或创建term
   - concept_term_id2为空则查找或创建term
   - concept_term_id3为空则生成缩写并查找或创建term
4. 修正后重新验证并更新数据库

创建时间: 2025年10月20日
"""

import sys
import os
import logging
import argparse
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config
from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from deepsearcher.rbase.terms import Concept
from deepsearcher.api.rbase_util import load_concept_by_id
from deepsearcher.agent.academic_translator import AcademicTranslator
from deepsearcher.llm.base import BaseLLM

class ConceptFixer:
    """Concept数据修复类"""
    
    def __init__(self, config: Configuration, translator: AcademicTranslator, llm: BaseLLM, reasoning_llm: BaseLLM, dry_run: bool = False):
        """
        初始化
        
        Args:
            config: 配置对象
            dry_run: 是否为干跑模式（不实际修改数据）
        """
        self.config = config
        self.dry_run = dry_run
        self.connection = None
        self.translator = translator
        self.llm = llm
        self.reasoning_llm = reasoning_llm
        self._init_db_connection()
    
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info("数据库连接成功")
        except Exception as e:
            error(f"数据库连接失败: {e}")
            raise
    
    def _ensure_db_connection(self):
        """确保数据库连接有效，如果断开则重连"""
        try:
            if self.connection:
                self.connection.ping(reconnect=True)
        except Exception as e:
            from deepsearcher.tools.log import warning
            warning(f"数据库连接失效，尝试重连: {e}")
            try:
                self._init_db_connection()
            except Exception as reconnect_error:
                error(f"数据库重连失败: {reconnect_error}")
                raise
    
    def find_or_create_term(self, name: str, intro = None, concept_id: int = 0, is_abbr: bool = False, 
                           is_concept_term: bool = False) -> Optional[int]:
        """
        查找或创建term
        
        Args:
            name: 术语名称
            concept_id: 所属概念ID（创建时可能为0，后续更新）
            is_abbr: 是否为缩写形式
            is_concept_term: 是否为概念核心词
            
        Returns:
            term_id，失败时返回None
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                # 先查找是否已存在
                cursor.execute(
                    "SELECT id FROM term WHERE name = %s AND status >= 1 AND is_abbr = %s",
                    (name, is_abbr)
                )
                existing = cursor.fetchone()
                
                if existing:
                    info(f"使用已存在的术语 '{name}' (ID: {existing['id']})")
                    return existing['id']
                
                # 如果是干跑模式，不实际创建
                if self.dry_run:
                    info(f"[DRY RUN] 将创建术语 '{name}'")
                    return -1  # 返回假ID
                
                # 创建新term
                term_uuid = str(uuid.uuid4()).replace('-', '')
                insert_sql = """
                INSERT INTO term (
                    uuid, name, intro, concept_id, is_concept_term, is_abbr, 
                    is_virtual, status, created, modified
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """
                
                values = (
                    term_uuid,                                      # uuid
                    name,                                           # name
                    intro if intro else f"自动修复生成的术语：{name}", # intro
                    concept_id,                                     # concept_id (可能为0，后续更新)
                    1 if is_concept_term else 0,                    # is_concept_term (核心词)
                    1 if is_abbr else 0,                            # is_abbr
                    0,                                              # is_virtual
                    10,                                             # status (审核通过)
                    datetime.now(),                                 # created
                    datetime.now()                                  # modified
                )
                
                cursor.execute(insert_sql, values)
                term_id = cursor.lastrowid
                self.connection.commit()
                
                info(f"成功创建术语 '{name}' (ID: {term_id})")
                return term_id
                
        except Exception as e:
            error(f"处理术语失败: {e}")
            try:
                if self.connection:
                    self.connection.rollback()
            except Exception as rollback_error:
                error(f"回滚失败: {rollback_error}")
            return None
    
    def generate_abbr_with_llm(self, english_name: str) -> Optional[str]:
        """
        使用LLM生成术语缩写
        
        Args:
            english_name: 英文名称
            chinese_name: 中文名称
            
        Returns:
            生成的缩写
        """
        try:
            intention_prompt = f"""请判断用户提供的术语是否需要生成缩写，通常以下类型的术语才有必要生成缩写：
1. 若干专业名词的组合；
2. 词语具有一定的长度，包含多个单词；
3. 可能在学术界是一个被普遍认知的概念，其缩写已被普遍认可。

用户提供的术语：{english_name}

请直接返回"YES"或"NO"，表示是否需要生成缩写，不要包含其他解释文字。"""
            intention_response = self.reasoning_llm.chat([{"role": "user", "content": intention_prompt}])
            intention_result = intention_response.content.strip()
            if intention_result.lower() != "yes":
                debug(f"术语{english_name}不需要生成缩写")
                return None

            abbr_prompt = f"""请为以下学术术语生成合适的英文缩写：

术语：{english_name}

要求：
1. 缩写应该简洁明了，通常2-6个字母；如确有需要也不应超过10个字母；
2. 缩写应该能够代表术语的核心含义
3. 优先使用学术界常用的缩写
4. 如果没有标准缩写，请基于英文单词的首字母创建

请只返回缩写，不要包含其他解释文字。"""
            
            abbr_response = self.llm.chat([{"role": "user", "content": abbr_prompt}])
            abbr_name = abbr_response.content.strip().upper()
            info(f"LLM生成缩写: {abbr_name}")
            return abbr_name
        except Exception as e:
            error(f"LLM生成缩写失败: {e}")
            # 简单的备用方案：取英文单词首字母
            abbr_name = ''.join(word[0].upper() for word in english_name.split() if word)[:4]
            info(f"使用备用方案生成缩写: {abbr_name}")
            return abbr_name
    
    def has_english_chars(self, text: str) -> bool:
        """
        判断文本中是否包含英文字符（使用ASCII码检查）
        
        Args:
            text: 待判断的文本
            
        Returns:
            是否包含英文字符
        """
        if not text:
            return False
        
        for char in text:
            ascii_code = ord(char)
            if (65 <= ascii_code <= 90) or (97 <= ascii_code <= 122):
                return True
        
        return False
    
    def fix_concept(self, concept_id: int, force: bool = False, reset_cname: bool = False, create_intro: bool = False) -> bool:
        """
        修复单个concept
        
        Args:
            concept_id: concept的ID
            
        Returns:
            修复是否成功
        """
        try:
            self._ensure_db_connection()
            # 1. 从数据库读取concept数据
            with self.connection.cursor() as cursor:
                concept = load_concept_by_id(concept_id)
                if concept is None:
                    error(f"未找到ID为 {concept_id} 的concept")
                    return False
                
                # 2. 检查是否完整
                if not force and concept.is_complete():
                    if not create_intro or self.is_concept_intro_useful(concept):
                        info(f"Concept {concept_id} ({concept.cname}) 已经完整，无需修复")
                        return True
                
                debug(f"\n开始修复Concept {concept_id}: {concept.name} / {concept.cname}")
                
                # 记录是否有修改
                has_changes = False
                updates = {}

                if not self.is_concept_intro_useful(concept):
                    concept.intro = None

                # 3. 逐项检查和修正
                # 3.1 检查name
                if not concept.name or concept.name.strip() == "":
                    if concept.cname and concept.cname.strip() != "":
                        extra_info=f"This is a biomedical field concept, with some additional explaination: {concept.intro}" if concept.intro else ""
                        updates['name'] = self.translator.translate(concept.cname, "en", extra_info=extra_info)
                        concept.name = updates['name']
                        has_changes = True
                    else:
                        error(f"Concept {concept_id} 的name为空，无法修复")
                        return False
                
                # 3.2 检查cname
                if reset_cname or not concept.cname or concept.cname.strip() == "":
                    debug(f"cname为空或需要重新翻译，正在翻译 '{concept.name}' 为中文...")
                    try:
                        extra_info=f"This is a biomedical field concept, with some additional explaination: {concept.intro}" if concept.intro else ""
                        cname = self.translator.translate(concept.name, "zh", extra_info=extra_info)
                        debug(f"翻译结果: {concept.name} -> {cname}")
                        updates['cname'] = cname
                        concept.cname = cname
                        has_changes = True
                        concept.concept_term_id2 = 0
                    except Exception as e:
                        error(f"翻译失败: {e}")
                        return False
                
                # 3.3 检查concept_term_id (name对应的term)
                if not concept.concept_term_id or concept.concept_term_id == 0:
                    debug(f"concept_term_id为空，正在查找或创建 '{concept.name}' 对应的term...")
                    term_id = self.find_or_create_term(
                        concept.name, 
                        concept_id=concept_id if not self.dry_run else 0,
                        is_abbr=False,
                        is_concept_term=False
                    )
                    if term_id:
                        updates['concept_term_id'] = term_id
                        concept.concept_term_id = term_id
                        has_changes = True
                    else:
                        error(f"无法创建term for '{concept.name}'")
                        return False
                
                # 3.4 检查concept_term_id2 (cname对应的term)
                if not concept.concept_term_id2 or concept.concept_term_id2 == 0:
                    debug(f"concept_term_id2为空，正在查找或创建 '{concept.cname}' 对应的term...")
                    if concept.cname:  # 确保cname已经存在
                        term_id = self.find_or_create_term(
                            concept.cname,
                            concept_id=concept_id if not self.dry_run else 0,
                            is_abbr=False,
                            is_concept_term=True
                        )
                        if term_id:
                            updates['concept_term_id2'] = term_id
                            concept.concept_term_id2 = term_id
                            has_changes = True
                        else:
                            error(f"无法创建term for '{concept.cname}'")
                            return False
                
                # 3.5 检查concept_term_id3 (缩写对应的term)
                if not concept.concept_term_id3 or concept.concept_term_id3 == 0:
                    # 判断是否有英文词条
                    has_english = self.has_english_chars(concept.name)
                    
                    if has_english:
                        debug(f"concept_term_id3为空，正在生成缩写...")
                        # 使用英文名和中文名生成缩写
                        abbr_name = self.generate_abbr_with_llm(concept.name)
                        
                        if abbr_name:
                            term_id = self.find_or_create_term(
                                abbr_name,
                                intro=f"术语{concept.name}的缩写",
                                concept_id=concept_id if not self.dry_run else 0,
                                is_abbr=True,
                                is_concept_term=False
                            )
                            if term_id:
                                updates['concept_term_id3'] = term_id
                                updates['abbr_name'] = abbr_name
                                updates['abbr_cname'] = abbr_name
                                concept.concept_term_id3 = term_id
                                concept.abbr_name = abbr_name
                                concept.abbr_cname = abbr_name
                                has_changes = True
                            else:
                                error(f"无法创建缩写term for '{abbr_name}'")
                                # 缩写创建失败不算致命错误，继续执行
                        else:
                            debug(f"'{concept.name}' 无法或不需要生成缩写")
                    else:
                        debug("没有英文词条，跳过缩写生成")
                
                # 4. 再次验证完整性
                if not concept.is_complete():
                    error(f"修复后Concept {concept_id} 仍然不完整")
                    error(f"  name: {concept.name}")
                    error(f"  cname: {concept.cname}")
                    error(f"  concept_term_id: {concept.concept_term_id}")
                    error(f"  concept_term_id2: {concept.concept_term_id2}")
                    error(f"  concept_term_id3: {concept.concept_term_id3}")
                    return False
                
                # 5. 创建有价值的介绍
                if create_intro and not self.is_concept_intro_useful(concept):
                    concept.intro = self.create_valuable_intro(concept.name, concept.cname)
                    if self.is_concept_intro_useful(concept):
                        debug(f"创建有价值的介绍成功: {concept.intro}")
                        updates['intro'] = concept.intro
                        has_changes = True
                    else:
                        debug("创建有价值的介绍失败")

                # 6. 更新数据库
                if has_changes and updates:
                    if self.dry_run:
                        info(f"[DRY RUN] Concept {concept_id} needs to be updated:")
                        for key, value in updates.items():
                            info(f"  {key}: {value}")
                    else:
                        # 构建UPDATE SQL
                        set_clause = ", ".join([f"{key} = %s" for key in updates.keys()])
                        update_sql = f"UPDATE concept SET {set_clause}, modified = %s WHERE id = %s"
                        values = list(updates.values()) + [datetime.now(), concept_id]
                        
                        cursor.execute(update_sql, values)
                        self.connection.commit()
                        
                        debug(f"✅ 成功修复Concept {concept_id} ({concept.cname})")
                        for key, value in updates.items():
                            debug(f"  {key}: {value}")
                
                return True
        except Exception as e:
            error(f"修复Concept {concept_id} 失败: {e}")
            import traceback
            traceback.print_exc()
            try:
                if self.connection:
                    self.connection.rollback()
            except Exception as rollback_error:
                error(f"回滚失败: {rollback_error}")
            return False
        
    def is_concept_intro_useful(self, concept: Concept) -> bool:
        if concept.intro and concept.intro.strip() != "":
            if concept.intro.strip().startswith("来自词表导入"):
                return False
            if concept.intro.strip().startswith("分类器生成的概念"):
                return False
            else:
                prompt = f"""请判断数据库中对属于的解释，是否是一个有价值的解释（即是否是对属于的学术含义做出了有效的表达）
术语：{concept.name}
解释：{concept.intro}
请直接返回"YES"或"NO"，表示是否是一个有价值的解释，不要包含其他任何解释或说明文字。"""
                response = self.llm.chat([{"role": "user", "content": prompt}])
                return response.content.strip().lower() == "yes"
        else:
            return False

    def create_valuable_intro(self, concept_name: str, concept_cname: str) -> str:
        """
        创建有价值的介绍
        
        Args:
            concept: concept对象
            
        Returns:
            str: 有价值的介绍
        """
        prompt = f"""请为以下学术术语生成有价值的解释：

术语英文：{concept_name}
术语中文：{concept_cname}

如果术语在多个不同学科领域中都有存在，那么优先解释其在生物医药方面的含义。
术语解释请用英文书写，请直接返回介绍，不要包含其他解释文字。"""
        response = self.llm.chat([{"role": "user", "content": prompt}])
        return response.content.strip()
    
    def fix_all_incomplete_concepts(self, limit: Optional[int] = None, create_intro: bool = False) -> Dict[str, int]:
        """
        修复所有不完整的concepts
        
        Args:
            limit: 限制处理的数量，None表示处理全部
            
        Returns:
            统计结果字典 {'total': 总数, 'success': 成功数, 'failed': 失败数, 'skipped': 跳过数}
        """
        try:
            # 查找所有concept
            with self.connection.cursor() as cursor:
                sql = "SELECT id FROM concept WHERE status >= 1 ORDER BY id ASC"
                if limit:
                    sql += f" LIMIT {limit}"
                cursor.execute(sql)
                concept_ids = [row['id'] for row in cursor.fetchall()]
            
            total = len(concept_ids)
            success = 0
            failed = 0
            skipped = 0
            
            color_print(f"\n开始批量修复concepts，共 {total} 个...")
            color_print("=" * 60)
            
            for idx, concept_id in enumerate(concept_ids, 1):
                info(f"\n[{idx}/{total}] 处理Concept ID: {concept_id}")
                
                # 先检查是否完整
                with self.connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT id, name, cname, concept_term_id, concept_term_id2, 
                                  created, modified
                           FROM concept WHERE id = %s""",
                        (concept_id,)
                    )
                    row = cursor.fetchone()
                    
                    if not row:
                        error(f"未找到ID为 {concept_id} 的concept")
                        failed += 1
                        continue
                    
                    # 快速检查是否完整
                    if (row['name'] and row['cname'] and 
                        row['concept_term_id'] and row['concept_term_id2']):
                        info(f"Concept {concept_id} 已完整，跳过")
                        skipped += 1
                        continue
                
                # 执行修复
                if self.fix_concept(concept_id, create_intro=create_intro):
                    success += 1
                else:
                    failed += 1
            
            # 输出统计结果
            color_print("\n" + "=" * 60)
            color_print("批量修复完成!")
            color_print(f"总计: {total}")
            color_print(f"✅ 成功: {success}")
            color_print(f"⏭️  跳过: {skipped}")
            color_print(f"❌ 失败: {failed}")
            color_print("=" * 60)
            
            return {
                'total': total,
                'success': success,
                'failed': failed,
                'skipped': skipped
            }
            
        except Exception as e:
            error(f"批量修复失败: {e}")
            import traceback
            traceback.print_exc()
            return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
    
    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()
            debug("数据库连接已关闭")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='修复不完整的concept数据')
    parser.add_argument('-i', '--id', type=int, help='指定要修复的concept ID')
    parser.add_argument('-a', '--all', action='store_true', help='修复所有不完整的concepts')
    parser.add_argument('-l', '--limit', type=int, help='限制处理的数量（配合--all使用）')
    parser.add_argument('-d', '--dry-run', action='store_true', help='干跑模式，不实际修改数据')
    parser.add_argument('-f', '--force', action='store_true', help='强制修复，不检查是否完整')
    parser.add_argument('-c', '--create-intro', action='store_true', help='创建有价值的介绍')
    parser.add_argument('--reset-cname', action='store_true', help='重新翻译cname')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    # 参数验证
    if not args.id and not args.all:
        parser.error("必须指定 --id 或 --all 参数")
    
    if args.id and args.all:
        parser.error("--id 和 --all 参数不能同时使用")
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        if args.id:
            debug(f"修复模式: 单个 (ID: {args.id})")
        else:
            debug(f"修复模式: 批量 (limit: {args.limit or '无限制'})")
        debug(f"干跑模式: {args.dry_run}")
        debug("-" * 50)
    
    # 初始化配置
    init_rbase_config()
    
    try:
        fixer = ConceptFixer(configuration.config, 
                             translator=configuration.academic_translator, 
                             llm=configuration.llm, 
                             reasoning_llm=configuration.reasoning_llm,
                             dry_run=args.dry_run)
        
        if args.id:
            # 修复单个concept
            success = fixer.fix_concept(args.id, force=args.force, reset_cname=args.reset_cname, create_intro=args.create_intro)
            return 0 if success else 1
        else:
            # 批量修复
            stats = fixer.fix_all_incomplete_concepts(limit=args.limit)
            return 0 if stats['failed'] == 0 else 1
            
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if fixer:
            fixer.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())

