"""cat_ai.py가 쓰는 규칙 표(AI 기술). 버림용 스파이크(2026-11-26, 제품 코드 아님).

- 모두 「제안」(Claude 정의, 사용자가 2026-11-26 'Claude가 정해서 결과와 이유를 알려 달라'고 함). 문서에는 변수 이름·시작값만 있다.
- 연동 1개 = (제공자, API 종류) 쌍(B-37 후보 B). 로컬 모델(Hugging Face·Whisper·YOLO·MediaPipe·Ollama 등)은 local=True로 따로 표시.
"""
import re

# ---------------------------------------------------------------- Python: 풀이한 호출 이름(별칭·인스턴스 따라감) → (제공자, 종류, local)
# 이름은 'openai.OpenAI().chat.completions.create' 꼴(인스턴스는 '()'로 표시)
_OAI = r'^openai\.(?:(?:Async)?(?:Azure)?OpenAI\(\)\.)?'
PY_API = [
    (_OAI + r'(?:beta\.)?chat\.completions\.(?:create|parse|stream)$', 'OpenAI', 'chat'),
    (_OAI + r'responses\.(?:create|parse|stream)$', 'OpenAI', 'chat'),
    (_OAI + r'completions\.create$', 'OpenAI', 'chat'),
    (_OAI + r'embeddings\.create$', 'OpenAI', 'embedding'),
    (_OAI + r'audio\.(?:transcriptions|translations)\.create$', 'OpenAI', 'speech-to-text'),
    (_OAI + r'audio\.speech\.create$', 'OpenAI', 'text-to-speech'),
    (_OAI + r'images\.(?:generate|edit|create_variation)$', 'OpenAI', 'image-generation'),
    (_OAI + r'moderations\.create$', 'OpenAI', 'moderation'),
    (_OAI + r'fine_tuning\.jobs\.create$', 'OpenAI', 'fine-tuning'),
    (_OAI + r'beta\.(?:threads|assistants)\..*(?:create|create_and_poll|stream)$', 'OpenAI', 'chat'),
    (r'^openai\.(?:ChatCompletion|Completion)\.a?create$', 'OpenAI', 'chat'),
    (r'^openai\.Embedding\.a?create$', 'OpenAI', 'embedding'),
    (r'^openai\.Image\.a?create$', 'OpenAI', 'image-generation'),
    (r'^openai\.Audio\.(?:transcribe|translate|atranscribe)$', 'OpenAI', 'speech-to-text'),
    (r'^openai\.FineTuningJob\.create$', 'OpenAI', 'fine-tuning'),
    (r'^anthropic\.(?:Async)?Anthropic(?:Bedrock|Vertex)?\(\)\.(?:beta\.)?messages\.(?:create|stream|count_tokens|parse)$', 'Anthropic', 'chat'),
    (r'^anthropic\.(?:Async)?Anthropic\(\)\.completions\.create$', 'Anthropic', 'chat'),
    (r'^google\.generativeai\.GenerativeModel\(\)\.(?:start_chat\(\)\.)?(?:generate_content|generate_content_async|send_message|send_message_async|count_tokens)$', 'Gemini', 'chat'),
    (r'^google\.generativeai\.(?:embed_content|embed_content_async)$', 'Gemini', 'embedding'),
    (r'^google\.generativeai\.(?:generate_text|chat)$', 'Gemini', 'chat'),
    (r'^google\.genai\.Client\(\)\.(?:aio\.)?models\.(?:generate_content|generate_content_stream)$', 'Gemini', 'chat'),
    (r'^google\.genai\.Client\(\)\.(?:aio\.)?models\.embed_content$', 'Gemini', 'embedding'),
    (r'^google\.genai\.Client\(\)\.(?:aio\.)?models\.(?:generate_images|generate_videos)$', 'Gemini', 'image-generation'),
    (r'^google\.genai\.Client\(\)\.(?:aio\.)?chats\.create\(\)\.(?:send_message|send_message_stream)$', 'Gemini', 'chat'),
    (r'^vertexai\.(?:preview\.)?generative_models\.GenerativeModel\(\)\.(?:start_chat\(\)\.)?(?:generate_content|send_message)$', 'Vertex AI', 'chat'),
    (r'^vertexai\.(?:preview\.)?language_models\.TextEmbeddingModel\.from_pretrained\(\)\.get_embeddings$', 'Vertex AI', 'embedding'),
    (r'^ollama\.(?:Async)?Client\(\)\.(?:chat|generate)$|^ollama\.(?:chat|generate)$', 'Ollama', 'chat', True),
    (r'^ollama\.(?:Async)?Client\(\)\.(?:embeddings|embed)$|^ollama\.(?:embeddings|embed)$', 'Ollama', 'embedding', True),
    (r'^cohere\.(?:Async)?Client(?:V2)?\(\)\.(?:chat|generate|chat_stream)$', 'Cohere', 'chat'),
    (r'^cohere\.(?:Async)?Client(?:V2)?\(\)\.embed$', 'Cohere', 'embedding'),
    (r'^cohere\.(?:Async)?Client(?:V2)?\(\)\.rerank$', 'Cohere', 'rerank'),
    (r'^mistralai\.(?:client\.)?(?:Mistral|MistralClient)\(\)\.(?:chat\.(?:complete|stream)|chat)$', 'Mistral', 'chat'),
    (r'^mistralai\.(?:client\.)?(?:Mistral|MistralClient)\(\)\.(?:embeddings\.create|embeddings)$', 'Mistral', 'embedding'),
    (r'^groq\.(?:Async)?Groq\(\)\.chat\.completions\.create$', 'Groq', 'chat'),
    (r'^groq\.(?:Async)?Groq\(\)\.audio\.transcriptions\.create$', 'Groq', 'speech-to-text'),
    (r'^together\.(?:Async)?Together\(\)\.chat\.completions\.create$', 'Together', 'chat'),
    (r'^replicate\.(?:run|predictions\.create|async_run)$', 'Replicate', 'model-run'),
    (r'^huggingface_hub\.(?:Async)?InferenceClient\(\)\.(?:chat_completion|text_generation|chat\.completions\.create)$', 'Hugging Face API', 'chat'),
    (r'^huggingface_hub\.(?:Async)?InferenceClient\(\)\.feature_extraction$', 'Hugging Face API', 'embedding'),
    (r'^huggingface_hub\.(?:Async)?InferenceClient\(\)\.(?:text_to_image|image_classification|object_detection|image_to_text)$', 'Hugging Face API', 'vision'),
    (r'^huggingface_hub\.(?:Async)?InferenceClient\(\)\.(?:automatic_speech_recognition|text_to_speech)$', 'Hugging Face API', 'speech'),
    (r'^sentence_transformers\.SentenceTransformer\(\)\.encode', 'Hugging Face(로컬)', 'embedding', True),
    (r'^sentence_transformers\.CrossEncoder\(\)\.(?:predict|rank)$', 'Hugging Face(로컬)', 'rerank', True),
    (r'^whisper\.load_model\(\)\.transcribe$|^faster_whisper\.WhisperModel\(\)\.transcribe$', 'Whisper(로컬)', 'speech-to-text', True),
    (r'^ultralytics\.(?:YOLO|RTDETR)\(\)(?:\.predict|\.track|\.val)?$', 'YOLO(로컬)', 'vision', True),
    (r'^mediapipe\.solutions\.\w+\.\w+\(\)\.process$', 'MediaPipe(로컬)', 'vision', True),
    (r'^easyocr\.Reader\(\)\.readtext$', 'EasyOCR(로컬)', 'vision', True),
    (r'^deepface\.DeepFace\.(?:analyze|verify|find|represent)$', 'DeepFace(로컬)', 'vision', True),
    (r'^google\.cloud\.vision(?:_v1)?\.ImageAnnotatorClient\(\)\.\w+$', 'Google Cloud Vision', 'vision'),
    (r'^google\.cloud\.speech(?:_v1|_v2)?\.SpeechClient\(\)\.(?:recognize|long_running_recognize|streaming_recognize)$', 'Google Cloud Speech', 'speech-to-text'),
    (r'^google\.cloud\.texttospeech\.TextToSpeechClient\(\)\.synthesize_speech$', 'Google Cloud TTS', 'text-to-speech'),
    (r'^google\.cloud\.language(?:_v1|_v2)?\.LanguageServiceClient\(\)\.\w+$', 'Google Cloud NL', 'nlp'),
    (r'^elevenlabs\.(?:client\.)?ElevenLabs\(\)\.(?:text_to_speech\.convert|generate)$|^elevenlabs\.generate$', 'ElevenLabs', 'text-to-speech'),
    (r'^llama_index\..*\.(?:query|chat|complete|stream_chat|astream_chat|aquery)$', 'LlamaIndex', 'chat'),
    (r'^pyannote\.audio\.Pipeline\.from_pretrained\(\)$', 'pyannote(로컬)', 'speech', True),
    (r'^litellm\.(?:Router\(\)\.)?a?completion$', 'LiteLLM', 'chat'),
    (r'^litellm\.(?:Router\(\)\.)?a?embedding$', 'LiteLLM', 'embedding'),
    (r'^instructor\.(?:from_\w+|patch)\(\)\.(?:chat\.completions\.create|messages\.create|create|create_with_completion)$', 'Instructor(LLM)', 'chat'),
]
PY_API = [(re.compile(t[0]), t[1], t[2], (t[3] if len(t) > 3 else False)) for t in PY_API]

