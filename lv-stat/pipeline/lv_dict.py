"""도구·기능 사전: 라이브러리(import 경로·패키지 이름) -> (도구 이름, 기능).
도구 이름이 None이면 "알고 있지만 역량 대상은 아님"(유틸·타입 등). 기능은 활동 판정에 씀:
test, cache, queue, oauth, payment, monitoring, http, auth, orm, scheduler, websocket, ai, cloud
"""
JAVA = [  # prefix, tool, capability  (가장 긴 prefix가 이김)
 ('org.springframework.security.oauth2.client', 'Spring Security', 'oauth'), ('org.springframework.security.oauth2.core.user', 'Spring Security', 'oauth'),
 ('org.springframework.security', 'Spring Security', 'auth'),
 ('org.springframework.data.jpa', 'JPA', 'orm'), ('jakarta.persistence', 'JPA', 'orm'), ('javax.persistence', 'JPA', 'orm'),
 ('org.hibernate.validator', 'Bean Validation', None), ('org.hibernate', 'JPA', 'orm'), ('com.querydsl', 'QueryDSL', 'orm'),
 ('org.mybatis', 'MyBatis', 'orm'), ('org.apache.ibatis', 'MyBatis', 'orm'),
 ('org.springframework.data.redis', 'Redis', None), ('redis.clients', 'Redis', None), ('io.lettuce', 'Redis', None), ('org.redisson', 'Redis', None),
 ('org.springframework.data.mongodb', 'MongoDB', None), ('com.mongodb', 'MongoDB', None), ('org.bson', 'MongoDB', None),
 ('org.springframework.data.elasticsearch', 'Elasticsearch', None), ('co.elastic', 'Elasticsearch', None), ('org.elasticsearch', 'Elasticsearch', None),
 ('org.springframework.kafka', 'Kafka', 'queue'), ('org.apache.kafka', 'Kafka', 'queue'),
 ('org.springframework.amqp', 'RabbitMQ', 'queue'), ('com.rabbitmq', 'RabbitMQ', 'queue'),
 ('org.springframework.cache', 'Spring', 'cache'), ('com.github.benmanes.caffeine', 'Caffeine', 'cache'), ('net.sf.ehcache', 'Ehcache', 'cache'), ('org.ehcache', 'Ehcache', 'cache'),
 ('org.springframework.scheduling', 'Spring', 'scheduler'), ('org.quartz', 'Quartz', 'scheduler'),
 ('org.springframework.web.socket', 'WebSocket', 'websocket'), ('org.springframework.messaging.simp', 'WebSocket', 'websocket'), ('org.springframework.messaging', None, None), ('jakarta.websocket', 'WebSocket', 'websocket'),
 ('org.springframework.batch', 'Spring Batch', None), ('org.springframework.cloud.gateway', 'Spring Cloud Gateway', None), ('org.springframework.cloud.netflix', 'Eureka', None), ('org.springframework.cloud', 'Spring Cloud', None), ('org.springframework.ai', 'Spring AI', 'ai'),
 ('org.springframework.web.client', 'Spring', 'http'), ('org.springframework.web.reactive.function.client', 'Spring', 'http'),
 ('org.springframework.cloud.openfeign', 'OpenFeign', 'http'), ('feign', 'OpenFeign', 'http'), ('okhttp3', 'OkHttp', 'http'), ('org.apache.http', 'HttpClient', 'http'), ('org.apache.hc', 'HttpClient', 'http'), ('retrofit2', 'Retrofit', 'http'),
 ('org.springframework.boot.test', 'Spring', 'test'), ('org.springframework.test', 'Spring', 'test'), ('org.springframework.security.test', 'Spring Security', 'test'),
 ('org.junit', 'JUnit', 'test'), ('org.mockito', 'Mockito', 'test'), ('org.assertj', 'AssertJ', 'test'), ('org.hamcrest', 'Hamcrest', 'test'), ('org.testcontainers', 'Testcontainers', 'test'), ('io.restassured', 'REST Assured', 'test'), ('com.jayway.jsonpath', None, None),
 ('org.springframework.jdbc', 'Spring JDBC', None), ('org.springframework.mail', 'Spring Mail', None), ('org.springframework.retry', 'Spring Retry', None),
 ('org.springframework.data', 'Spring Data', None), ('org.springframework', 'Spring', None),
 ('lombok', 'Lombok', None), ('jakarta.validation', 'Bean Validation', None), ('javax.validation', 'Bean Validation', None),
 ('com.fasterxml.jackson', 'Jackson', None), ('tools.jackson', 'Jackson', None), ('com.google.gson', 'Gson', None),
 ('io.jsonwebtoken', 'JWT', 'auth'), ('com.auth0.jwt', 'JWT', 'auth'), ('com.nimbusds', 'JWT', 'auth'),
 ('io.swagger', 'Swagger/OpenAPI', None), ('org.springdoc', 'Swagger/OpenAPI', None),
 ('org.slf4j', None, None), ('ch.qos.logback', None, None), ('org.apache.logging', None, None), ('org.apache.commons', None, None), ('com.google.common', None, None),
 ('org.jspecify', None, None), ('jakarta.annotation', None, None), ('javax.annotation', None, None), ('org.jetbrains.annotations', None, None), ('org.aspectj', 'Spring AOP', None),
 ('org.flywaydb', 'Flyway', None), ('liquibase', 'Liquibase', None), ('com.zaxxer.hikari', None, None),
 ('software.amazon.awssdk', 'AWS SDK', 'cloud'), ('com.amazonaws', 'AWS SDK', 'cloud'), ('com.google.cloud', 'Google Cloud SDK', 'cloud'), ('com.google.firebase', 'Firebase', 'cloud'), ('com.azure', 'Azure SDK', 'cloud'),
 ('io.micrometer', 'Micrometer', 'monitoring'), ('io.prometheus', 'Prometheus', 'monitoring'), ('io.sentry', 'Sentry', 'monitoring'), ('io.opentelemetry', 'OpenTelemetry', 'monitoring'),
 ('jakarta.servlet', 'Servlet', None), ('javax.servlet', 'Servlet', None), ('jakarta.mail', 'JavaMail', None), ('javax.mail', 'JavaMail', None),
 ('org.apache.poi', 'Apache POI', None), ('org.apache.pdfbox', 'PDFBox', None), ('org.apache.tika', 'Apache Tika', None), ('org.jsoup', 'Jsoup', None),
 ('reactor', 'Reactor', None), ('io.netty', 'Netty', None), ('io.grpc', 'gRPC', None), ('org.mapstruct', 'MapStruct', None),
 ('io.github.resilience4j', 'Resilience4j', None), ('dev.langchain4j', 'LangChain4j', 'ai'), ('com.theokanning.openai', 'OpenAI API', 'ai'), ('com.openai', 'OpenAI API', 'ai'),
 ('com.siot.IamportRestClient', 'Iamport', 'payment'), ('com.stripe', 'Stripe', 'payment'),
 ('kotlinx.coroutines', 'Kotlin Coroutines', None), ('kotlinx.serialization', None, None), ('kotlin', None, None), ('io.kotest', 'Kotest', 'test'), ('io.mockk', 'MockK', 'test'),
 ('software.amazon.awssdk.services.sqs', 'AWS SQS', 'queue'), ('com.amazonaws.services.sqs', 'AWS SQS', 'queue'), ('io.awspring.cloud.sqs', 'AWS SQS', 'queue'),
 ('org.springframework.security.oauth2.jwt', 'JWT', 'auth'), ('org.awaitility', None, 'test'), ('org.yaml', None, None), ('jakarta.transaction', None, None), ('org.w3c', None, None), ('org.xml', None, None),
 ('com.github.dockerjava', None, None), ('org.locationtech', None, None),
 ('org.springframework.graphql', 'GraphQL', None), ('com.netflix.graphql', 'GraphQL', None), ('graphql', 'GraphQL', None), ('org.postgresql', None, None), ('com.rometools', None, None), ('ai.djl', 'DJL', 'ai'), ('ai.onnxruntime', 'ONNX Runtime', 'ai'),
 ('com.apple.itunes', None, None), ('com.google.auth', None, None), ('org.apache.catalina', None, None), ('org.apache.coyote', None, None), ('com.github.tomakehurst', 'WireMock', 'test'), ('org.wiremock', 'WireMock', 'test'),
 ('com.tngtech.archunit', 'ArchUnit', 'test'), ('org.aopalliance', None, None), ('app.photofox', None, None), ('org.neo4j', 'Neo4j', None),
 ('org.apache.flink', 'Flink', None), ('com.google.protobuf', None, None), ('kr.dogfoot', None, None),
 ('com.mercadopago', 'Mercado Pago', 'payment'), ('com.paypal', 'PayPal', 'payment'), ('com.razorpay', 'Razorpay', 'payment'), ('com.braintreegateway', 'Braintree', 'payment'), ('com.adyen', 'Adyen', 'payment'),
 ('com.squareup.square', 'Square', 'payment'), ('kr.co.bootpay', 'Bootpay', 'payment'), ('com.google.api.client.googleapis.auth', 'Google API', 'oauth'), ('com.nimbusds.oauth2', None, 'oauth'), ('org.keycloak', 'Keycloak', 'oauth'),
 ('org.springframework.security.oauth2.server.authorization', 'Spring Security', 'oauth'), ('org.springframework.security.oauth2.server', 'Spring Security', 'auth'), ('org.springframework.data.redis.cache', 'Redis', 'cache'), ('com.hazelcast', 'Hazelcast', 'cache'),
 ('org.apache.pulsar', 'Pulsar', 'queue'), ('org.springframework.cloud.stream', 'Spring Cloud Stream', 'queue'), ('org.springframework.jms', 'JMS', 'queue'), ('org.apache.activemq', 'ActiveMQ', 'queue'), ('org.apache.rocketmq', 'RocketMQ', 'queue'),
 ('com.google.cloud.pubsub', 'Google Pub/Sub', 'queue'), ('com.datadoghq', 'Datadog', 'monitoring'), ('datadog', 'Datadog', 'monitoring'), ('com.newrelic', 'New Relic', 'monitoring'), ('io.zipkin', 'Zipkin', 'monitoring'), ('brave', 'Zipkin', 'monitoring'),
 ('java.net.http', None, 'http'), ('com.squareup.okhttp', 'OkHttp', 'http'), ('io.github.openfeign', 'OpenFeign', 'http'), ('kong.unirest', None, 'http'), ('org.asynchttpclient', None, 'http'),
 ('com.cloudinary', 'Cloudinary', 'cloud'), ('io.minio', 'MinIO', 'cloud'), ('io.github.bucket4j', 'Bucket4j', None), ('net.ttddyy', None, None), ('org.apache.tomcat', None, None),
 ('org.jooq', 'jOOQ', 'orm'), ('com.linecorp.kotlinjdsl', 'Kotlin JDSL', 'orm'), ('com.oracle.bmc', 'OCI SDK', 'cloud'), ('io.github.oshai', None, None), ('com.pgvector', 'pgvector', None), ('net.logstash', None, None),
 ('com.google.genai', 'Gemini API', 'ai'), ('io.zonky', None, 'test'), ('com.google.zxing', None, None),
 ('com.pulumi', 'Pulumi', 'iac'), ('software.amazon.awscdk', 'AWS CDK', 'iac'), ('com.microsoft.sqlserver', 'SQL Server', None), ('net.sourceforge.plantuml', None, None), ('cn.hutool', None, None), ('com.uber.h3core', None, None),
 ('org.modelmapper', None, None),
 ('io.gatling', 'Gatling', 'loadtest'), ('net.grinder', 'nGrinder', 'loadtest'),
 ('vn.payos', 'PayOS', 'payment'), ('com.solapi', 'SOLAPI', None), ('org.skyscreamer', None, 'test'), ('com.sun', None, None), ('javax.tools', None, None), ('javax.lang', None, None),
 ('net.sourceforge.tess4j', 'Tesseract OCR', None), ('com.opencsv', None, None), ('com.fasterxml.uuid', None, None),
 ('io.ktor', 'Ktor', None), ('org.jetbrains.exposed', 'Exposed', 'orm'), ('org.thymeleaf', 'Thymeleaf', None), ('com.h2database', None, None), ('org.h2', None, None),
]
JAVA.sort(key=lambda x: -len(x[0]))

