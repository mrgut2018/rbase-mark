"""
MilvusSchema is the abstract base class for all Milvus table schemas, defining the schema_name attribute and four required methods.
"""
from abc import ABC, abstractmethod
from typing import List, Any, Union
import numpy as np
from pymilvus import DataType, MilvusClient, CollectionSchema
from pymilvus.milvus_client import IndexParams

from deepsearcher.loader.splitter import Chunk
from deepsearcher.vector_db.base import RetrievalResult

class MilvusSchema(ABC):
    """
    MilvusSchema is the abstract base class for all Milvus table schemas, 
    defining the schema_name attribute and 4 required methods that must be implemented.

    :param schema_name: schema name
    :return: MilvusSchema object
    """

    schema_name: str

    @abstractmethod
    def schema(self, client: MilvusClient, **kwargs) -> CollectionSchema:
        """
        Returns the CollectionSchema object for the current schema

        :param client: MilvusClient instance
        :return: CollectionSchema object
        """
        pass

    @abstractmethod
    def index_params(self, client: MilvusClient, **kwargs) -> IndexParams:
        """
        Returns the IndexParams object for the current schema

        :param client: MilvusClient instance
        :return: IndexParams object
        """
        pass

    @abstractmethod
    def prepare_insert_batch(self, chunks: List[Chunk], **kwargs) -> List[Any]:
        """
        Converts a list of Chunks into batch data format for Milvus insertion

        :param chunks: List of Chunk objects
        :return: Data array ready for Milvus insertion
        """
        pass

    @abstractmethod
    def search_data(self, client: MilvusClient, 
                    collection: str, 
                    vector: Union[np.array, List[float]],
                    **kwargs) -> List[RetrievalResult]:
        """
        Returns a list of RetrievalResult objects from search results for the current schema

        :param client: MilvusClient instance
        :param collection: Collection name
        :param vector: Query vector
        :param kwargs: Additional parameters
            - top_k: Number of results to return
            - filter: Query filter conditions
        :return: List of RetrievalResult objects
        """
        pass