# transformers pipeline(task) → 종류
HF_TASK = {'text-generation': 'chat', 'text2text-generation': 'chat', 'conversational': 'chat', 'summarization': 'nlp',
           'translation': 'nlp', 'sentiment-analysis': 'nlp', 'text-classification': 'nlp', 'zero-shot-classification': 'nlp',
           'ner': 'nlp', 'token-classification': 'nlp', 'question-answering': 'nlp', 'fill-mask': 'nlp', 'feature-extraction': 'embedding',
           'automatic-speech-recognition': 'speech-to-text', 'text-to-speech': 'text-to-speech', 'image-classification': 'vision',
           'object-detection': 'vision', 'image-segmentation': 'vision', 'image-to-text': 'vision', 'zero-shot-image-classification': 'vision',
           'depth-estimation': 'vision', 'visual-question-answering': 'vision', 'document-question-answering': 'vision'}

# LangChain·LlamaIndex 생성자(쓰인 이름일 때만 센다) → (제공자, 종류, local)
LC_CTOR = {
    'ChatOpenAI': ('OpenAI', 'chat', False), 'OpenAI': ('OpenAI', 'chat', False), 'AzureChatOpenAI': ('Azure OpenAI', 'chat', False),
    'OpenAIEmbeddings': ('OpenAI', 'embedding', False), 'AzureOpenAIEmbeddings': ('Azure OpenAI', 'embedding', False),
    'ChatAnthropic': ('Anthropic', 'chat', False), 'ChatGoogleGenerativeAI': ('Gemini', 'chat', False),
    'GoogleGenerativeAI': ('Gemini', 'chat', False), 'GoogleGenerativeAIEmbeddings': ('Gemini', 'embedding', False),
    'ChatVertexAI': ('Vertex AI', 'chat', False), 'VertexAIEmbeddings': ('Vertex AI', 'embedding', False),
    'ChatOllama': ('Ollama', 'chat', True), 'Ollama': ('Ollama', 'chat', True), 'OllamaLLM': ('Ollama', 'chat', True),
    'OllamaEmbeddings': ('Ollama', 'embedding', True), 'ChatGroq': ('Groq', 'chat', False), 'ChatMistralAI': ('Mistral', 'chat', False),
    'MistralAIEmbeddings': ('Mistral', 'embedding', False), 'ChatCohere': ('Cohere', 'chat', False), 'CohereEmbeddings': ('Cohere', 'embedding', False),
    'ChatUpstage': ('Upstage', 'chat', False), 'UpstageEmbeddings': ('Upstage', 'embedding', False),
    'ChatBedrock': ('AWS Bedrock', 'chat', False), 'BedrockEmbeddings': ('AWS Bedrock', 'embedding', False), 'ChatBedrockConverse': ('AWS Bedrock', 'chat', False),
    'HuggingFaceEmbeddings': ('Hugging Face(로컬)', 'embedding', True), 'HuggingFaceBgeEmbeddings': ('Hugging Face(로컬)', 'embedding', True),
    'SentenceTransformerEmbeddings': ('Hugging Face(로컬)', 'embedding', True), 'HuggingFacePipeline': ('Hugging Face(로컬)', 'chat', True),
    'HuggingFaceEndpoint': ('Hugging Face API', 'chat', False), 'HuggingFaceHub': ('Hugging Face API', 'chat', False),
    'ChatHuggingFace': ('Hugging Face API', 'chat', False), 'ChatPerplexity': ('Perplexity', 'chat', False),
    'ChatDeepSeek': ('DeepSeek', 'chat', False), 'ChatTogether': ('Together', 'chat', False), 'ChatClovaX': ('HyperCLOVA X', 'chat', False),
    'ClovaXEmbeddings': ('HyperCLOVA X', 'embedding', False), 'OpenAIEmbedding': ('OpenAI', 'embedding', False), 'Gemini': ('Gemini', 'chat', False),
    'GeminiEmbedding': ('Gemini', 'embedding', False), 'HuggingFaceEmbedding': ('Hugging Face(로컬)', 'embedding', True),
}
LC_MOD = re.compile(r'^(langchain[\w.]*|llama_index[\w.]*)\.(\w+)\(\)$')