PY = {  # import 최상위 모듈
 'fastapi': ('FastAPI', None), 'starlette': ('FastAPI', None), 'django': ('Django', None), 'rest_framework': ('Django REST framework', None), 'flask': ('Flask', None),
 'sqlalchemy': ('SQLAlchemy', 'orm'), 'sqlmodel': ('SQLModel', 'orm'), 'alembic': ('Alembic', None), 'tortoise': ('Tortoise ORM', 'orm'), 'peewee': ('Peewee', 'orm'),
 'psycopg2': ('PostgreSQL', None), 'psycopg': ('PostgreSQL', None), 'asyncpg': ('PostgreSQL', None), 'pymysql': ('MySQL', None), 'aiomysql': ('MySQL', None), 'MySQLdb': ('MySQL', None),
 'pymongo': ('MongoDB', None), 'motor': ('MongoDB', None), 'beanie': ('MongoDB', None), 'mongoengine': ('MongoDB', None),
 'redis': ('Redis', None), 'aioredis': ('Redis', None), 'elasticsearch': ('Elasticsearch', None), 'opensearchpy': ('OpenSearch', None),
 'pydantic': ('Pydantic', None), 'pydantic_settings': ('Pydantic', None), 'pydantic_core': ('Pydantic', None),
 'pytest': ('pytest', 'test'), 'pytest_asyncio': ('pytest', 'test'), 'hypothesis': ('Hypothesis', 'test'), 'respx': ('pytest', 'test'), 'freezegun': (None, 'test'),
 'requests': ('requests', 'http'), 'httpx': ('httpx', 'http'), 'aiohttp': ('aiohttp', 'http'), 'urllib3': (None, None),
 'celery': ('Celery', 'queue'), 'nats': ('NATS', 'queue'), 'kafka': ('Kafka', 'queue'), 'aiokafka': ('Kafka', 'queue'), 'confluent_kafka': ('Kafka', 'queue'),
 'pika': ('RabbitMQ', 'queue'), 'aio_pika': ('RabbitMQ', 'queue'), 'rq': ('RQ', 'queue'), 'dramatiq': ('Dramatiq', 'queue'),
 'boto3': ('AWS SDK', 'cloud'), 'botocore': ('AWS SDK', 'cloud'), 'aioboto3': ('AWS SDK', 'cloud'), 'mypy_boto3_s3': (None, None), 'firebase_admin': ('Firebase', 'cloud'), 'azure': ('Azure SDK', 'cloud'),
 'numpy': ('NumPy', None), 'pandas': ('Pandas', None), 'scipy': ('SciPy', None), 'sklearn': ('scikit-learn', 'ai'), 'torch': ('PyTorch', 'ai'), 'torchvision': ('PyTorch', 'ai'), 'torchaudio': ('PyTorch', 'ai'),
 'tensorflow': ('TensorFlow', 'ai'), 'keras': ('TensorFlow', 'ai'), 'transformers': ('Transformers', 'ai'), 'openai': ('OpenAI API', 'ai'), 'anthropic': ('Anthropic API', 'ai'),
 'langchain': ('LangChain', 'ai'), 'langchain_core': ('LangChain', 'ai'), 'langchain_openai': ('LangChain', 'ai'), 'langchain_community': ('LangChain', 'ai'), 'langgraph': ('LangGraph', 'ai'),
 'google': ('Google API', None), 'vertexai': ('Google API', 'ai'), 'cv2': ('OpenCV', None), 'PIL': ('Pillow', None), 'matplotlib': ('Matplotlib', None), 'seaborn': ('Matplotlib', None),
 'chromadb': ('벡터 DB', 'ai'), 'faiss': ('벡터 DB', 'ai'), 'qdrant_client': ('벡터 DB', 'ai'), 'pymilvus': ('벡터 DB', 'ai'), 'pinecone': ('벡터 DB', 'ai'),
 'jwt': ('JWT', 'auth'), 'jose': ('JWT', 'auth'), 'passlib': (None, 'auth'), 'bcrypt': (None, 'auth'), 'authlib': ('Authlib', 'oauth'),
 'uvicorn': (None, None), 'gunicorn': (None, None), 'dotenv': (None, None), 'yaml': (None, None), 'toml': (None, None), 'orjson': (None, None), 'ujson': (None, None),
 'typing_extensions': (None, None), 'tqdm': (None, None), 'click': (None, None), 'typer': (None, None), 'jinja2': ('Jinja2', None), 'loguru': (None, None), 'structlog': (None, None),
 'bs4': ('BeautifulSoup', None), 'selenium': ('Selenium', None), 'playwright': ('Playwright', None), 'scrapy': ('Scrapy', None), 'lxml': (None, None), 'trafilatura': ('trafilatura', None),
 'apscheduler': ('APScheduler', 'scheduler'), 'sentry_sdk': ('Sentry', 'monitoring'), 'prometheus_client': ('Prometheus', 'monitoring'), 'opentelemetry': ('OpenTelemetry', 'monitoring'),
 'cachetools': ('cachetools', 'cache'), 'aiocache': ('aiocache', 'cache'), 'fastapi_cache': ('fastapi-cache', 'cache'), 'tenacity': (None, None),
 'websockets': ('WebSocket', 'websocket'), 'socketio': ('WebSocket', 'websocket'), 'grpc': ('gRPC', None), 'stripe': ('Stripe', 'payment'), 'slowapi': (None, None), 'locust': ('Locust', 'loadtest'),
 'geopandas': ('GeoPandas', None), 'shapely': ('GeoPandas', None), 'networkx': (None, None), 'pyproj': (None, None), 'osmnx': (None, None), 'openpyxl': (None, None), 'pdfplumber': (None, None),
 'pdfminer': (None, None), 'ultralytics': ('YOLO', 'ai'), 'weasyprint': (None, None), 'webdriver_manager': ('Selenium', None),
 'joserfc': ('JWT', 'auth'), 'strawberry': ('GraphQL', None), 'graphene': ('GraphQL', None), 'ariadne': ('GraphQL', None), 'graphiti_core': (None, 'ai'), 'fastembed': (None, 'ai'), 'neo4j': ('Neo4j', None),
 'llama_index': ('LlamaIndex', 'ai'), 'reportlab': (None, None), 'pypdf': (None, None), 'fakeredis': (None, 'test'), 'httpcore': (None, None), 'psycopg_pool': ('PostgreSQL', None), 'shapefile': (None, None),
 'rest_framework_simplejwt': ('JWT', 'auth'), 'drf_spectacular': ('Swagger/OpenAPI', None), 'drf_yasg': ('Swagger/OpenAPI', None), 'groq': ('Groq', 'ai'), 'cloudinary': ('Cloudinary', 'cloud'), 'cloudinary_storage': ('Cloudinary', 'cloud'),
 'faker': (None, None), 'email_validator': (None, None), 'aiosmtplib': (None, None), 'environ': (None, None), 'docx': (None, None), 'fastapi_pagination': (None, None), 'factory': (None, 'test'), 'moto': (None, 'test'),
 'asgiref': (None, None), 'elastic_transport': ('Elasticsearch', None), 'drifting': (None, None), 'decouple': (None, None), 'dj_database_url': (None, None), 'corsheaders': (None, None), 'django_filters': (None, None), 'channels': ('WebSocket', 'websocket'),
 'paypalrestsdk': ('PayPal', 'payment'), 'razorpay': ('Razorpay', 'payment'), 'mercadopago': ('Mercado Pago', 'payment'), 'iamport': ('아임포트', 'payment'), 'braintree': ('Braintree', 'payment'), 'portone': ('포트원', 'payment'),
 'allauth.socialaccount': ('django-allauth', 'oauth'), 'allauth': ('django-allauth', 'auth'), 'social_django': (None, 'oauth'), 'social_core': (None, 'oauth'), 'google_auth_oauthlib': ('Google API', 'oauth'), 'google.oauth2': ('Google API', 'oauth'), 'requests_oauthlib': (None, 'oauth'),
 'oauthlib': (None, 'oauth'), 'fastapi_sso': (None, 'oauth'), 'httpx_oauth': (None, 'oauth'), 'google.cloud': ('Google Cloud', 'cloud'), 'google.generativeai': ('Gemini API', 'ai'), 'google.genai': ('Gemini API', 'ai'),
 'django_redis': ('Redis', 'cache'), 'flask_caching': (None, 'cache'), 'diskcache': (None, 'cache'), 'dogpile': (None, 'cache'), 'cashews': (None, 'cache'),
 'kombu': (None, 'queue'), 'django_celery_beat': ('Celery', 'scheduler'), 'django_celery_results': ('Celery', None), 'huey': ('Huey', 'queue'), 'arq': ('arq', 'queue'), 'taskiq': ('Taskiq', 'queue'), 'faststream': ('FastStream', 'queue'),
 'aiormq': ('RabbitMQ', 'queue'), 'django_rq': ('RQ', 'queue'), 'ddtrace': ('Datadog', 'monitoring'), 'newrelic': ('New Relic', 'monitoring'), 'elasticapm': ('Elastic APM', 'monitoring'),
 'prometheus_fastapi_instrumentator': ('Prometheus', 'monitoring'), 'django_prometheus': ('Prometheus', 'monitoring'), 'starlette_prometheus': ('Prometheus', 'monitoring'), 'starlette_exporter': ('Prometheus', 'monitoring'),
 'logfire': ('Logfire', 'monitoring'), 'statsd': (None, 'monitoring'), 'urllib.request': (None, 'http'), 'httplib2': (None, 'http'), 'storages': (None, 'cloud'), 'minio': ('MinIO', 'cloud'),
 'unfold': (None, None), 'simple_history': (None, None), 'pgvector': ('pgvector', None), 'solo': (None, None), 'av': (None, None), 'health_check': (None, None), 'debug_toolbar': (None, None), 'emails': (None, None),
 'fastapi_csrf_protect': (None, None), 'packaging': (None, None), 'fastapi_async_sqlalchemy': ('SQLAlchemy', 'orm'), 'zxcvbn': (None, None), 'bleach': (None, None), 'backports': (None, None), 'loguru': (None, None), 'structlog': (None, None),
 'fontTools': (None, None), 'win32com': (None, None), 'pythoncom': (None, None), 'win32api': (None, None), 'win32process': (None, None), 'win32gui': (None, None), 'pywintypes': (None, None), 'win32event': (None, None),
 'win32evtlog': (None, None), 'win32con': (None, None), 'fitz': (None, None), 'django_hosts': (None, None), 'saiyaku': (None, None), 'pyscord_storage': (None, None), 'pixivpy3': (None, None),
 'pulumi': ('Pulumi', 'iac'), 'aws_cdk': ('AWS CDK', 'iac'), 'ragas': (None, 'ai'), 'certifi': (None, None), 'datasets': (None, 'ai'), 'llama_parse': ('LlamaIndex', 'ai'), 'googleapiclient': ('Google API', 'cloud'), 'webrtcvad': (None, None),
 'jobspy': (None, None), 'apify_client': (None, None),
 'clerk_backend_api': ('Clerk', 'auth'), 'cryptography': (None, None), 'tiktoken': (None, 'ai'), 'sentence_transformers': ('Transformers', 'ai'), 'huggingface_hub': ('Transformers', 'ai'),
 'xgboost': ('XGBoost', 'ai'), 'onnxruntime': ('ONNX Runtime', 'ai'), 'jsonschema': (None, None), 'joblib': (None, None), 'supabase': ('Supabase', 'cloud'),
 'setuptools': (None, None), 'dateutil': (None, None), 'pytz': (None, None), 'attr': (None, None), 'attrs': (None, None), 'multipart': (None, None), 'anyio': (None, None), 'aiofiles': (None, None),
}
NPM = {
 'express': ('Express', None), 'fastify': ('Fastify', None), 'koa': ('Koa', None), 'hono': ('Hono', None),
 'react': ('React', None), 'react-dom': ('React', None), 'react-router': ('React Router', None), 'react-router-dom': ('React Router', None), 'next': ('Next.js', None),
 'vue': ('Vue', None), 'svelte': ('Svelte', None), 'zustand': ('상태 관리', None), 'redux': ('상태 관리', None), 'react-redux': ('상태 관리', None), 'recoil': ('상태 관리', None), 'jotai': ('상태 관리', None),
 'axios': ('axios', 'http'), 'node-fetch': ('node-fetch', 'http'), 'ky': ('ky', 'http'), 'got': ('got', 'http'),
 'prisma': ('Prisma', 'orm'), 'typeorm': ('TypeORM', 'orm'), 'sequelize': ('Sequelize', 'orm'), 'drizzle-orm': ('Drizzle', 'orm'), 'mongoose': ('MongoDB', None), 'mongodb': ('MongoDB', None),
 'mysql2': ('MySQL', None), 'mysql': ('MySQL', None), 'pg': ('PostgreSQL', None), 'ioredis': ('Redis', None), 'redis': ('Redis', None),
 'jsonwebtoken': ('JWT', 'auth'), 'jose': ('JWT', 'auth'), 'bcrypt': (None, 'auth'), 'bcryptjs': (None, 'auth'), 'passport': ('Passport', 'auth'), 'next-auth': ('NextAuth', 'oauth'),
 'zod': ('입력 검증', None), 'joi': ('입력 검증', None), 'yup': ('입력 검증', None), 'class-validator': ('입력 검증', None), 'class-transformer': (None, None),
 'jest': ('Jest', 'test'), 'vitest': ('Vitest', 'test'), 'mocha': ('Mocha', 'test'), 'chai': ('Mocha', 'test'), 'supertest': ('Supertest', 'test'), 'cypress': ('Cypress', 'test'), 'fake-indexeddb': (None, 'test'),
 'socket.io': ('WebSocket', 'websocket'), 'socket.io-client': ('WebSocket', 'websocket'), 'ws': ('WebSocket', 'websocket'),
 'bullmq': ('BullMQ', 'queue'), 'bull': ('BullMQ', 'queue'), 'amqplib': ('RabbitMQ', 'queue'), 'kafkajs': ('Kafka', 'queue'),
 'aws-sdk': ('AWS SDK', 'cloud'), 'firebase': ('Firebase', 'cloud'), 'firebase-admin': ('Firebase', 'cloud'),
 'multer': (None, None), 'cors': (None, None), 'helmet': (None, None), 'cookie-parser': (None, None), 'dotenv': (None, None), 'morgan': (None, None), 'express-rate-limit': (None, None), 'compression': (None, None),
 'node-cron': ('node-cron', 'scheduler'), 'cron': ('node-cron', 'scheduler'), 'winston': (None, None), 'pino': (None, None), 'swagger-ui-express': ('Swagger/OpenAPI', None),
 'tailwindcss': ('Tailwind CSS', None), 'vite': ('Vite', None), 'typescript': (None, None), 'openai': ('OpenAI API', 'ai'), 'langchain': ('LangChain', 'ai'),
 'lru-cache': ('lru-cache', 'cache'), 'node-cache': ('node-cache', 'cache'), 'stripe': ('Stripe', 'payment'), 'uuid': (None, None), 'dayjs': (None, None), 'date-fns': (None, None), 'lodash': (None, None), 'clsx': (None, None),
 'lucide-react': (None, None), 'motion': (None, None), 'class-variance-authority': (None, None), 'cmdk': (None, None), 'vaul': (None, None), 'embla-carousel-react': (None, None),
 'graphql': ('GraphQL', None), 'graphql-subscriptions': ('GraphQL', None), 'apollo-server': ('GraphQL', None), 'apollo-server-express': ('GraphQL', None), 'graphql-yoga': ('GraphQL', None), 'es-hangul': (None, None),
 'jest-mock-extended': (None, 'test'), 'vitest-mock-extended': (None, 'test'), 'express-session': (None, None), 'connect-redis': ('Redis', None), 'jwks-rsa': ('JWT', 'auth'), 'speakeasy': (None, None), 'unplugin-swc': (None, None),
 'geojson': (None, None), 'react-hook-form': (None, None),
 'paypal-rest-sdk': ('PayPal', 'payment'), 'razorpay': ('Razorpay', 'payment'), 'mercadopago': ('Mercado Pago', 'payment'), 'braintree': ('Braintree', 'payment'), 'midtrans-client': ('Midtrans', 'payment'),
 'xendit-node': ('Xendit', 'payment'), 'paystack': ('Paystack', 'payment'), 'iamport': ('아임포트', 'payment'), 'square': ('Square', 'payment'),
 'arctic': (None, 'oauth'), 'openid-client': (None, 'oauth'), 'simple-oauth2': (None, 'oauth'), 'oauth': (None, 'oauth'), 'grant': (None, 'oauth'), 'better-auth': ('Better Auth', 'oauth'), 'auth0': ('Auth0', 'oauth'), 'googleapis': ('Google API', 'cloud'),
 'keyv': (None, 'cache'), 'cacheable': (None, 'cache'), 'memory-cache': (None, 'cache'), 'quick-lru': (None, 'cache'), 'apicache': (None, 'cache'),
 'amqp-connection-manager': ('RabbitMQ', 'queue'), 'bee-queue': (None, 'queue'), 'sqs-consumer': ('AWS SQS', 'queue'), 'sqs-producer': ('AWS SQS', 'queue'), 'nats': ('NATS', 'queue'), 'mqtt': ('MQTT', 'queue'), 'pg-boss': ('pg-boss', 'queue'),
 'graphile-worker': (None, 'queue'), 'inngest': ('Inngest', 'queue'), 'agenda': (None, 'scheduler'),
 'dd-trace': ('Datadog', 'monitoring'), 'newrelic': ('New Relic', 'monitoring'), 'elastic-apm-node': ('Elastic APM', 'monitoring'), 'express-prom-bundle': ('Prometheus', 'monitoring'),
 'undici': (None, 'http'), 'superagent': (None, 'http'), 'cross-fetch': (None, 'http'), 'isomorphic-fetch': (None, 'http'), 'ofetch': (None, 'http'), 'request': (None, 'http'),
 'cloudinary': ('Cloudinary', 'cloud'), 'minio': ('MinIO', 'cloud'), 'multer-s3': ('AWS SDK', 'cloud'), 'redlock': ('Redis', None), 'resend': (None, None), 'twilio': (None, None),
 'nestjs-zod': ('입력 검증', None), 'nestjs-i18n': (None, None), 'ms': (None, None), 'otpauth': (None, None), 'mime-types': (None, None), 'react-email': (None, None), 'sonner': (None, None), 'next-themes': (None, None),
 'tailwind-merge': (None, None), 'pino-http': (None, None), 'pino': (None, None), 'winston': (None, None), 'uuidv7': (None, None), 'fork-ts-checker-webpack-plugin': (None, None),
 'sharp': (None, None), 'fast-check': (None, 'test'), 'opossum': (None, None), 'rate-limit-redis': ('Redis', None), 'swagger-jsdoc': ('Swagger/OpenAPI', None), 'swagger-ui-express': ('Swagger/OpenAPI', None), 'async-retry': (None, None),
 'winston-daily-rotate-file': (None, None), 'express-validator': ('입력 검증', None), 'response-time': (None, None), 'bignumber.js': (None, None), 'graphql-request': ('GraphQL', 'http'), 'dockerode': (None, None),
 'js-yaml': (None, None), 'async-mutex': (None, None), 'html-to-text': (None, None), 'isemail': (None, None), 'debug': (None, None), 'unisms': (None, None), 'qcloud-cos-sts': (None, None), 'cos-nodejs-sdk-v5': (None, 'cloud'),
 'qs': (None, None), 'randomstring': (None, None), 'ollama': ('Ollama', 'ai'), 'drizzle-zod': ('Drizzle', 'orm'), 'drizzle-kit': ('Drizzle', 'orm'), 'sanitize-html': (None, None), 'http-status-codes': (None, None), 'ejs': (None, None),
 'leaflet': (None, None), 'server-only': (None, None), 'slugify': (None, None), 'radix-ui': (None, None), 'geist': (None, None), 'chalk': (None, None), 'monaco-editor': (None, None), 'pinia': ('Vue', None), 'vue-router': ('Vue', None),
 'dexie': (None, None), 'sql.js': (None, None), 'playwright': ('Playwright', 'test'), 'ffmpeg-static': (None, None),
 'aws-cdk-lib': ('AWS CDK', 'iac'), 'async': (None, None), 'config': (None, None), 'steamapi': (None, None), 'express-bearer-token': (None, None), 'http-errors': (None, None), 'jszip': (None, None), 'yaml': (None, None),
 'ssh2': (None, None), 'fflate': (None, None), 'croner': (None, 'scheduler'), 'suncalc': (None, None), 'react-syntax-highlighter': (None, None), 'dompurify': (None, None), 'highlight.js': (None, None),
 'rxjs': (None, None), 'argon2': (None, 'auth'), 'nestjs-pino': (None, None), 'prom-client': ('Prometheus', 'monitoring'), 'cache-manager': ('cache-manager', 'cache'),
 'cache-manager-redis-store': ('Redis', 'cache'), 'cache-manager-ioredis': ('Redis', 'cache'), 'cache-manager-redis-yet': ('Redis', 'cache'), 'nodemailer': ('Nodemailer', None),
 'google-auth-library': ('Google API', 'oauth'), 'eventemitter2': (None, None), 'k6': ('k6', 'loadtest'), 'reflect-metadata': (None, None), 'globals': (None, None), 'typescript-eslint': (None, None),
 'react-markdown': (None, None), 'pdfkit': (None, None),
 'expo': ('Expo', None), 'react-native': ('React Native', None), 'electron': ('Electron', None), 'three': ('Three.js', None), 'd3': ('D3', None), 'recharts': ('Recharts', None),
}
NPM_EXACT = {'@golevelup/nestjs-rabbitmq': ('RabbitMQ', 'queue'), '@aws-sdk/client-sqs': ('AWS SQS', 'queue'), '@google-cloud/pubsub': ('Google Pub/Sub', 'queue'), '@upstash/redis': ('Redis', None), '@upstash/qstash': (None, 'queue'),
             '@nestjs/microservices': ('NestJS Microservices', None), '@react-oauth/google': (None, 'oauth'), '@vercel/blob': (None, 'cloud'), '@isaacs/ttlcache': (None, 'cache'), '@nestjs/graphql': ('GraphQL', None), '@nestjs/apollo': ('GraphQL', None), '@nestjs/jwt': ('JWT', 'auth'), '@nestjs/passport': ('Passport', 'auth'), '@nestjs/cache-manager': ('cache-manager', 'cache'), '@nestjs/bullmq': ('BullMQ', 'queue'), '@nestjs/bull': ('BullMQ', 'queue'),
             '@nestjs/schedule': ('NestJS', 'scheduler'), '@nestjs/swagger': ('Swagger/OpenAPI', None), '@nestjs/typeorm': ('TypeORM', 'orm'), '@nestjs/mongoose': ('MongoDB', None),
             '@nestjs/websockets': ('WebSocket', 'websocket'), '@nestjs/platform-socket.io': ('WebSocket', 'websocket'), '@nestjs/axios': ('axios', 'http')}
