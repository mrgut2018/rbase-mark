#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入分类器的脚本。

该脚本的执行流程：
1. 验证CSV数据的完整性和格式
2. 解析前置条件字符串并转换为JSON格式
3. 按照seq顺序创建分类器
4. 支持交互式确认模式
5. 处理分类器的各种配置参数

创建时间: 2025年9月29日
"""

import sys
import os
import logging
import json
import argparse
import csv
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from deepsearcher.rbase.ai_models import ClassifierType, ClassifyMethod, ClassifierStatus


class ClassifierImporter:
    """分类器批量导入类"""
    
    def __init__(self, config: Configuration, interactive_mode: bool = False):
        """初始化"""
        self.config = config
        self.connection = None
        self.interactive_mode = interactive_mode
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
    
    def parse_prerequisite(self, prerequisite_str: str) -> Optional[list]:
        """
        解析前置条件字符串并转换为JSON格式
        
        支持格式:
        - "article_type in [Article, Short Article]"
        - "original_research in [原创性研究]"
        - 多个条件用逗号分隔，但需要正确识别方括号内外的逗号
        
        Args:
            prerequisite_str: 前置条件字符串
            
        Returns:
            解析后的JSON列表，格式: [{'classifier_alias': 'xxx', 'value_in': ['xxx', 'xxx']}]
        """
        if not prerequisite_str or prerequisite_str.strip() == '':
            return None
        
        try:
            conditions = []
            
            # 使用更智能的方式分割条件，需要考虑方括号内的逗号不是分隔符
            parts = self._split_conditions(prerequisite_str)
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                # 使用正则表达式解析 "alias in [value1, value2]" 格式
                # 匹配方括号内的所有内容，包括逗号
                match = re.match(r'([a-zA-Z_]\w*)\s+in\s+\[(.*?)\]', part, re.DOTALL)
                if match:
                    classifier_alias = match.group(1).strip()
                    values_str = match.group(2).strip()
                    
                    # 解析值列表，支持带引号和不带引号的值
                    values = []
                    # 分割逗号分隔的值，但要考虑引号内的逗号
                    value_parts = self._split_values(values_str)
                    
                    for value in value_parts:
                        value = value.strip()
                        # 移除可能的引号
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                        if value:
                            values.append(value)
                    
                    if classifier_alias and values:
                        conditions.append({
                            'classifier_alias': classifier_alias,
                            'value_in': values
                        })
                        debug(f"解析前置条件: {classifier_alias} in {values}")
                else:
                    error(f"无法解析前置条件格式: {part}")
                    error(f"期望格式: 'classifier_alias in [value1, value2]'")
                    return None
            
            return conditions if conditions else None
            
        except Exception as e:
            error(f"解析前置条件失败: {e}")
            return None
    
    def _split_conditions(self, prerequisite_str: str) -> List[str]:
        """
        智能分割多个条件，考虑方括号内的逗号不是分隔符
        
        Args:
            prerequisite_str: 前置条件字符串
            
        Returns:
            分割后的条件列表
        """
        parts = []
        current_part = ""
        bracket_level = 0
        
        for char in prerequisite_str:
            if char == '[':
                bracket_level += 1
            elif char == ']':
                bracket_level -= 1
            elif char == ',' and bracket_level == 0:
                # 只有在方括号外的逗号才是条件分隔符
                if current_part.strip():
                    parts.append(current_part.strip())
                current_part = ""
                continue
            
            current_part += char
        
        # 添加最后一个部分
        if current_part.strip():
            parts.append(current_part.strip())
        
        return parts
    
    def _split_values(self, values_str: str) -> List[str]:
        """
        分割值列表，考虑引号内的逗号不是分隔符
        
        Args:
            values_str: 值字符串
            
        Returns:
            分割后的值列表
        """
        values = []
        current_value = ""
        in_quotes = False
        quote_char = None
        
        for char in values_str:
            if char in ['"', "'"] and not in_quotes:
                # 开始引号
                in_quotes = True
                quote_char = char
                current_value += char
            elif char == quote_char and in_quotes:
                # 结束引号
                in_quotes = False
                quote_char = None
                current_value += char
            elif char == ',' and not in_quotes:
                # 只有在引号外的逗号才是值分隔符
                if current_value.strip():
                    values.append(current_value.strip())
                current_value = ""
            else:
                current_value += char
        
        # 添加最后一个值
        if current_value.strip():
            values.append(current_value.strip())
        
        return values
    
    def load_csv_data(self, csv_file_path: str) -> List[Dict[str, Any]]:
        """
        加载CSV数据并验证
        
        Args:
            csv_file_path: CSV文件路径
            
        Returns:
            验证后的数据列表
        """
        try:
            data = []
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row_num, row in enumerate(reader, start=2):  # 从第2行开始（包含标题行）
                    # 跳过空行
                    if not any(value.strip() for value in row.values() if value):
                        continue
                    
                    try:
                        # 解析前置条件
                        prerequisite_json = self.parse_prerequisite(row.get('prerequisite', ''))
                        
                        # 转换数据类型
                        processed_row = {
                            'seq': int(row['seq']) if row['seq'].strip() else 0,
                            'name': row['name'].strip(),
                            'alias': row['alias'].strip(),
                            'ver': row['ver'].strip(),
                            'prerequisite': prerequisite_json,
                            'purpose': row['purpose'].strip(),
                            'target': row['target'].strip(),
                            'principle': row['principle'].strip(),
                            'criterion': row['criterion'].strip(),
                            'is_need_fulltext': int(row['is_need_fulltext']) if row['is_need_fulltext'].strip() else 1,
                            'is_allow_other_value': int(row['is_allow_other_value']) if row['is_allow_other_value'].strip() else 0,
                            'is_multi': int(row['is_multi']) if row['is_multi'].strip() else 0,
                            'multi_limit_min': int(row['multi_limit_min']) if row['multi_limit_min'].strip() else 0,
                            'multi_limit_max': int(row['multi_limit_max']) if row['multi_limit_max'].strip() else 0,
                            'is_include_sub_value': int(row['is_include_sub_value']) if row['is_include_sub_value'].strip() else 0,
                        }
                        
                        # 验证必填字段
                        required_fields = ['name', 'alias', 'ver', 'purpose', 'target']
                        for field in required_fields:
                            if not processed_row[field]:
                                error(f"第{row_num}行缺少必填字段: {field}")
                                continue
                        
                        data.append(processed_row)
                        
                    except ValueError as e:
                        error(f"第{row_num}行数据格式错误: {e}")
                        continue
            
            # 按seq排序
            data.sort(key=lambda x: x['seq'])
            
            info(f"成功加载 {len(data)} 条分类器数据")
            return data
            
        except Exception as e:
            error(f"加载CSV文件失败: {e}")
            return []
    
    def check_classifier_exists(self, alias: str, ver: str) -> Optional[int]:
        """
        检查分类器是否已存在
        
        Args:
            alias: 分类器别名
            ver: 版本号
            
        Returns:
            如果存在返回ID，否则返回None
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM classifier WHERE alias = %s AND ver = %s",
                    (alias, ver)
                )
                result = cursor.fetchone()
                return result['id'] if result else None
        except Exception as e:
            error(f"检查分类器是否存在失败: {e}")
            return None
    
    def create_classifier(self, data_row: Dict[str, Any]) -> Optional[int]:
        """
        创建分类器
        
        Args:
            data_row: CSV数据行
            
        Returns:
            创建的分类器ID，失败时返回None
        """
        try:
            # 检查是否已存在
            existing_id = self.check_classifier_exists(data_row['alias'], data_row['ver'])
            if existing_id:
                color_print(f"分类器 '{data_row['alias']}' (版本 {data_row['ver']}) 已存在 (ID: {existing_id})")
                if self.interactive_mode:
                    user_input = input("是否更新此分类器? (y/N，默认N): ").strip().lower()
                    if user_input == 'y':
                        return self.update_classifier(existing_id, data_row)
                    else:
                        info("跳过已存在的分类器")
                        return existing_id
                else:
                    info("自动跳过已存在的分类器")
                    return existing_id
            
            # 交互式确认
            if self.interactive_mode:
                color_print(f"\n准备创建分类器:")
                print(f"  序号: {data_row['seq']}")
                print(f"  名称: {data_row['name']}")
                print(f"  别名: {data_row['alias']}")
                print(f"  版本: {data_row['ver']}")
                print(f"  用途: {data_row['purpose']}")
                print(f"  目标: {data_row['target']}")
                print(f"  前置条件: {data_row['prerequisite']}")
                print(f"  是否需要全文: {data_row['is_need_fulltext']}")
                print(f"  是否多选: {data_row['is_multi']}")
                if data_row['is_multi']:
                    print(f"  多选范围: {data_row['multi_limit_min']}-{data_row['multi_limit_max']}")
                
                user_input = input("确认创建此分类器? (Y/n，默认Y): ").strip().lower()
                if user_input != '' and user_input != 'y':
                    info("用户取消创建")
                    return None
            
            # 插入分类器
            with self.connection.cursor() as cursor:
                insert_sql = """
                INSERT INTO classifier (
                    name, alias, ver, level, base_id, parent_classifier_id,
                    type, classify_method, classify_params, prerequisite,
                    term_tree_id, term_tree_node_id, purpose, target, principle, criterion,
                    is_need_full_text, is_allow_other_value, is_multi,
                    multi_limit_min, multi_limit_max, is_include_sub_value,
                    status, created, modified
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                """
                
                values = (
                    data_row['name'],                           # name
                    data_row['alias'],                          # alias
                    data_row['ver'],                            # ver
                    1,                                          # level (默认为1)
                    None,                                       # base_id (为空表示对总体数据)
                    None,                                       # parent_classifier_id
                    ClassifierType.VALUE_CLASSIFIER.value,     # type (默认为取值分类器)
                    ClassifyMethod.GENERAL_CLASSIFICATION.value, # classify_method (默认为一般性分类)
                    None,                                       # classify_params
                    json.dumps(data_row['prerequisite'], ensure_ascii=False) if data_row['prerequisite'] else None, # prerequisite
                    None,                                       # term_tree_id
                    None,                                       # term_tree_node_id
                    data_row['purpose'],                        # purpose
                    data_row['target'],                         # target
                    data_row['principle'],                      # principle
                    data_row['criterion'],                      # criterion
                    data_row['is_need_fulltext'],              # is_need_full_text
                    data_row['is_allow_other_value'],          # is_allow_other_value
                    data_row['is_multi'],                      # is_multi
                    data_row['multi_limit_min'],               # multi_limit_min
                    data_row['multi_limit_max'],               # multi_limit_max
                    data_row['is_include_sub_value'],          # is_include_sub_value
                    ClassifierStatus.NORMAL.value,             # status
                    datetime.now(),                            # created
                    datetime.now()                             # modified
                )
                
                cursor.execute(insert_sql, values)
                classifier_id = cursor.lastrowid
                
                self.connection.commit()
                
                info(f"成功创建分类器 '{data_row['name']}' (ID: {classifier_id})")
                return classifier_id
                
        except Exception as e:
            error(f"创建分类器失败: {e}")
            self.connection.rollback()
            return None
    
    def update_classifier(self, classifier_id: int, data_row: Dict[str, Any]) -> Optional[int]:
        """
        更新分类器
        
        Args:
            classifier_id: 分类器ID
            data_row: CSV数据行
            
        Returns:
            更新的分类器ID，失败时返回None
        """
        try:
            with self.connection.cursor() as cursor:
                update_sql = """
                UPDATE classifier SET
                    name = %s, purpose = %s, target = %s, principle = %s, criterion = %s,
                    prerequisite = %s, is_need_full_text = %s, is_allow_other_value = %s,
                    is_multi = %s, multi_limit_min = %s, multi_limit_max = %s,
                    is_include_sub_value = %s, modified = %s
                WHERE id = %s
                """
                
                values = (
                    data_row['name'],
                    data_row['purpose'],
                    data_row['target'],
                    data_row['principle'],
                    data_row['criterion'],
                    json.dumps(data_row['prerequisite'], ensure_ascii=False) if data_row['prerequisite'] else None,
                    data_row['is_need_fulltext'],
                    data_row['is_allow_other_value'],
                    data_row['is_multi'],
                    data_row['multi_limit_min'],
                    data_row['multi_limit_max'],
                    data_row['is_include_sub_value'],
                    datetime.now(),
                    classifier_id
                )
                
                cursor.execute(update_sql, values)
                self.connection.commit()
                
                info(f"成功更新分类器 '{data_row['name']}' (ID: {classifier_id})")
                return classifier_id
                
        except Exception as e:
            error(f"更新分类器失败: {e}")
            self.connection.rollback()
            return None
    
    def import_classifiers(self, csv_file_path: str) -> bool:
        """
        执行批量导入
        
        Args:
            csv_file_path: CSV文件路径
            
        Returns:
            导入是否成功
        """
        color_print(f"开始批量导入分类器...")
        
        # 1. 加载CSV数据
        data_list = self.load_csv_data(csv_file_path)
        if not data_list:
            return False
        
        # 2. 显示导入预览
        color_print(f"\n📋 导入预览 (共 {len(data_list)} 个分类器):")
        color_print("=" * 80)
        for row in data_list:
            print(f"  {row['seq']:2d}. {row['name']} ({row['alias']}) - {row['ver']}")
            if row['prerequisite']:
                print(f"      前置条件: {row['prerequisite']}")
        color_print("=" * 80)
        
        if self.interactive_mode:
            user_input = input("\n确认开始导入? (Y/n，默认Y): ").strip().lower()
            if user_input != '' and user_input != 'y':
                info("用户取消导入")
                return False
        
        # 3. 按顺序创建分类器
        success_count = 0
        total_count = len(data_list)
        
        for row in data_list:
            color_print(f"\n[{row['seq']}/{total_count}] 处理分类器: {row['name']} ({row['alias']})")
            classifier_id = self.create_classifier(row)
            if classifier_id:
                success_count += 1
            else:
                error(f"分类器创建失败: {row['name']}")
                if self.interactive_mode:
                    user_input = input("继续处理剩余分类器? (Y/n，默认Y): ").strip().lower()
                    if user_input != '' and user_input != 'y':
                        break
        
        color_print(f"\n📊 导入完成: 成功 {success_count}/{total_count} 个分类器")
        return success_count > 0
    
    def list_imported_classifiers(self) -> None:
        """列出已导入的分类器"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, alias, ver, purpose, prerequisite, status, created
                    FROM classifier 
                    ORDER BY id ASC
                """)
                classifiers = cursor.fetchall()
                
                if not classifiers:
                    info("数据库中没有分类器")
                    return
                
                color_print(f"\n📋 已导入的分类器 (共 {len(classifiers)} 个):")
                color_print("=" * 100)
                
                for cls in classifiers:
                    status_text = "正常" if cls['status'] == 1 else "无效"
                    print(f"ID: {cls['id']:2d} | {cls['name']} ({cls['alias']}) - {cls['ver']} | 状态: {status_text}")
                    print(f"      用途: {cls['purpose']}")
                    if cls['prerequisite']:
                        prerequisite = json.loads(cls['prerequisite']) if cls['prerequisite'] else None
                        print(f"      前置条件: {prerequisite}")
                    print(f"      创建时间: {cls['created']}")
                    print("-" * 100)
                
        except Exception as e:
            error(f"列出分类器失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()
            debug("数据库连接已关闭")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='批量导入分类器')
    parser.add_argument('csv_file', nargs='?', help='CSV文件路径')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互式确认模式')
    parser.add_argument('-l', '--list', action='store_true', help='列出已导入的分类器')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        debug(f"CSV文件: {args.csv_file}")
        debug(f"交互模式: {args.interactive}")
        debug("-" * 50)

    # 初始化配置
    init_rbase_config()
    
    importer = None
    try:
        importer = ClassifierImporter(configuration.config, args.interactive)
        
        if args.list:
            importer.list_imported_classifiers()
            return 0
        
        success = importer.import_classifiers(args.csv_file)
        
        if success:
            color_print("\n✅ 批量导入成功!")
            
            # 显示导入后的分类器列表
            importer.list_imported_classifiers()
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