# 외부 AI 주소(어느 언어든 문자열) → 제공자. 경로로 종류를 고른다
AI_HOSTS = [
    (r'api\.openai\.com', 'OpenAI'), (r'[\w-]+\.openai\.azure\.com', 'Azure OpenAI'), (r'api\.anthropic\.com', 'Anthropic'),
    (r'generativelanguage\.googleapis\.com', 'Gemini'), (r'aiplatform\.googleapis\.com', 'Vertex AI'),
    (r'api-inference\.huggingface\.co|router\.huggingface\.co', 'Hugging Face API'), (r'api\.cohere\.(?:ai|com)', 'Cohere'),
    (r'api\.mistral\.ai', 'Mistral'), (r'api\.groq\.com', 'Groq'), (r'api\.together\.(?:xyz|ai)', 'Together'),
    (r'api\.upstage\.ai', 'Upstage'), (r'clovastudio\.(?:apigw|stream)\.ntruss\.com', 'HyperCLOVA X'),
    (r'naveropenapi\.apigw\.ntruss\.com/(?:vision|recog|tts|voice|sentiment|text-summary|image)', 'Naver Clova AI'),
    (r'api\.perplexity\.ai', 'Perplexity'), (r'api\.deepseek\.com', 'DeepSeek'), (r'openrouter\.ai/api', 'OpenRouter'),
    (r'(?:localhost|127\.0\.0\.1|ollama):11434', 'Ollama'), (r'api\.replicate\.com', 'Replicate'), (r'api\.stability\.ai', 'Stability'),
    (r'api\.elevenlabs\.io', 'ElevenLabs'), (r'api\.x\.ai', 'xAI'), (r'speech\.googleapis\.com', 'Google Cloud Speech'),
    (r'vision\.googleapis\.com', 'Google Cloud Vision'), (r'texttospeech\.googleapis\.com', 'Google Cloud TTS'),
    (r'api\.kakaobrain\.com', 'Kakao Brain'), (r'bedrock-runtime\.[\w-]+\.amazonaws\.com', 'AWS Bedrock'),
]
AI_HOSTS = [(re.compile(a), b) for a, b in AI_HOSTS]
HOST_KIND = [(re.compile(r'/(?:v\d+/)?(?:chat/completions|responses|messages|completions)\b|:generateContent|:streamGenerateContent|/generate\b|/chat\b'), 'chat'),
             (re.compile(r'/embeddings?\b|:embedContent|:batchEmbedContents|/embed\b'), 'embedding'),
             (re.compile(r'/audio/transcriptions|/recog|speech:recognize|/stt'), 'speech-to-text'),
             (re.compile(r'/audio/speech|/tts|text:synthesize'), 'text-to-speech'),
             (re.compile(r'/images/generations|/vision|images:annotate|/image'), 'vision')]


def host_hit(s):
    for rx, prov in AI_HOSTS:
        m = rx.search(s)
        if m:
            kind = 'api'
            for krx, k in HOST_KIND:
                if krx.search(s):
                    kind = k
                    break
            if prov == 'Ollama' and kind == 'api':
                kind = 'chat'
            return prov, kind
    return None


# ---------------------------------------------------------------- 기법 목록(「제안」 B-38, Claude 결정)
TECH_LLM = ['rag', 'embedding_search', 'tool_calling', 'agent', 'mcp', 'structured_output', 'prompt_template', 'prompt_chain', 'llm_eval', 'fine_tuning']
TECH_ML = ['model_training', 'data_split', 'preprocess_pipeline', 'hyperparam_search', 'cross_validation', 'transfer_learning', 'eval_metrics',
           'model_save', 'serving', 'data_versioning']