NPM_SCOPE = [('@pulumi/', 'Pulumi', 'iac'), ('@hono/node-ws', 'WebSocket', 'websocket'), ('@hono/', 'Hono', None), ('@angular/', 'Angular', None), ('@base-ui/', None, None), ('@stylistic/', None, None), ('@testcontainers/', 'Testcontainers', 'test'), ('@paypal/', 'PayPal', 'payment'), ('@portone/', '포트원', 'payment'), ('@stripe/', 'Stripe', 'payment'), ('@lemonsqueezy/', None, 'payment'), ('@paddle/', None, 'payment'), ('@mollie/', None, 'payment'), ('@adyen/', 'Adyen', 'payment'),
             ('@auth/', 'Auth.js', 'oauth'), ('@azure/msal', None, 'oauth'), ('@okta/', 'Okta', 'oauth'), ('@auth0/', 'Auth0', 'oauth'), ('@clerk/', 'Clerk', 'auth'), ('@datadog/', 'Datadog', 'monitoring'), ('@google-cloud/', 'Google Cloud', 'cloud'),
             ('@azure/', 'Azure', 'cloud'), ('@cloudflare/', None, 'cloud'), ('@redis/', 'Redis', None), ('@react-email/', None, None), ('@sendgrid/', None, None), ('@trigger.dev/', None, 'queue'), ('@keyv/redis', 'Redis', 'cache'), ('@turf/', None, None), ('@tailwindcss/', None, None), ('@typescript-eslint/', None, None), ('@apollo/', 'GraphQL', None), ('@neondatabase/', 'PostgreSQL', None), ('@stellar/', 'Stellar SDK', None), ('@willsoto/', 'Prometheus', 'monitoring'), ('@simplewebauthn/', None, 'auth'), ('@clerk/', 'Clerk', 'auth'), ('@eslint/', None, None), ('@modelcontextprotocol/', 'MCP SDK', 'ai'), ('@nest-lab/', None, None),
             ('@nestjs/', 'NestJS', None), ('@aws-sdk/', 'AWS SDK', 'cloud'), ('@testing-library/', 'Testing Library', 'test'), ('@playwright/', 'Playwright', 'test'), ('@jest/', 'Jest', 'test'), ('@vitest/', 'Vitest', 'test'),
             ('@tanstack/', 'TanStack Query', None), ('@prisma/', 'Prisma', 'orm'), ('@sentry/', 'Sentry', 'monitoring'), ('@reduxjs/', '상태 관리', None), ('@types/', None, None),
             ('@radix-ui/', None, None), ('@mui/', 'MUI', None), ('@emotion/', None, None), ('@anthropic-ai/', 'Anthropic API', 'ai'), ('@langchain/', 'LangChain', 'ai'), ('@google/', 'Google API', None),
             ('@tosspayments/', 'Toss Payments', 'payment'), ('@supabase/', 'Supabase', 'cloud'), ('@opentelemetry/', 'OpenTelemetry', 'monitoring'), ('@react-navigation/', 'React Native', None),
             ('@expo/', 'Expo', None), ('@vitejs/', 'Vite', None), ('@hookform/', None, None), ('@heroicons/', None, None), ('@faker-js/', None, 'test')]


