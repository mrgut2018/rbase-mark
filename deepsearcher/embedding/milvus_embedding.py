from typing import List

import numpy as np

from deepsearcher.embedding.base import BaseEmbedding

MILVUS_MODEL_DIM_MAP = {
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-large-zh-v1.5": 1024,
    "BAAI/bge-base-zh-v1.5": 768,
    "BAAI/bge-small-zh-v1.5": 384,
    "GPTCache/paraphrase-albert-onnx": 768,
    "default": 768,  # 'GPTCache/paraphrase-albert-onnx',
    # see https://github.com/milvus-io/milvus-model/blob/4974e2d190169618a06359bcda040eaed73c4d0f/src/pymilvus/model/dense/onnx.py#L12
    "jina-embeddings-v3": 1024,  # required jina api key
}


def _batch_onnx_encode(ort_session, tokenizer, texts: List[str]) -> List[np.ndarray]:
    """对 ONNX 模型做批量推理，逐条送入后拼接结果（ONNX 模型仅支持 batch_size=1）"""
    all_embeddings = []
    for text in texts:
        encoded = tokenizer.encode_plus(
            text, padding="max_length", truncation=True, return_tensors="np"
        )
        ort_inputs = {
            "input_ids": encoded["input_ids"].astype("int64"),
            "attention_mask": encoded["attention_mask"].astype("int64"),
            "token_type_ids": encoded["token_type_ids"].astype("int64"),
        }
        ort_outputs = ort_session.run(None, ort_inputs)
        token_embeddings = ort_outputs[0]  # (1, seq_len, dim)
        # mean pooling
        attention_mask = ort_inputs["attention_mask"]
        input_mask_expanded = (
            np.expand_dims(attention_mask, -1)
            .repeat(token_embeddings.shape[-1], -1)
            .astype(float)
        )
        sentence_emb = np.sum(token_embeddings * input_mask_expanded, 1) / np.maximum(
            input_mask_expanded.sum(1), 1e-9
        )
        all_embeddings.append(sentence_emb[0])
    # L2 normalize
    sentence_embs = np.stack(all_embeddings)
    norms = np.linalg.norm(sentence_embs, axis=1, keepdims=True)
    sentence_embs = sentence_embs / np.maximum(norms, 1e-9)
    return [sentence_embs[i] for i in range(len(texts))]


class MilvusEmbedding(BaseEmbedding):
    def __init__(self, model: str = None, **kwargs) -> None:
        model_name = model
        from pymilvus import model

        if "model_name" in kwargs and (not model_name or model_name == "default"):
            model_name = kwargs.pop("model_name")

        self._is_onnx = False
        if not model_name or model_name in [
            "default",
            "GPTCache/paraphrase-albert-onnx",
        ]:
            self.model = model.DefaultEmbeddingFunction(**kwargs)
            self._is_onnx = True
        else:
            if model_name.startswith("jina-"):
                self.model = model.dense.JinaEmbeddingFunction(model_name, **kwargs)
            elif model_name.startswith("BAAI/"):
                self.model = model.dense.SentenceTransformerEmbeddingFunction(model_name, **kwargs)
            else:
                # Only support default model and BGE series model
                raise ValueError(f"Currently unsupported model name: {model_name}")

    def embed_query(self, text: str) -> List[float]:
        return self.model.encode_queries([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._is_onnx and hasattr(self.model, "ort_session"):
            # 批量 ONNX 推理，避免逐条调用
            embeddings = _batch_onnx_encode(
                self.model.ort_session, self.model.tokenizer, texts
            )
        else:
            embeddings = self.model.encode_documents(texts)
        if isinstance(embeddings[0], np.ndarray):
            return [embedding.tolist() for embedding in embeddings]
        else:
            return embeddings

    @property
    def dimension(self) -> int:
        return self.model.dim  # or MILVUS_MODEL_DIM_MAP[self.model_name]