TECH_NAME = {
    'rag': 'RAG(검색한 문서를 프롬프트에 넣어 생성)', 'embedding_search': '임베딩 검색(벡터 저장·유사도 검색)', 'tool_calling': '도구 호출(function calling)',
    'agent': '에이전트(여러 단계 도구 루프)', 'mcp': 'MCP 서버·클라이언트', 'structured_output': '구조화 출력(JSON 스키마·파서)',
    'prompt_template': '프롬프트 템플릿 관리', 'prompt_chain': '프롬프트 체인(앞 LLM 결과를 다음 LLM 입력으로)', 'llm_eval': 'LLM 평가',
    'fine_tuning': 'LLM 미세 조정', 'model_training': 'ML 모델 학습', 'data_split': '데이터 나누기', 'preprocess_pipeline': '전처리 파이프라인',
    'hyperparam_search': '하이퍼파라미터 탐색', 'cross_validation': '교차 검증', 'transfer_learning': '전이 학습', 'eval_metrics': '평가 지표',
    'model_save': '모델 저장', 'serving': '모델 서빙(학습 모델을 API·화면에서 추론)', 'data_versioning': '데이터 버전 관리(DVC 등)'}
# 작업 지시문에 적힌 예(RAG·임베딩 검색·에이전트·프롬프트 체인·파인튜닝·ML 모델 학습)만 쓰는 좁은 목록(대안)
TECH_NARROW = {'rag', 'embedding_search', 'agent', 'prompt_chain', 'fine_tuning', 'model_training'}

SK_METRICS = {'accuracy_score', 'f1_score', 'precision_score', 'recall_score', 'roc_auc_score', 'mean_squared_error', 'mean_absolute_error',
              'r2_score', 'classification_report', 'confusion_matrix', 'log_loss', 'mean_absolute_percentage_error', 'average_precision_score',
              'precision_recall_fscore_support', 'balanced_accuracy_score', 'root_mean_squared_error', 'mean_squared_log_error', 'roc_curve',
              'precision_recall_curve', 'matthews_corrcoef', 'cohen_kappa_score', 'top_k_accuracy_score', 'ndcg_score', 'silhouette_score'}
SK_CV = {'cross_val_score', 'cross_validate', 'cross_val_predict', 'KFold', 'StratifiedKFold', 'GroupKFold', 'RepeatedKFold', 'TimeSeriesSplit',
         'StratifiedGroupKFold', 'LeaveOneOut', 'RepeatedStratifiedKFold', 'ShuffleSplit', 'StratifiedShuffleSplit'}
SK_SEARCH = {'GridSearchCV', 'RandomizedSearchCV', 'HalvingGridSearchCV', 'HalvingRandomSearchCV', 'BayesSearchCV'}
SK_PIPE = {'Pipeline', 'make_pipeline', 'ColumnTransformer', 'make_column_transformer', 'FeatureUnion'}
SK_PREP = {'StandardScaler', 'MinMaxScaler', 'RobustScaler', 'LabelEncoder', 'OneHotEncoder', 'OrdinalEncoder', 'SimpleImputer', 'MaxAbsScaler',
           'Normalizer', 'PolynomialFeatures', 'KNNImputer', 'TfidfVectorizer', 'CountVectorizer'}
ML_EST_MOD = re.compile(r'^(sklearn|xgboost|lightgbm|catboost|keras|tensorflow\.keras|tf\.keras|tensorflow|statsmodels|prophet|pmdarima)\b')
PRETRAIN_KW = {'pretrained', 'weights', 'include_top'}
LC_RAG = {'RetrievalQA', 'create_retrieval_chain', 'ConversationalRetrievalChain', 'RetrievalQAWithSourcesChain', 'create_history_aware_retriever'}
LC_AGENT = {'initialize_agent', 'create_react_agent', 'create_openai_functions_agent', 'create_tool_calling_agent', 'AgentExecutor',
            'create_openai_tools_agent', 'create_structured_chat_agent', 'create_agent', 'StateGraph', 'MessageGraph', 'create_supervisor', 'Crew', 'Runner'}
LC_STRUCT = {'PydanticOutputParser', 'JsonOutputParser', 'StructuredOutputParser', 'ResponseSchema', 'with_structured_output', 'JsonOutputFunctionsParser',
             'PydanticToolsParser'}
LC_PROMPT = {'PromptTemplate', 'ChatPromptTemplate', 'SystemMessagePromptTemplate', 'HumanMessagePromptTemplate', 'FewShotPromptTemplate',
             'FewShotChatMessagePromptTemplate', 'MessagesPlaceholder', 'from_template', 'from_messages'}
LC_CHAIN = {'LLMChain', 'SequentialChain', 'SimpleSequentialChain', 'RunnableSequence', 'TransformChain', 'StuffDocumentsChain', 'create_stuff_documents_chain',
            'load_qa_chain', 'load_summarize_chain', 'MapReduceDocumentsChain'}
VEC_SEARCH = re.compile(r'(^chromadb\..*\.query$|\.similarity_search(?:_with_score|_with_relevance_scores|_by_vector)?$|\.max_marginal_relevance_search$|'
                        r'\.as_retriever$|^faiss\..*\.search$|^pinecone\..*\.query$|^qdrant_client\..*\.(?:search|query_points|query)$|'
                        r'^sentence_transformers\.util\.(?:semantic_search|cos_sim)$|^sklearn\.metrics\.pairwise\.cosine_similarity$|'
                        r'(?:^|\.)(?:Chroma|FAISS|Pinecone|Qdrant|PGVector|Milvus|Weaviate|LanceDB|ElasticsearchStore|PineconeVectorStore|QdrantVectorStore)'
                        r'\.(?:from_documents|from_texts|from_existing_index)$|^llama_index\..*VectorStoreIndex.*$|\.l2_distance$|\.cosine_distance$|\.max_inner_product$)')
VEC_SQL = re.compile(r"<->|<=>|<#>|\bvector_cosine_ops\b|\bmatch_documents\b|\bcosine_distance\b")