def lookup(eco, mod):
    """-> (tool, capability) or None when the library is not in the dictionary"""
    if eco == 'java':
        for pre, tool, cap in JAVA:
            if mod == pre or mod.startswith(pre + '.'): return tool, cap
        return None
    if eco == 'py':
        parts = mod.split('.')
        two = PY.get('.'.join(parts[:2])) if len(parts) > 1 else None
        return two if two is not None else PY.get(parts[0])
    if mod.startswith('.'): return None
    if mod.startswith('@'):
        ex = NPM_EXACT.get('/'.join(mod.split('/')[:2]))
        if ex: return ex
        for pre, tool, cap in NPM_SCOPE:
            if mod.startswith(pre): return tool, cap
        return NPM.get('/'.join(mod.split('/')[:2]))
    root = mod.split('/')[0]
    if root.startswith('passport-'): return 'Passport', ('oauth' if any(x in root for x in ('google', 'kakao', 'naver', 'github', 'facebook', 'oauth', 'apple', 'twitter', 'discord', 'linkedin', 'steam', 'openid', 'oidc', 'saml', 'microsoft', 'azure')) else 'auth')
    if root.startswith('expo-'): return 'Expo', None
    if root.startswith('react-native-'): return 'React Native', None
    if root.startswith(('eslint-', 'vite-plugin-', 'remark-', 'rehype-')): return None, None
    if root.startswith('react-') and root not in NPM: return None
    return NPM.get(root)