class ArticleEntitySchema(MilvusSchema):
    schema_name = "article_entity"

    def schema(self, client: MilvusClient, **kwargs) -> CollectionSchema:
        description = kwargs.get("description", "")
        dim = kwargs.get("dim", 768)
        text_max_length = kwargs.get("text_max_length", 65535)
        reference_max_length = kwargs.get("reference_max_length", 2048)
        schema = client.create_schema(
            enable_dynamic_field=False, auto_id=True, description=description
        )
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("text", DataType.VARCHAR, max_length=text_max_length)
        schema.add_field("reference", DataType.VARCHAR, max_length=reference_max_length)
        schema.add_field("reference_id", DataType.INT64)
        schema.add_field(
            "keywords",
            DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_capacity=500,
            max_length=200,
        )
        schema.add_field(
            "authors",
            DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_capacity=200,
            max_length=100,
        )
        schema.add_field(
            "author_ids", DataType.ARRAY, element_type=DataType.INT64, max_capacity=500
        )
        schema.add_field(
            "corresponding_authors",
            DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_capacity=40,
            max_length=100,
        )
        schema.add_field(
            "corresponding_author_ids",
            DataType.ARRAY,
            element_type=DataType.INT64,
            max_capacity=100,
        )
        schema.add_field("base_ids", DataType.ARRAY, element_type=DataType.INT64, max_capacity=100)
        schema.add_field("impact_factor", DataType.FLOAT)
        schema.add_field("rbase_factor", DataType.FLOAT)
        schema.add_field("pubdate", DataType.INT64)
        schema.add_field("metadata", DataType.JSON, nullable=True)
        return schema

    def index_params(self, client: MilvusClient, **kwargs) -> IndexParams:
        metric_type = kwargs.get("metric_type", "L2")
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", metric_type=metric_type)
        index_params.add_index(field_name="keywords", index_type="", index_name="keywords_idx")
        index_params.add_index(field_name="authors", index_type="", index_name="authors_idx")
        index_params.add_index(
            field_name="author_ids", index_type="", index_name="author_ids_idx"
        )
        index_params.add_index(
            field_name="corresponding_authors",
            index_type="",
            index_name="corresponding_authors_idx",
        )
        index_params.add_index(
            field_name="corresponding_author_ids",
            index_type="",
            index_name="corresponding_author_ids_idx",
        )
        index_params.add_index(
            field_name="base_ids", index_type="", index_name="base_ids_idx"
        )
        index_params.add_index(
            field_name="impact_factor", index_type="", index_name="impact_factor_idx"
        )
        index_params.add_index(
            field_name="rbase_factor", index_type="", index_name="rbase_factor_idx"
        )
        index_params.add_index(field_name="pubdate", index_type="", index_name="pubdate_idx")
        return index_params

    def prepare_insert_batch(self, chunks: List[Chunk], **kwargs) -> List[Any]:
        batch_size = kwargs.get("batch_size", 256)

        embeddings = [chunk.embedding for chunk in chunks]
        texts = [chunk.text for chunk in chunks]
        references_list = [chunk.metadata.get("title", "") for chunk in chunks]
        reference_ids_list = [chunk.metadata.get("article_id", 0) for chunk in chunks]
        keywords_list = [chunk.metadata.get("keywords", []) for chunk in chunks]
        authors_list = [chunk.metadata.get("authors", []) for chunk in chunks]
        author_ids_list = [chunk.metadata.get("author_ids", []) for chunk in chunks]
        base_ids_list = [chunk.metadata.get("base_ids", []) for chunk in chunks]
        corresponding_authors_list = [
            chunk.metadata.get("corresponding_authors", []) for chunk in chunks
        ]
        corresponding_author_ids_list = [
            chunk.metadata.get("corresponding_author_ids", []) for chunk in chunks
        ]
        impact_factor_list = [chunk.metadata.get("impact_factor", 0) for chunk in chunks]
        rbase_factor_list = [chunk.metadata.get("rbase_factor", 0) for chunk in chunks]
        pubdate_list = [int(chunk.metadata.get("pubdate", 0)) for chunk in chunks]

        datas = [
            {
                "embedding": embedding,
                "text": text,
                "reference": reference,
                "reference_id": reference_id,
                "keywords": keywords,
                "authors": authors,
                "author_ids": author_ids,
                "corresponding_authors": corresponding_authors,
                "corresponding_author_ids": corresponding_author_ids,
                "impact_factor": impact_factor,
                "pubdate": pubdate,
                "rbase_factor": rbase_factor,
                "base_ids": base_ids,
            }
            for embedding, text, reference, reference_id, keywords, authors, author_ids, corresponding_authors, corresponding_author_ids, impact_factor, pubdate, rbase_factor, base_ids in zip(
                embeddings,
                texts,
                references_list,
                reference_ids_list,
                keywords_list,
                authors_list,
                author_ids_list,
                corresponding_authors_list,
                corresponding_author_ids_list,
                impact_factor_list,
                pubdate_list,
                rbase_factor_list,
                base_ids_list,
            )
        ]
        return [datas[i : i + batch_size] for i in range(0, len(datas), batch_size)]

    def search_data(self, client: MilvusClient, 
                    collection: str, 
                    vector: Union[np.array, List[float]],
                    **kwargs) -> List[RetrievalResult]:
        top_k = kwargs.get("top_k", 5)
        filter = kwargs.get("filter", "")
        try:
            search_results = client.search(
                collection_name=collection,
                data=[vector],
                limit=top_k,
                filter=filter,
                output_fields=[
                    "embedding",
                    "text",
                    "reference",
                    "reference_id",
                    "pubdate",
                    "impact_factor",
                ],
                timeout=10,
            )

            return [
                RetrievalResult(
                    embedding=b["entity"]["embedding"],
                    text=b["entity"]["text"],
                    reference=b["entity"]["reference"],
                    score=b["distance"],
                    metadata={
                        "reference_id": b["entity"]["reference_id"],
                        "pubdate": b["entity"]["pubdate"],
                        "impact_factor": b["entity"]["impact_factor"],
                    },
                )
                for a in search_results
                for b in a
            ]
        except Exception as e:
            raise e