# ---------------------------------------------------------------- JS/TS·Java/Kotlin·Dart 줄 규칙
JS_IMPORT = re.compile(r'''(?:from\s+|require\(\s*|import\(\s*|import\s+)['"]((?:@[\w.-]+/)?[\w.-]+)(?:/[\w./-]*)?['"]''')
JS_PKG = {'openai': 'OpenAI', '@anthropic-ai/sdk': 'Anthropic', '@google/generative-ai': 'Gemini', '@google/genai': 'Gemini', 'ai': 'Vercel AI SDK',
          'ollama': 'Ollama', '@huggingface/inference': 'Hugging Face API', '@xenova/transformers': 'Hugging Face(로컬)',
          '@huggingface/transformers': 'Hugging Face(로컬)', 'groq-sdk': 'Groq', '@mistralai/mistralai': 'Mistral', 'cohere-ai': 'Cohere',
          'replicate': 'Replicate', '@langchain/openai': 'OpenAI', '@langchain/anthropic': 'Anthropic', '@langchain/google-genai': 'Gemini',
          '@langchain/ollama': 'Ollama', '@langchain/community': 'LangChain', 'langchain': 'LangChain', '@langchain/core': 'LangChain',
          '@tensorflow/tfjs': 'TensorFlow.js(로컬)', '@tensorflow/tfjs-node': 'TensorFlow.js(로컬)', '@mediapipe/tasks-vision': 'MediaPipe(로컬)',
          '@mediapipe/hands': 'MediaPipe(로컬)', '@mediapipe/face_mesh': 'MediaPipe(로컬)', '@mediapipe/pose': 'MediaPipe(로컬)',
          'onnxruntime-web': 'ONNX(로컬)', 'onnxruntime-node': 'ONNX(로컬)', '@modelcontextprotocol/sdk': 'MCP', '@ai-sdk/openai': 'OpenAI',
          '@ai-sdk/anthropic': 'Anthropic', '@ai-sdk/google': 'Gemini', '@ai-sdk/groq': 'Groq', '@ai-sdk/mistral': 'Mistral',
          '@ai-sdk/react': 'Vercel AI SDK', '@pinecone-database/pinecone': 'Pinecone', 'chromadb': 'Chroma', '@qdrant/js-client-rest': 'Qdrant',
          'face-api.js': 'face-api(로컬)', '@vladmandic/face-api': 'face-api(로컬)', 'tesseract.js': 'Tesseract(로컬)'}
JS_PKG_PREFIX = [('@tensorflow-models/', 'TensorFlow.js(로컬)'), ('@ai-sdk/', 'Vercel AI SDK'), ('@langchain/', 'LangChain'), ('@mediapipe/', 'MediaPipe(로컬)')]
LOCAL_PROV = re.compile(r'로컬')
# (패턴, 필요한 제공자 집합 또는 None, 고정 제공자 또는 None, 종류)
JS_CALLS = [
    (r'\.chat\.completions\.(?:create|parse|stream)\s*\(', {'OpenAI', 'Groq', 'Hugging Face API'}, None, 'chat'),
    (r'\.responses\.(?:create|parse|stream)\s*\(', {'OpenAI'}, 'OpenAI', 'chat'),
    (r'\.embeddings\.create\s*\(', {'OpenAI', 'Mistral'}, None, 'embedding'),
    (r'\.audio\.(?:transcriptions|translations)\.create\s*\(', {'OpenAI', 'Groq'}, None, 'speech-to-text'),
    (r'\.audio\.speech\.create\s*\(', {'OpenAI'}, 'OpenAI', 'text-to-speech'),
    (r'\.images\.(?:generate|edit)\s*\(', {'OpenAI'}, 'OpenAI', 'image-generation'),
    (r'\.moderations\.create\s*\(', {'OpenAI'}, 'OpenAI', 'moderation'),
    (r'\.(?:createChatCompletion|createCompletion)\s*\(', {'OpenAI'}, 'OpenAI', 'chat'),
    (r'\.createEmbedding\s*\(', {'OpenAI'}, 'OpenAI', 'embedding'),
    (r'\.createImage\s*\(', {'OpenAI'}, 'OpenAI', 'image-generation'),
    (r'\.createTranscription\s*\(', {'OpenAI'}, 'OpenAI', 'speech-to-text'),
    (r'\.beta\.threads\.', {'OpenAI'}, 'OpenAI', 'chat'),
    (r'\.messages\.(?:create|stream|countTokens)\s*\(', {'Anthropic'}, 'Anthropic', 'chat'),
    (r'\.(?:generateContent|generateContentStream|sendMessage|sendMessageStream)\s*\(', {'Gemini'}, 'Gemini', 'chat'),
    (r'\.(?:embedContent|batchEmbedContents)\s*\(', {'Gemini'}, 'Gemini', 'embedding'),
    (r'\.models\.generateImages\s*\(', {'Gemini'}, 'Gemini', 'image-generation'),
    (r'\.live\.connect\s*\(', {'Gemini'}, 'Gemini', 'realtime'),
    (r'\b(?:generateText|streamText|generateObject|streamObject)\s*\(', {'Vercel AI SDK'}, None, 'chat'),
    (r'\b(?:embed|embedMany)\s*\(\s*\{', {'Vercel AI SDK'}, None, 'embedding'),
    (r'\bollama\.(?:chat|generate)\s*\(', {'Ollama'}, 'Ollama', 'chat'),
    (r'\bollama\.(?:embeddings|embed)\s*\(', {'Ollama'}, 'Ollama', 'embedding'),
    (r'\.(?:textGeneration|chatCompletion|chatCompletionStream|textGenerationStream)\s*\(', {'Hugging Face API'}, 'Hugging Face API', 'chat'),
    (r'\.featureExtraction\s*\(', {'Hugging Face API'}, 'Hugging Face API', 'embedding'),
    (r'\.(?:imageClassification|objectDetection|imageToText|textToImage)\s*\(', {'Hugging Face API'}, 'Hugging Face API', 'vision'),
    (r'\.(?:automaticSpeechRecognition|textToSpeech)\s*\(', {'Hugging Face API'}, 'Hugging Face API', 'speech'),
    (r'\.chat\.(?:complete|stream)\s*\(', {'Mistral'}, 'Mistral', 'chat'),
    (r'\bcohere\.(?:chat|generate|chatStream)\s*\(', {'Cohere'}, 'Cohere', 'chat'),
    (r'\breplicate\.run\s*\(', {'Replicate'}, 'Replicate', 'model-run'),
    (r'\btf\.(?:loadLayersModel|loadGraphModel)\s*\(', {'TensorFlow.js(로컬)'}, 'TensorFlow.js(로컬)', 'model-inference'),
    (r'\bInferenceSession\.create\s*\(', {'ONNX(로컬)'}, 'ONNX(로컬)', 'model-inference'),
    (r'\b(?:HandLandmarker|PoseLandmarker|FaceLandmarker|GestureRecognizer|ObjectDetector|ImageClassifier|FaceDetector|ImageSegmenter)\.createFrom\w+\s*\(|new\s+(?:Hands|FaceMesh|Pose|Holistic|SelfieSegmentation)\s*\(',
     {'MediaPipe(로컬)'}, 'MediaPipe(로컬)', 'vision'),
    (r'\bfaceapi\.(?:detectAllFaces|detectSingleFace)\s*\(', {'face-api(로컬)'}, 'face-api(로컬)', 'vision'),
    (r'\bTesseract\.recognize\s*\(|\bcreateWorker\s*\(', {'Tesseract(로컬)'}, 'Tesseract(로컬)', 'vision'),
]
JS_CALLS = [(re.compile(a), b, c, d) for a, b, c, d in JS_CALLS]
JS_LC_CTOR = re.compile(r'\bnew\s+(' + '|'.join(sorted(LC_CTOR, key=len, reverse=True)) + r')\s*\(')
JS_PIPELINE = re.compile(r'''\bpipeline\s*\(\s*['"]([\w-]+)['"]''')
JS_HTTP = re.compile(r'\bfetch\s*\(|\baxios\b|\$\.(?:ajax|post|get)\b|XMLHttpRequest|\bgot\s*\(|\bky\s*\(|\bhttps?\.request\s*\(|\buseFetch\s*\(|\$fetch\s*\(')

