from .api import EmbeddingClient

class VoyageClient(EmbeddingClient):
    def _request(self, texts, input_type):
        if self.sdk is None:
            import voyageai
            self.sdk = voyageai.Client(api_key=self.config.api_key, timeout=self.config.timeout_seconds, max_retries=0)
        result = self.sdk.embed(texts=texts, model=self.config.model, input_type=input_type,
            output_dimension=self.config.dimensions, truncation=False)
        return result.embeddings, result.total_tokens
