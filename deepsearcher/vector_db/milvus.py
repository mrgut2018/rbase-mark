from typing import List, Optional, Union

import numpy as np
from pymilvus import DataType, MilvusClient

from deepsearcher.loader.splitter import Chunk
from deepsearcher.tools import log
from deepsearcher.vector_db.base import BaseVectorDB, CollectionInfo, RetrievalResult

from deepsearcher.vector_db.milvus_schema import MilvusSchema, get_milvus_schema


class Milvus(BaseVectorDB):
    """Milvus vector database implementation that extends BaseVectorDB."""

    client: MilvusClient = None

    def __init__(
        self,
        default_collection: str = "deepsearcher",
        uri: str = "http://localhost:19530",
        token: str = "root:Milvus",
        db: str = "default",
        schema_name: str = "default"
    ):
        """
        Initialize Milvus client with connection parameters.

        Args:
            default_collection: Name of the default collection
            uri: Milvus server URI
            token: Authentication token
            db: Database name
        """
        super().__init__(default_collection)
        self.default_collection = default_collection
        self.uri = uri
        self.token = token
        self.db = db
        self.schema = get_milvus_schema(schema_name)
        self.schema_name = schema_name
        self.connect()
    
    def connect(self):
        self.client = MilvusClient(uri=self.uri, token=self.token, db_name=self.db, timeout=30)

    def check_connection(self):
        try:
            self.client.get_server_version()
        except Exception as e:
            log.critical(f"fail to check connection, error info: {e}")
            self.connect()

    def refresh_schema(self, schema_name: str):
        if schema_name != self.schema_name:
            self.schema_name = schema_name
            self.schema = get_milvus_schema(schema_name)

    def init_collection(
        self,
        dim: int,
        collection: Optional[str] = "deepsearcher",
        description: Optional[str] = "",
        force_new_collection: bool = False,
        text_max_length: int = 65_535,
        reference_max_length: int = 2048,
        metric_type: str = "L2",
        schema_name: str = "default",
        *args,
        **kwargs,
    ):
        """
        Initialize a new collection with specified schema and indexes.

        Args:
            dim: Dimension of the vector embeddings
            collection: Collection name
            description: Collection description
            force_new_collection: Whether to drop existing collection
            text_max_length: Maximum length for text field
            reference_max_length: Maximum length for reference field
            metric_type: Distance metric type for vector similarity
        """
        self.check_connection()
        if not collection:
            collection = self.default_collection
        if description is None:
            description = ""

        self.refresh_schema(schema_name)
        try:
            has_collection = self.client.has_collection(collection, timeout=5)
            if force_new_collection and has_collection:
                self.client.drop_collection(collection)
            elif has_collection:
                return

            schema = self.schema.schema(self.client, description=description, dim=dim, text_max_length=text_max_length, reference_max_length=reference_max_length)
            index_params = self.schema.index_params(self.client, metric_type=metric_type)
            self.client.create_collection(
                collection,
                schema=schema,
                index_params=index_params,
                consistency_level="Strong",
            )
            log.color_print(f"create collection [{collection}] successfully")
        except Exception as e:
            log.critical(f"fail to init db for milvus, error info: {e}")

    def insert_data(
        self,
        collection: Optional[str],
        chunks: List[Chunk],
        batch_size: int = 256,
        schema_name: str = "default",
        *args,
        **kwargs,
    ):
        """
        Insert data into the vector database.

        Args:
            collection: Collection name
            chunks: List of data chunks to insert
            batch_size: Batch size for insertion

        Returns:
            Dictionary containing total insert count and list of inserted IDs
        """
        if not collection:
            collection = self.default_collection

        self.check_connection()
        self.refresh_schema(schema_name)
        batch_datas = self.schema.prepare_insert_batch(chunks, batch_size=batch_size)

        # Initialize result summary
        total_result = {"insert_count": 0, "ids": []}

        try:
            for batch_data in batch_datas:
                res = self.client.insert(collection_name=collection, data=batch_data)
                # Aggregate results
                if res:
                    total_result["insert_count"] += res.get("insert_count", 0)
                    if "ids" in res:
                        # Check and process IDs appropriately
                        total_result["ids"].extend(list(res["ids"]))
            # Return aggregated results
            return total_result
        except Exception as e:
            log.critical(f"fail to insert data, error info: {e}")
            return {"insert_count": 0, "ids": []}

    def search_data(
        self,
        collection: Optional[str],
        vector: Union[np.array, List[float]],
        top_k: int = 5,
        filter: Optional[str] = "",
        schema_name: str = "default",
        *args,
        **kwargs,
    ) -> List[RetrievalResult]:
        """
        Search for most similar vectors in the database.

        Args:
            collection: Collection name
            vector: Query vector
            top_k: Number of most similar results to return
            filter: Query filter expression in Milvus syntax

        Returns:
            List of RetrievalResult objects containing search results
        """
        if not collection:
            collection = self.default_collection
        self.check_connection()
        try:
            self.refresh_schema(schema_name)
            return self.schema.search_data(self.client, collection, vector, top_k=top_k, filter=filter)
        except Exception as e:
            log.critical(f"fail to search data, error info: {e}")
            return []

    def list_collections(self, *args, **kwargs) -> List[CollectionInfo]:
        """
        List all collections in the database.

        Returns:
            List of CollectionInfo objects containing collection details
        """
        self.check_connection()
        collection_infos = []
        try:
            collections = self.client.list_collections()
            for collection in collections:
                description = self.client.describe_collection(collection)
                collection_infos.append(
                    CollectionInfo(
                        collection_name=collection,
                        description=description["description"],
                    )
                )
        except Exception as e:
            log.critical(f"fail to list collections, error info: {e}")
        return collection_infos

    def clear_db(self, collection: str = "deepsearcher", *args, **kwargs):
        """
        Clear the specified collection from the database.

        Args:
            collection: Name of the collection to clear
        """
        if not collection:
            collection = self.default_collection
        self.check_connection()
        try:
            self.client.drop_collection(collection)
        except Exception as e:
            log.warning(f"fail to clear db, error info: {e}")

    def delete_data(self, collection: str, ids: Optional[List[int]] = None, filter: Optional[str] = None, *args, **kwargs) -> int:
        """
        Delete data from the specified collection based on the filter.

        Args:
            collection: Collection name
            filter: Filter expression in Milvus syntax
            ids: List of IDs to delete

        Returns:
            Number of deleted documents
        """
        if not ids and not filter:
            log.warning("no ids or filter provided, skip delete")
            return 0

        self.check_connection()
        try:
            if ids:
                rt = self.client.delete(collection_name=collection, filter=filter, ids=ids)
            else:
                rt = self.client.delete(collection_name=collection, filter=filter)
            return rt.get("delete_count", 0)
        except Exception as e:
            log.critical(f"fail to delete data, error info: {e}")
    
    def flush(self, collection_name: str, **kwargs):
        self.check_connection()
        timeout = kwargs.get("timeout", None)
        self.client.flush(collection_name, timeout)
        
    def close(self):
        self.client.close()