JVM_IMPORT = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)')
JVM_PKG = [('com.anthropic.', 'Anthropic'), ('com.openai.', 'OpenAI'), ('com.theokanning.openai', 'OpenAI'), ('io.github.sashirestela.openai', 'OpenAI'),
           ('com.azure.ai.openai', 'Azure OpenAI'), ('org.springframework.ai.', 'Spring AI'), ('dev.langchain4j.', 'LangChain4j'),
           ('com.google.cloud.vertexai', 'Vertex AI'), ('com.google.ai.client.generativeai', 'Gemini'), ('com.google.genai', 'Gemini'),
           ('com.google.firebase.vertexai', 'Gemini'), ('com.google.firebase.ai', 'Gemini'), ('com.google.mlkit.', 'ML Kit(로컬)'),
           ('org.tensorflow.lite', 'TensorFlow Lite(로컬)'), ('ai.onnxruntime', 'ONNX(로컬)'), ('com.google.cloud.vision', 'Google Cloud Vision'),
           ('com.google.cloud.speech', 'Google Cloud Speech'), ('com.google.cloud.texttospeech', 'Google Cloud TTS'),
           ('com.google.mediapipe', 'MediaPipe(로컬)')]
JVM_CALLS = [
    (r'\.messages\(\)\s*\.\s*(?:create|createStreaming|countTokens)\s*\(', {'Anthropic'}, 'Anthropic', 'chat'),
    (r'\.chat\(\)\s*\.\s*completions\(\)\s*\.\s*(?:create|createStreaming)\s*\(', {'OpenAI', 'Azure OpenAI'}, None, 'chat'),
    (r'\.responses\(\)\s*\.\s*create\s*\(', {'OpenAI'}, 'OpenAI', 'chat'),
    (r'\.embeddings\(\)\s*\.\s*create\s*\(', {'OpenAI'}, 'OpenAI', 'embedding'),
    (r'\.(?:createChatCompletion|createCompletion|streamChatCompletion|getChatCompletions)\s*\(', {'OpenAI', 'Azure OpenAI'}, None, 'chat'),
    (r'\.(?:createEmbeddings|getEmbeddings)\s*\(', {'OpenAI', 'Azure OpenAI'}, None, 'embedding'),
    (r'\.createImage\s*\(', {'OpenAI'}, 'OpenAI', 'image-generation'),
    (r'\.createTranscription\s*\(', {'OpenAI'}, 'OpenAI', 'speech-to-text'),
    (r'\b(?:chatModel|chatClient|model|llm|ollamaChatModel|openAiChatModel)\s*\.\s*(?:call|stream)\s*\(', {'Spring AI'}, 'Spring AI', 'chat'),
    (r'\bembeddingModel\s*\.\s*(?:embed|call)\s*\(', {'Spring AI', 'LangChain4j'}, None, 'embedding'),
    (r'\.prompt\s*\(', {'Spring AI'}, 'Spring AI', 'chat'),
    (r'\b(?:OpenAiChatModel|AnthropicChatModel|GoogleAiGeminiChatModel|OllamaChatModel|VertexAiGeminiChatModel|AzureOpenAiChatModel|OpenAiStreamingChatModel)\s*\.\s*builder\s*\(',
     {'LangChain4j'}, 'LangChain4j', 'chat'),
    (r'\bAiServices\s*\.\s*(?:create|builder)\s*\(', {'LangChain4j'}, 'LangChain4j', 'chat'),
    (r'\.generateContent\s*\(|\.sendMessage\s*\(|\.generateContentStream\s*\(', {'Gemini', 'Vertex AI'}, None, 'chat'),
    (r'\b(?:TextRecognition|FaceDetection|ImageLabeling|BarcodeScanning|ObjectDetection|PoseDetection|SubjectSegmentation|SelfieSegmentation|FaceMeshDetection)\s*\.\s*getClient\s*\(',
     {'ML Kit(로컬)'}, 'ML Kit(로컬)', 'vision'),
    (r'\b(?:Translation|LanguageIdentification|EntityExtraction|SmartReply)\s*\.\s*getClient\s*\(', {'ML Kit(로컬)'}, 'ML Kit(로컬)', 'nlp'),
    (r'\bInterpreter\s*\(|\bnew\s+Interpreter\s*\(', {'TensorFlow Lite(로컬)'}, 'TensorFlow Lite(로컬)', 'model-inference'),
    (r'\bOrtEnvironment\s*\.\s*getEnvironment\s*\(', {'ONNX(로컬)'}, 'ONNX(로컬)', 'model-inference'),
    (r'\bImageAnnotatorClient\s*\.\s*create\s*\(', {'Google Cloud Vision'}, 'Google Cloud Vision', 'vision'),
    (r'\bSpeechClient\s*\.\s*create\s*\(', {'Google Cloud Speech'}, 'Google Cloud Speech', 'speech-to-text'),
    (r'\bTextToSpeechClient\s*\.\s*create\s*\(', {'Google Cloud TTS'}, 'Google Cloud TTS', 'text-to-speech'),
]
JVM_CALLS = [(re.compile(a), b, c, d) for a, b, c, d in JVM_CALLS]
JVM_HTTP = re.compile(r'RestTemplate|WebClient|RestClient|OkHttpClient|HttpClient|HttpURLConnection|Retrofit|Feign|\.uri\(|\.url\(')