class ClassifyValueEntitySchema(MilvusSchema):
    schema_name = "classify_value_entity"

    def schema(self, client: MilvusClient, **kwargs) -> CollectionSchema:
        description = kwargs.get("description", "")
        dim = kwargs.get("dim", 768)
        text_max_length = kwargs.get("text_max_length", 65535)
        schema = client.create_schema(
            enable_dynamic_field=False, auto_id=True, description=description
        )
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("text", DataType.VARCHAR, max_length=text_max_length)
        schema.add_field("classifier_id", DataType.INT64)
        schema.add_field("classifier_value_id", DataType.INT64)
        schema.add_field("metadata", DataType.JSON, nullable=True)
        return schema

    def index_params(self, client: MilvusClient, **kwargs) -> IndexParams:
        metric_type = kwargs.get("metric_type", "L2")
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", metric_type=metric_type)
        index_params.add_index(field_name="classifier_id", index_type="", index_name="classifier_id_idx")
        index_params.add_index(field_name="classifier_value_id", index_type="", index_name="classifier_value_id_idx")
        return index_params

    def prepare_insert_batch(self, chunks: List[Chunk], **kwargs) -> List[Any]:
        batch_size = kwargs.get("batch_size", 256)
        embeddings = [chunk.embedding for chunk in chunks]
        texts = [chunk.text for chunk in chunks]
        classifier_ids_list = [chunk.metadata.get("classifier_id", 0) for chunk in chunks]
        classifier_value_ids_list = [chunk.metadata.get("classifier_value_id", 0) for chunk in chunks]
        metadata_list = [chunk.metadata for chunk in chunks]

        datas = [
            {
                "embedding": embedding,
                "text": text,
                "classifier_id": classifier_id,
                "classifier_value_id": classifier_value_id,
                "metadata": metadata,
            }
            for embedding, text, classifier_id, classifier_value_id, metadata in zip(
                embeddings,
                texts,
                classifier_ids_list,
                classifier_value_ids_list,
                metadata_list,
            )
        ]
        return [datas[i : i + batch_size] for i in range(0, len(datas), batch_size)]
    
    def search_data(self, client: MilvusClient, 
                    collection: str, 
                    vector: Union[np.array, List[float]],
                    **kwargs) -> List[RetrievalResult]:
        top_k = kwargs.get("top_k", 5)
        filter = kwargs.get("filter", "")
        try:
            search_results = client.search(
                collection_name=collection,
                data=[vector],
                limit=top_k,
                filter=filter,
                output_fields=[
                    "embedding",
                    "text",
                    "classifier_id",
                    "classifier_value_id",
                    "metadata"
                ],
                timeout=10,
            )

            return [
                RetrievalResult(
                    embedding=b["entity"]["embedding"],
                    text=b["entity"]["text"],
                    reference="",
                    score=b["distance"],
                    metadata={
                        "classifier_id": b["entity"]["classifier_id"],
                        "classifier_value_id": b["entity"]["classifier_value_id"],
                        "terms": b["entity"]["metadata"].get("terms", []),
                    },
                )
                for a in search_results
                for b in a
            ]
        except Exception as e:
            raise e


def get_milvus_schema(schema_name: str) -> MilvusSchema:
    """
    Returns the corresponding MilvusSchema object based on schema_name

    :param schema_name: schema name
    :return: MilvusSchema object
    """
    if schema_name == "default" or schema_name == "article_entity":
        return ArticleEntitySchema()
    elif schema_name == "classify_value_entity":
        return ClassifyValueEntitySchema()
    else:
        raise ValueError(f"Invalid schema name: {schema_name}")
