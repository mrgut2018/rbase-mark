#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为指定classifier的所有取值创建向量数据库数据的脚本

该脚本的执行流程：
1. 获取classifier数据并校验classifier_method必须是命名实体匹配
2. 初始化collection，使用classify_value_entity schema
3. 对所有的classifier_value批量插入数据到向量数据库

作者: AI Assistant
创建时间: 2025年10月20日
"""

import sys
import os
import logging
import argparse
from typing import List
from tqdm import tqdm

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config
from deepsearcher.rbase.ai_models import ClassifyMethod
from deepsearcher.loader.splitter import Chunk
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher.vector_db.base import BaseVectorDB
from deepsearcher.embedding.base import BaseEmbedding
from deepsearcher.api.rbase_util import (
    load_terms_by_concept_id, 
    load_classifier_by_id, 
    list_classifier_values_by_classifier_id
)

# 抑制不必要的日志输出
logging.getLogger("httpx").setLevel(logging.WARNING)


class ClassifierValueVectorDBCreator:
    """Classifier Value向量数据库创建类"""
    
    def __init__(self, config: Configuration, vector_db: BaseVectorDB, embedding_model: BaseEmbedding):
        """
        初始化
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.vector_db = vector_db
        self.embedding_model = embedding_model
    
    def validate_classifier(self, classifier_id: int) -> bool:
        """
        验证classifier是否存在且classify_method为命名实体匹配
        
        Args:
            classifier_id: classifier的ID
            
        Returns:
            验证结果
        """
        try:
            # 加载classifier数据
            classifier = load_classifier_by_id(classifier_id)
            
            if not classifier:
                error(f"未找到ID为 {classifier_id} 的classifier")
                return False
            
            # 验证classify_method
            if classifier.classify_method != ClassifyMethod.NAMED_ENTITY_MATCHING:
                error(f"Classifier {classifier_id} 的classify_method不是命名实体匹配")
                error(f"当前classify_method: {classifier.classify_method}")
                error(f"期望classify_method: {ClassifyMethod.NAMED_ENTITY_MATCHING} (命名实体匹配)")
                return False
            
            info(f"找到Classifier: {classifier.name} (ID: {classifier_id})")
            info(f"分类器别名: {classifier.alias}")
            info(f"分类方法: 命名实体匹配")
            
            return True
            
        except Exception as e:
            error(f"验证classifier失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def prepare_chunks(self, classifier_id: int, collection_name: str, offset: int = 0, limit: int = 10240) -> List[Chunk]:
        """
        准备classifier_value的chunks数据
        
        Args:
            classifier_id: classifier的ID
            collection_name: collection名称
            offset: 偏移量
            limit: 限制数量
            
        Returns:
            Chunk列表
        """
        try:
            # 获取所有classifier_value
            classifier_values = list_classifier_values_by_classifier_id(classifier_id, offset, limit)
            
            if not classifier_values:
                error(f"Classifier {classifier_id} 没有任何取值")
                return []
            
            info(f"找到 {len(classifier_values)} 个classifier_value")
            
            chunks = []
            
            # 为每个classifier_value创建chunk并计算embedding
            for cv in tqdm(classifier_values, desc="创建chunks", total=len(classifier_values)):
                terms = load_terms_by_concept_id(cv.concept_id)
                term_metadatas = []
                for term in terms:
                    term_metadatas.append({
                        "term": term.name,
                        "term_id": term.id
                    })

                # 构建文本：使用value作为主要文本
                text = cv.value
                if cv.value_clue:
                    text += f": {cv.value_clue}"
                
                # 创建metadata
                metadata = {
                    "classifier_id": classifier_id,
                    "classifier_value_id": cv.id,
                    "terms": term_metadatas,
                }
                
                # 计算embedding
                embedding = self.embedding_model.embed_query(text)
                
                # 检查是否已存在相同的classifier_value
                results = self.vector_db.search_data(
                    collection=collection_name, 
                    vector=embedding, 
                    filter=f"classifier_value_id=={cv.id}",
                    top_k=1,
                    schema_name="classify_value_entity"
                )
                
                if len(results) > 0:
                    # 如果找到相同的ClassifierValue，则不创建chunk，直接跳过
                    debug(f"跳过已存在的ClassifierValue(text={results[0].text}, id={results[0].metadata['classifier_value_id']}, score={results[0].score})")
                else:
                    # 创建chunk（带embedding）
                    chunk = Chunk(
                        text=text,
                        reference=f"classifier_value_{cv.id}",
                        metadata=metadata,
                        embedding=embedding,
                    )
                    chunks.append(chunk)
                    debug(f"已创建 ClassifierValue({cv.id}) 的chunk: {text}")
            
            info(f"成功生成 {len(chunks)} 个chunks（带embeddings）")
            
            return chunks
            
        except Exception as e:
            error(f"准备chunks失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def create_vector_db(
        self, 
        classifier_id: int, 
        collection_name: str = "classifier_value_entities",
        collection_description: str = "Classifier Value Entities Dataset",
        force_new_collection: bool = False,
        batch_size: int = 256,
        offset: int = 0,
        limit: int = 10240
    ) -> bool:
        """
        创建向量数据库
        
        Args:
            classifier_id: classifier的ID
            collection_name: collection名称
            collection_description: collection描述
            force_new_collection: 是否强制创建新collection
            batch_size: 批量插入大小
            offset: 偏移量
            limit: 限制数量
            
        Returns:
            创建是否成功
        """
        try:
            # 1. 验证classifier
            if not self.validate_classifier(classifier_id):
                return False
            
            # 2. 初始化collection
            color_print(f"\n初始化collection: {collection_name}")
            
            # 规范化collection名称
            collection_name = collection_name.replace(" ", "_").replace("-", "_")
            
            # 初始化collection，使用classify_value_entity schema
            self.vector_db.init_collection(
                dim=self.embedding_model.dimension,
                collection=collection_name,
                description=collection_description,
                force_new_collection=force_new_collection,
                schema_name="classify_value_entity"
            )
            if force_new_collection:
                info(f"Collection {collection_name} 初始化成功")
            else:
                info(f"Collection {collection_name} 已准备")
            
            # 3. 准备chunks
            chunks = self.prepare_chunks(classifier_id, collection_name, offset=offset, limit=limit)
            
            if not chunks:
                error("没有可插入的数据")
                return False
            
            # 4. 批量插入数据
            color_print(f"\n开始插入数据到向量数据库...")
            insert_result = self.vector_db.insert_data(
                collection=collection_name,
                chunks=chunks,
                batch_size=batch_size,
                schema_name="classify_value_entity"
            )
            
            # 5. 输出结果
            if insert_result:
                insert_count = insert_result.get('insert_count', 0)
                ids = insert_result.get('ids', [])
                
                # Flush数据
                self.vector_db.flush(collection_name)
                
                color_print(f"\n✅ 成功创建向量数据库!")
                info(f"Collection名称: {collection_name}")
                info(f"插入数据量: {insert_count}")
                if ids:
                    info(f"ID范围: {min(ids)} - {max(ids)}")
                
                return True
            else:
                error("插入数据失败")
                return False
                
        except Exception as e:
            error(f"创建向量数据库失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='为classifier的所有取值创建向量数据库')
    parser.add_argument('-c', '--classifier_id', type=int, help='Classifier的ID')
    parser.add_argument('-e', '--env', type=str, help='环境名称，dev或prod，如果config.rbase_settings.env已配置则传参无效')
    parser.add_argument('-n', '--collection_name', type=str, default='classifier_value_entities',
                        help='Collection名称，默认为classifier_value_entities')
    parser.add_argument('-d', '--description', type=str, default='Classifier Value Entities Dataset',
                        help='Collection描述')
    parser.add_argument('-f', '--force_new_collection', action='store_true',
                        help='是否强制创建新collection，默认为False')
    parser.add_argument('-b', '--batch_size', type=int, default=256,
                        help='批量插入大小，默认为256')
    parser.add_argument('-o', '--offset', type=int, default=0,
                        help='偏移量，默认为0')
    parser.add_argument('-l', '--limit', type=int, default=10240,
                        help='限制数量，默认为10240')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='显示详细信息')
    
    args = parser.parse_args()
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
    
    info(f"Classifier ID: {args.classifier_id}")
    info(f"强制新建: {args.force_new_collection}")
    info(f"批量大小: {args.batch_size}")
    info(f"偏移量: {args.offset}")
    info(f"处理数量: {args.limit}")
    
    # 初始化配置
    init_rbase_config()
    
    if configuration.config.rbase_settings.get("env"):
        args.env = configuration.config.rbase_settings.get("env")
    
    if args.env != 'dev' and args.env != 'prod':
        error(f"环境 {args.env} 不支持")
        return

    args.collection_name = f"{args.env}_{args.collection_name}"
    info(f"环境：{args.env}")
    info(f"Collection名称: {args.collection_name}")
    info(f"开始时间: {__import__('datetime').datetime.now()}")
    info("-" * 50)
    
    # 创建向量数据库
    creator = ClassifierValueVectorDBCreator(configuration.config, vector_db=configuration.vector_db, embedding_model=configuration.embedding_model)
    success = creator.create_vector_db(
        classifier_id=args.classifier_id,
        collection_name=args.collection_name,
        collection_description=args.description,
        force_new_collection=args.force_new_collection,
        batch_size=args.batch_size,
        offset=args.offset,
        limit=args.limit
    )
    
    if args.verbose:
        debug(f"结束时间: {__import__('datetime').datetime.now()}")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