DART_PKG = [('package:google_generative_ai/', 'Gemini'), ('package:firebase_vertexai/', 'Gemini'), ('package:firebase_ai/', 'Gemini'),
            ('package:dart_openai/', 'OpenAI'), ('package:chat_gpt_sdk/', 'OpenAI'), ('package:tflite_flutter/', 'TensorFlow Lite(로컬)'),
            ('package:google_mlkit_', 'ML Kit(로컬)'), ('package:langchain', 'LangChain')]
DART_CALLS = [
    (r'\.generateContent\s*\(|\.sendMessage\s*\(|\.generateContentStream\s*\(', {'Gemini'}, 'Gemini', 'chat'),
    (r'OpenAI\.instance\.(?:chat|completion)\.create', {'OpenAI'}, 'OpenAI', 'chat'),
    (r'OpenAI\.instance\.embedding\.create', {'OpenAI'}, 'OpenAI', 'embedding'),
    (r'\.onChatCompletion\s*\(|\.onCompletion\s*\(', {'OpenAI'}, 'OpenAI', 'chat'),
    (r'\bInterpreter\.from(?:Asset|File|Buffer)\s*\(', {'TensorFlow Lite(로컬)'}, 'TensorFlow Lite(로컬)', 'model-inference'),
    (r'\.processImage\s*\(', {'ML Kit(로컬)'}, 'ML Kit(로컬)', 'vision'),
]
DART_CALLS = [(re.compile(a), b, c, d) for a, b, c, d in DART_CALLS]

# ---------------------------------------------------------------- 흔적(점수에 안 넣음, S5 대상 고르기만)
DEP_FILE = re.compile(r'(^|/)(requirements[^/]*\.(txt|in)|pyproject\.toml|setup\.py|setup\.cfg|Pipfile|environment[^/]*\.ya?ml|package\.json|'
                      r'pom\.xml|build\.gradle(\.kts)?|pubspec\.yaml|go\.mod|Cargo\.toml|Gemfile|composer\.json|[^/]+\.csproj)$')
DEP_AI = re.compile(r'''(?ix)(?<![\w-])(openai|anthropic|google-generativeai|google-genai|langchain[\w-]*|llama-index[\w-]*|llama_index|ollama|transformers|
    sentence-transformers|huggingface[-_]hub|cohere|mistralai|groq|together|replicate|openai-whisper|faster-whisper|ultralytics|mediapipe|easyocr|deepface|
    chromadb|faiss-(?:cpu|gpu)|pinecone(?:-client)?|qdrant-client|pgvector|@anthropic-ai/sdk|@google/generative-ai|@google/genai|@ai-sdk/[\w-]+|
    @langchain/[\w-]+|@huggingface/[\w-]+|@xenova/transformers|@tensorflow/tfjs[\w-]*|@mediapipe/[\w-]+|onnxruntime[\w-]*|@modelcontextprotocol/sdk|mcp|fastmcp|
    groq-sdk|com\.anthropic|com\.openai|com\.theokanning|org\.springframework\.ai|spring-ai-[\w-]+|dev\.langchain4j|langchain4j[\w-]*|google-cloud-vertexai|
    generativeai|com\.google\.mlkit|tensorflow-lite|google_generative_ai|dart_openai|firebase_vertexai|firebase_ai|tflite_flutter|google_mlkit_\w+|go-openai|
    openai-go|anthropic-sdk-go|generative-ai-go|langchaingo|async-openai|ruby-openai|openai-php)(?![\w-])''')
DEP_ML = re.compile(r'''(?ix)(?<![\w-])(torch|torchvision|tensorflow|tensorflow-cpu|keras|scikit-learn|sklearn|xgboost|lightgbm|catboost|statsmodels|prophet|
    optuna|pytorch-lightning|lightning|timm|peft|trl|datasets|accelerate|mlflow|wandb|dvc)(?![\w-])''')
