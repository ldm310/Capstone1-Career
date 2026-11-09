import os
from dataclasses import dataclass

PREPROCESSING_VERSION = 'requirement-input-v1'
POLICY_VERSION = 'semantic-shadow-v1'


@dataclass(frozen=True)
class Config:
    model: str = 'text-embedding-3-small'
    revision: str = 'embedding-config-v1'
    dimensions: int = 1536
    preprocessing: str = PREPROCESSING_VERSION
    batch_items: int = 64
    batch_tokens: int = 8192
    input_tokens: int = 2048

    def __post_init__(self):
        if not self.model or not 1 <= self.dimensions <= 3072 or not 1 <= self.batch_items <= 64 or not 1 <= self.input_tokens <= 2048 or not self.input_tokens <= self.batch_tokens <= 8192:
            raise ValueError('INVALID_EMBEDDING_CONFIG')

    @classmethod
    def from_env(cls):
        return cls(model=os.getenv('OPENAI_EMBEDDING_MODEL','text-embedding-3-small'),
                   dimensions=int(os.getenv('OPENAI_EMBEDDING_DIMENSIONS','1536')))

    @property
    def key(self):
        return self.model,self.revision,self.dimensions,self.preprocessing
