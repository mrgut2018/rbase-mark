#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入term_tree_node的脚本。

该脚本的执行流程：
1. 检查term_tree和根节点term_tree_node是否存在
2. 按照level由小到大的顺序排列CSV数据并顺序插入
3. 根据parent_seq确定父子关系
4. 自动创建不存在的concept，使用翻译和LLM生成缩写
5. 支持交互式确认模式
6. 最后输出完整的树形结构

创建时间: 2025年9月23日
"""

import sys
import os
import logging
import json
import argparse
import csv
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from deepsearcher.api.rbase_util import load_concept_by_id
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from fix_incomplete_concepts import ConceptFixer


class TermTreeNodeImporter:
    """term_tree_node批量导入类"""
    
    def __init__(self, config: Configuration, interactive_mode: bool = False):
        """初始化"""
        self.config = config
        self.connection = None
        self.interactive_mode = interactive_mode
        self.seq_to_node_id = {}  # seq号到实际node_id的映射
        self.concept_fixer = ConceptFixer(config, configuration.academic_translator, configuration.llm, configuration.reasoning_llm, dry_run=False)
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
    
    def validate_term_tree_and_root(self, term_tree_id: int, root_node_id: int) -> bool:
        """
        验证term_tree和根节点是否存在
        
        Args:
            term_tree_id: 术语树ID
            root_node_id: 根节点ID
            
        Returns:
            验证结果
        """
        try:
            with self.connection.cursor() as cursor:
                # 验证term_tree是否存在
                cursor.execute(
                    "SELECT id, name, cname FROM term_tree WHERE id = %s AND status = 1",
                    (term_tree_id,)
                )
                tree_result = cursor.fetchone()
                if not tree_result:
                    error(f"term_tree_id {term_tree_id} 不存在或状态无效")
                    return False
                
                info(f"找到术语树: {tree_result['name']} / {tree_result['cname']}")
                
                # 验证根节点是否存在
                cursor.execute(
                    "SELECT id, tree_id, node_concept_name FROM term_tree_node WHERE id = %s AND status = 1",
                    (root_node_id,)
                )
                node_result = cursor.fetchone()
                if not node_result:
                    error(f"根节点ID {root_node_id} 不存在或状态无效")
                    return False
                
                # 验证根节点是否属于指定的term_tree
                if node_result['tree_id'] != term_tree_id:
                    error(f"根节点ID {root_node_id} 不属于术语树 {term_tree_id}")
                    return False
                
                info(f"找到根节点: {node_result['node_concept_name']}")
                # 将根节点映射添加到字典中（seq=0对应根节点）
                self.seq_to_node_id[0] = root_node_id
                return True
                
        except Exception as e:
            error(f"验证失败: {e}")
            return False
    
    def load_csv_data(self, csv_file_path: str) -> List[Dict[str, Any]]:
        """
        加载CSV数据并按level排序
        
        Args:
            csv_file_path: CSV文件路径
            
        Returns:
            排序后的数据列表
        """
        try:
            data = []
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # 转换数据类型
                    processed_row = {
                        'seq': int(row['seq']),
                        'tree_id': int(row['tree_id']),
                        'value': row['value'].strip(),
                        'intro': row.get('intro', '').strip(),
                        'level': int(row['level']),
                        'parent_seq': int(row['parent_seq']),
                        'priority': int(row['priority']) * -1,
                        'is_category_node': int(row.get('is_category_node', 0))
                    }
                    data.append(processed_row)
            
            # 按level排序
            data.sort(key=lambda x: (x['level'], x['priority'], x['seq']))
            
            info(f"成功加载 {len(data)} 条数据，按level排序完成")
            return data
            
        except Exception as e:
            error(f"加载CSV文件失败: {e}")
            return []
    
    def find_or_create_term(self, name: str, concept_id: int = 0, is_abbr: bool = False, is_concept_term: bool = False, intro: Optional[str] = None) -> Tuple[Optional[int], bool]:
        """
        查找或创建term
        
        Args:
            name: 术语名称
            concept_id: 所属概念ID（创建时可能为0，后续更新）
            is_abbr: 是否为缩写形式
            is_concept_term: 是否为概念核心词
            intro: 术语介绍
            
        Returns:
            (term_id, is_newly_created)，失败时返回(None, False)
        """
        try:
            with self.connection.cursor() as cursor:
                # 先查找是否已存在
                cursor.execute(
                    "SELECT id FROM term WHERE name = %s AND status >= 1",
                    (name,)
                )
                existing = cursor.fetchone()
                
                if existing:
                    info(f"使用已存在的术语 '{name}' (ID: {existing['id']})")
                    return existing['id'], False  # 已存在，非新创建
                
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
                    term_uuid,                    # uuid
                    name,                         # name
                    intro if intro else f"分类器生成的术语：{name}",     # intro
                    concept_id,                   # concept_id (可能为0，后续更新)
                    1 if is_concept_term else 0,  # is_concept_term (核心词)
                    1 if is_abbr else 0,          # is_abbr
                    1,                            # is_virtual
                    10,                           # status (审核通过)
                    datetime.now(),               # created
                    datetime.now()                # modified
                )
                
                cursor.execute(insert_sql, values)
                term_id = cursor.lastrowid
                
                info(f"成功创建术语 '{name}' (ID: {term_id})")
                return term_id, True  # 新创建
                
        except Exception as e:
            error(f"处理术语失败: {e}")
            return None, False
    
    def find_or_create_concept(self, cname: str, new_term_intro: Optional[str] = None) -> Optional[int]:
        """
        查找或创建concept
        
        当找到多个cname相同的概念时：
        1. 优先选择intro中包含"分类器"字段的概念
        2. 否则选择ID最大的概念
        
        Args:
            cname: 中文名称
            
        Returns:
            concept_id，失败时返回None
        """
        try:
            with self.connection.cursor() as cursor:
                # 查找所有匹配的概念，按ID排序
                cursor.execute(
                    "SELECT id, name, cname, intro FROM concept WHERE cname = %s AND status >= 1 ORDER BY id DESC",
                    (cname,)
                )
                existing_concepts = cursor.fetchall()
                
                if existing_concepts:
                    # 如果只有一个概念，直接使用
                    if len(existing_concepts) == 1:
                        selected_concept = existing_concepts[0]
                    else:
                        # 多个概念时，优先选择包含"分类器"的概念
                        classifier_concepts = [c for c in existing_concepts if c.get('intro') and "分类器" in c.get('intro')]
                        
                        if classifier_concepts:
                            # 如果有包含"分类器"的概念，选择其中ID最大的
                            selected_concept = classifier_concepts[0]  # 已按ID降序排列
                            info(f"在{len(existing_concepts)}个概念中选择包含'分类器'的概念 ID: {selected_concept['id']}")
                        else:
                            # 没有包含"分类器"的概念，选择ID最大的
                            selected_concept = existing_concepts[0]  # 已按ID降序排列
                            info(f"在{len(existing_concepts)}个概念中选择ID最大的概念 ID: {selected_concept['id']}")
                    
                    color_print(f"发现已存在的概念:")
                    print(f"  ID: {selected_concept['id']}")
                    print(f"  中文名: {selected_concept['cname']}")
                    print(f"  英文名: {selected_concept['name']}")
                    intro_text = selected_concept.get('intro') or ""
                    print(f"  介绍: {intro_text[:100]}...")
                    
                    # 如果是交互模式，询问用户确认
                    if self.interactive_mode:
                        user_input = input("是否使用此概念? (Y/n，默认Y): ").strip().lower()
                        if user_input == '' or user_input == 'y':
                            info(f"使用已存在的概念 ID: {selected_concept['id']}")
                            return selected_concept['id']
                        else:
                            info("用户选择不使用已存在的概念，将创建新概念")
                    else:
                        # 非交互模式下直接使用选中的概念
                        info(f"自动使用已存在的概念 ID: {selected_concept['id']}")
                        return selected_concept['id']
                
                # 创建新概念
                info(f"为 '{cname}' 创建新概念...")
                
                # 使用翻译器翻译为英文
                try:
                    english_name = configuration.academic_translator.translate(cname, "en")
                    info(f"翻译结果: {cname} -> {english_name}")
                except Exception as e:
                    error(f"翻译失败: {e}")
                    english_name = cname  # 翻译失败时使用原文
                
                # 使用LLM生成缩写
                try:
                    abbr_name = self.concept_fixer.generate_abbr_with_llm(english_name)
                    info(f"生成缩写: {abbr_name}")
                except Exception as e:
                    error(f"生成缩写失败: {e}")
                    # 简单的备用方案：取英文单词首字母
                    abbr_name = ''.join(word[0].upper() for word in english_name.split() if word)[:4]
                
                # 先创建3个对应的term
                # 1. 英文term
                english_term_id, english_is_new = self.find_or_create_term(english_name, concept_id=0, 
                                                                           is_abbr=False, is_concept_term=False, intro=new_term_intro)
                if not english_term_id:
                    error(f"创建英文术语失败: {english_name}")
                    return None
                
                # 2. 中文term  
                chinese_term_id, chinese_is_new = self.find_or_create_term(cname, concept_id=0, 
                                                                           is_abbr=False, is_concept_term=True, intro=new_term_intro)
                if not chinese_term_id:
                    error(f"创建中文术语失败: {cname}")
                    return None
                
                # 3. 缩写term
                if abbr_name:
                    abbr_term_id, abbr_is_new = self.find_or_create_term(abbr_name, concept_id=0, 
                                                                         is_abbr=True, is_concept_term=False, intro=f"术语{english_name}的缩写")
                else:
                    abbr_term_id = 0
                    abbr_is_new = False
                
                intro = self.concept_fixer.create_valuable_intro(english_name, cname)
                
                # 插入新概念，包含term外键
                concept_uuid = str(uuid.uuid4()).replace('-', '')
                insert_sql = """
                INSERT INTO concept (
                    uuid, name, cname, abbr_name, abbr_cname, intro,
                    concept_term_id, concept_term_id2, concept_term_id3,
                    is_virtual, is_preferred_concept, status,
                    created, modified
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                """
                
                values = (
                    concept_uuid,           # uuid
                    english_name,           # name
                    cname,                  # cname
                    abbr_name,             # abbr_name
                    abbr_name,             # abbr_cname (使用相同缩写)
                    f"分类器生成的概念：{cname}" if not intro else intro,  # intro
                    english_term_id,       # concept_term_id (英文term)
                    chinese_term_id,       # concept_term_id2 (中文term)
                    abbr_term_id,          # concept_term_id3 (缩写term)
                    1,                     # is_virtual
                    1,                     # is_preferred_concept
                    10,                    # status
                    datetime.now(),        # created
                    datetime.now()         # modified
                )
                
                cursor.execute(insert_sql, values)
                concept_id = cursor.lastrowid
                
                # 只更新新创建的term表中的concept_id字段
                newly_created_term_ids = []
                if english_is_new:
                    newly_created_term_ids.append(english_term_id)
                if chinese_is_new:
                    newly_created_term_ids.append(chinese_term_id)
                if abbr_is_new:
                    newly_created_term_ids.append(abbr_term_id)
                
                if newly_created_term_ids:
                    # 构建动态SQL，只更新新创建的term
                    placeholders = ','.join(['%s'] * len(newly_created_term_ids))
                    update_term_sql = f"UPDATE term SET concept_id = %s WHERE id IN ({placeholders})"
                    cursor.execute(update_term_sql, [concept_id] + newly_created_term_ids)
                    info(f"更新了 {len(newly_created_term_ids)} 个新创建术语的concept_id")
                else:
                    info("所有术语都已存在，无需更新concept_id")
                
                self.connection.commit()
                
                info(f"成功创建概念 '{cname}' (ID: {concept_id})")
                info(f"  - 英文术语ID: {english_term_id} {'(新创建)' if english_is_new else '(已存在)'}")
                info(f"  - 中文术语ID: {chinese_term_id} {'(新创建)' if chinese_is_new else '(已存在)'}")
                info(f"  - 缩写术语ID: {abbr_term_id} {'(新创建)' if abbr_is_new else '(已存在)'}")
                return concept_id
                
        except Exception as e:
            error(f"处理概念失败: {e}")
            self.connection.rollback()
            return None
    
    def create_term_tree_node(self, data_row: Dict[str, Any], term_tree_id: int) -> Optional[int]:
        """
        创建term_tree_node
        
        Args:
            data_row: CSV数据行
            term_tree_id: 术语树ID
            
        Returns:
            创建的节点ID，失败时返回None
        """
        try:
            # 确定父节点ID
            parent_seq = data_row['parent_seq']
            if parent_seq not in self.seq_to_node_id:
                error(f"找不到父节点seq={parent_seq}对应的node_id")
                return None
            
            parent_node_id = self.seq_to_node_id[parent_seq]
            
            # 检查节点是否已存在（根据父节点ID和value值判断）
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id FROM term_tree_node 
                       WHERE parent_node_id = %s AND node_concept_name = %s AND status = 1""",
                    (parent_node_id, data_row['value'])
                )
                existing_node = cursor.fetchone()
                
                if existing_node:
                    existing_node_id = existing_node['id']
                    info(f"节点 '{data_row['value']}' 在父节点 {parent_node_id} 下已存在 (ID: {existing_node_id})")
                    
                    # 将已存在的节点ID添加到映射中
                    self.seq_to_node_id[data_row['seq']] = existing_node_id
                    return existing_node_id
            
            # 查找或创建concept
            concept_id = self.find_or_create_concept(data_row['value'], data_row['intro'])
            if not concept_id:
                error(f"无法获取概念ID for '{data_row['value']}'")
                return None

            concept = load_concept_by_id(concept_id)
            
            # 交互式确认
            if self.interactive_mode:
                color_print(f"\n准备插入节点:")
                print(f"  序号: {data_row['seq']}")
                print(f"  名称: {data_row['value']}")
                print(f"  层级: {data_row['level']}")
                print(f"  父节点seq: {parent_seq} (node_id: {parent_node_id})")
                print(f"  概念ID: {concept_id}")
                print(f"  介绍: {data_row['intro'] if data_row['intro'] else concept.intro}")
                print(f"  是否分类节点: {data_row['is_category_node']}")
                
                user_input = input("确认插入此节点? (Y/n，默认Y): ").strip().lower()
                if user_input != '' and user_input != 'y':
                    info("用户取消插入")
                    return None
            
            # 插入term_tree_node
            with self.connection.cursor() as cursor:
                insert_sql = """
                INSERT INTO term_tree_node (
                    tree_id, parent_node_id, node_concept_id, node_concept_name,
                    intro, sequence, children_count, is_category_node,
                    status, created, modified
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                """
                
                values = (
                    term_tree_id,                       # tree_id
                    parent_node_id,                     # parent_node_id
                    concept_id,                         # node_concept_id
                    data_row['value'],                  # node_concept_name
                    data_row['intro'] if data_row['intro'] else concept.intro, # intro
                    data_row['seq'],                    # sequence
                    0,                                  # children_count (初始为0)
                    data_row['is_category_node'],       # is_category_node
                    1,                                  # status
                    datetime.now(),                     # created
                    datetime.now()                      # modified
                )
                
                cursor.execute(insert_sql, values)
                node_id = cursor.lastrowid
                
                # 更新父节点的children_count
                cursor.execute(
                    "UPDATE term_tree_node SET children_count = children_count + 1 WHERE id = %s",
                    (parent_node_id,)
                )
                
                self.connection.commit()
                
                # 将新节点ID添加到映射中
                self.seq_to_node_id[data_row['seq']] = node_id
                
                info(f"成功创建节点 '{data_row['value']}' (ID: {node_id})")
                return node_id
                
        except Exception as e:
            error(f"创建节点失败: {e}")
            self.connection.rollback()
            return None
    
    def import_nodes(self, csv_file_path: str, term_tree_id: int, root_node_id: int) -> bool:
        """
        执行批量导入
        
        Args:
            csv_file_path: CSV文件路径
            term_tree_id: 术语树ID
            root_node_id: 根节点ID
            
        Returns:
            导入是否成功
        """
        color_print(f"开始批量导入term_tree_node...")
        
        # 1. 验证term_tree和根节点
        if not self.validate_term_tree_and_root(term_tree_id, root_node_id):
            return False
        
        # 2. 加载CSV数据
        data_list = self.load_csv_data(csv_file_path)
        if not data_list:
            return False
        
        # 3. 验证CSV中的tree_id是否一致
        for row in data_list:
            if row['tree_id'] != term_tree_id:
                error(f"CSV中的tree_id {row['tree_id']} 与指定的term_tree_id {term_tree_id} 不一致")
                return False
        
        # 4. 按顺序创建节点
        success_count = 0
        total_count = len(data_list)
        
        for row in data_list:
            info(f"处理节点 {row['seq']}/{total_count}: {row['value']}")
            node_id = self.create_term_tree_node(row, term_tree_id)
            if node_id:
                success_count += 1
            else:
                error(f"节点创建失败: {row['value']}")
                # 可以选择继续或停止
                user_input = input("继续处理剩余节点? (Y/n，默认Y): ").strip().lower()
                if user_input != '' and user_input != 'y':
                    break
        
        color_print(f"导入完成: 成功 {success_count}/{total_count} 个节点")
        return success_count == total_count
    
    def print_tree_structure(self, root_node_id: int, level: int = 0) -> None:
        """
        递归打印树形结构
        
        Args:
            root_node_id: 根节点ID
            level: 当前层级
        """
        try:
            with self.connection.cursor() as cursor:
                # 获取当前节点信息
                cursor.execute(
                    """SELECT id, node_concept_name, children_count, is_category_node
                       FROM term_tree_node 
                       WHERE id = %s AND status = 1""",
                    (root_node_id,)
                )
                node = cursor.fetchone()
                
                if not node:
                    return
                
                # 打印当前节点
                indent = "  " * level
                category_mark = " [分类]" if node['is_category_node'] else ""
                print(f"{indent}├─ {node['node_concept_name']}{category_mark} (ID: {node['id']})")
                
                # 获取子节点
                cursor.execute(
                    """SELECT id FROM term_tree_node 
                       WHERE parent_node_id = %s AND status = 1 
                       ORDER BY id ASC""",
                    (root_node_id,)
                )
                children = cursor.fetchall()
                
                # 递归打印子节点
                for child in children:
                    self.print_tree_structure(child['id'], level + 1)
                    
        except Exception as e:
            error(f"打印树形结构失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()
            debug("数据库连接已关闭")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='批量导入term_tree_node')
    parser.add_argument('csv_file', nargs='?', help='CSV文件路径')
    parser.add_argument('-t', '--term_tree_id', type=int, help='术语树ID')
    parser.add_argument('-r', '--root_node_id', type=int, help='根节点ID')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互式确认模式')
    parser.add_argument('-l', '--list', action='store_true', help='列出指定根节点下的树形结构')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    # 参数验证
    if args.list:
        # list模式下只需要root_node_id
        if not args.root_node_id:
            parser.error("--list 模式需要指定 --root_node_id")
    else:
        # 导入模式下需要所有参数
        if not args.csv_file:
            parser.error("导入模式需要指定CSV文件路径")
        if not args.term_tree_id:
            parser.error("导入模式需要指定 --term_tree_id") 
        if not args.root_node_id:
            parser.error("导入模式需要指定 --root_node_id")
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        if not args.list:
            debug(f"CSV文件: {args.csv_file}")
            debug(f"术语树ID: {args.term_tree_id}")
        debug(f"根节点ID: {args.root_node_id}")
        if not args.list:
            debug(f"交互模式: {args.interactive}")
        debug(f"列表模式: {args.list}")
        debug("-" * 50)

    # 初始化配置
    init_rbase_config()
    
    importer = None
    try:
        importer = TermTreeNodeImporter(configuration.config, args.interactive)
        
        if args.list:
            # 列表模式：只显示树形结构
            color_print(f"\n📊 节点 {args.root_node_id} 的树形结构:")
            color_print("=" * 60)
            importer.print_tree_structure(args.root_node_id)
            color_print("=" * 60)
            return 0
        else:
            # 导入模式：执行批量导入
            success = importer.import_nodes(args.csv_file, args.term_tree_id, args.root_node_id)
            
            if success:
                color_print("\n✅ 批量导入成功!")
                
                # 输出树形结构
                color_print("\n📊 完整树形结构:")
                color_print("=" * 60)
                importer.print_tree_structure(args.root_node_id)
                color_print("=" * 60)
                return 0
            else:
                error("\n❌ 批量导入失败!")
                return 1
            
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if importer:
            importer.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())