KW_AI = re.compile(r'(?i)\b(openai|anthropic|gemini|genai|langchain|llama_?index|ollama|huggingface|transformers|sentence_transformers|whisper|'
                   r'chat\.completions|embeddings?|gpt-[34o]|claude-|vertexai|bedrock|cohere|mistral|groq|upstage|clova|hyperclova|llm|'
                   r'tensorflow|tflite|keras|torch|sklearn|xgboost|lightgbm|catboost|ultralytics|yolo|mediapipe|onnx|mlkit|chromadb|faiss|pinecone|'
                   r'qdrant|pgvector|fastmcp|modelcontextprotocol)\b')
KW_ML = re.compile(r'(?i)\b(tensorflow|tflite|keras|torch|sklearn|xgboost|lightgbm|catboost|ultralytics|yolo|onnx|statsmodels|prophet|optuna|mlflow)\b')

# ---------------------------------------------------------------- AI 도구 흔적
AI_CFG = re.compile(r'(?i)(^|/)(CLAUDE(?:\.local)?\.md|AGENTS\.md|AGENT\.md|GEMINI\.md|\.cursorrules|\.cursor/.+|\.claude/.+|\.github/copilot-instructions\.md|'
                    r'\.github/instructions/[^/]+\.instructions\.md|\.github/prompts/[^/]+\.prompt\.md|\.github/chatmodes/.+|\.windsurfrules|\.windsurf/.+|'
                    r'\.clinerules(?:/.+)?|\.aider[^/]*|CONVENTIONS\.md|\.continue/.+|\.codex/.+|\.junie/.+|\.kiro/.+|\.roo/.+|\.roomodes|\.mcp\.json|'
                    r'\.vscode/mcp\.json|\.gemini/.+|\.amazonq/.+|\.augment/.+|\.qodo/.+|\.tabnine/.+|copilot-setup-steps\.ya?ml)$')
AI_CFG_STRONG_NAMES = re.compile(r'(?i)(^|/)(CLAUDE(?:\.local)?\.md|AGENTS\.md|GEMINI\.md|\.cursorrules|\.cursor/|\.claude/|copilot-instructions\.md|'
                                 r'\.windsurfrules|\.clinerules|\.aider|\.codex/|\.junie/|\.kiro/|\.roo/|\.mcp\.json|\.gemini/)')
GEN_FINGERPRINT = re.compile(r'nextjs-agent-rules|This is NOT the Next\.js you know|node_modules/next/dist/docs', re.I)
TRAILER_AI = re.compile(r'(?im)^\s*Co-authored-by:[^\n]*(claude|anthropic|copilot|cursor|codex|openai|chatgpt|gemini|devin|aider|codeium|windsurf|jules|amazon q|junie)')
GEN_MARK = re.compile(r'(?i)generated with \[?claude code|🤖 generated with|generated (?:by|with) (?:github )?copilot|copilot (?:generated|coding agent)|'
                      r'created (?:by|with) (?:cursor|codex|devin|jules|claude)|(?:by|with) openai codex|devin-ai-integration|'
                      r'this (?:pr|pull request) was (?:written|generated|created|opened) (?:by|with|using) (?:an? )?(?:ai|claude|copilot|codex|cursor|devin|gemini)')
WEAK_AI_TOOL = re.compile(r'(?i)\b(claude(?: code)?|copilot|cursor(?: ai)?|chatgpt|gpt-?[345o]|codex|gemini|windsurf|devin|aider|ai(?:로| 도움| 생성| 작성)|'
                          r'llm(?:으로|이))\b')
AI_BOT_USER = re.compile(r'(?i)^(copilot|copilot-swe-agent(\[bot\])?|devin-ai-integration\[bot\]|claude(\[bot\])?|codex(\[bot\])?|cursor(\[bot\])?|'
                         r'google-labs-jules\[bot\]|openai-codex\[bot\]|gemini-code-assist\[bot\])$')
AI_AUTHOR = re.compile(r'(?i)(claude|anthropic|copilot|cursor|codex|devin|jules|gemini|aider)')

# 받는 쪽 이름을 못 푼 호출(매개변수로 받은 client 등): 끝 모양 + 그 파일이 그 SDK를 import했을 때만(「제안」)
PY_SUFFIX = [(r'(?:^|\.)chat\.completions\.(?:create|parse|stream)$', 'openai', 'OpenAI', 'chat'),
             (r'(?:^|\.)chat\.completions\.create$', 'groq', 'Groq', 'chat'),
             (r'(?:^|\.)responses\.(?:create|parse|stream)$', 'openai', 'OpenAI', 'chat'),
             (r'(?:^|\.)embeddings\.create$', 'openai', 'OpenAI', 'embedding'),
             (r'(?:^|\.)audio\.(?:transcriptions|translations)\.create$', 'openai', 'OpenAI', 'speech-to-text'),
             (r'(?:^|\.)images\.(?:generate|edit)$', 'openai', 'OpenAI', 'image-generation'),
             (r'(?:^|\.)messages\.(?:create|stream)$', 'anthropic', 'Anthropic', 'chat'),
             (r'(?:^|\.)models\.(?:generate_content|generate_content_stream)$', 'google.genai', 'Gemini', 'chat'),
             (r'(?:^|\.)models\.embed_content$', 'google.genai', 'Gemini', 'embedding'),
             (r'(?:^|\.)(?:generate_content|generate_content_async|send_message)$', 'google.generativeai', 'Gemini', 'chat'),
             (r'(?:^|\.)transcribe$', 'faster_whisper', 'Whisper(로컬)', 'speech-to-text'),
             (r'(?:^|\.)transcribe$', 'whisper', 'Whisper(로컬)', 'speech-to-text'),
             (r'(?:^|\.)encode$', 'sentence_transformers', 'Hugging Face(로컬)', 'embedding'),
             (r'(?:^|\.)(?:chat|generate)$', 'ollama', 'Ollama', 'chat')]
PY_SUFFIX = [(re.compile(a), b, c, d) for a, b, c, d in PY_SUFFIX]
