from .api import EmbeddingClient

class OpenAIClient(EmbeddingClient):
    def _request(self, texts, input_type):
        if self.sdk is None:
            from openai import OpenAI
            self.sdk = OpenAI(api_key=self.config.api_key, timeout=self.config.timeout_seconds, max_retries=0)
        result = self.sdk.embeddings.create(input=texts, model=self.config.model, dimensions=self.config.dimensions)
        rows = sorted(result.data, key=lambda row: row.index)
        if [row.index for row in rows] != list(range(len(texts))):
            raise ValueError("Invalid embedding indices")
        return [row.embedding for row in rows], getattr(result.usage, "total_tokens", None)
