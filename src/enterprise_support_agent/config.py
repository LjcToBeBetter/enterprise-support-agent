"""
统一配置模块。

主要功能：
    读取项目配置，供后端入口和其他模块使用。

主要部件：
    PROJECT_ROOT：项目根目录。
    Settings：定义配置字段、类型和默认值。
    settings：加载配置后得到的对象。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 根据当前文件的位置找到项目根目录。
# parents[0]：enterprise_support_agent 包目录
# parents[1]：src 目录
# parents[2]：项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """定义应用需要的配置。"""

    # 告诉 BaseSettings 去哪里读取 .env 文件，以及使用什么编码。
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    # 等号右边是默认值，没有提供对应配置时使用。
    app_name: str = "企业知识库与工单协作 Agent 平台"
    app_version: str = "0.1.0"

    host: str = "127.0.0.1"
    port: int = 8002

    # 开发时是否在代码保存后自动重启服务。
    reload: bool = True

    # PostgreSQL数据库的连接信息。
    # 这些值会自动从项目根目录的.env文件读取。
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "enterprise_support"
    db_user: str = "support_app"
    db_password: str

    # JWT签名密钥。
    # 生成和验证令牌时必须使用同一个密钥。
    jwt_secret_key: str

    # JWT使用的签名算法。
    jwt_algorithm: str = "HS256"

    # 登录令牌的有效时间，单位是分钟。
    jwt_access_token_expire_minutes: int = 30

    # S3兼容对象存储的连接地址。
    #
    # 本地开发使用RustFS的9000端口。9000 是 RustFS专门接收 S3程序请求的入口
    # 9001是管理页面，不是程序上传文件的接口。
    storage_endpoint_url: str = (
        "http://127.0.0.1:9000"
    )

    # RustFS访问账号。
    storage_access_key: str

    # RustFS访问密码。
    storage_secret_key: str

    # 企业知识库文件统一保存到这个Bucket。
    storage_bucket: str = (
        "enterprise-knowledge"
    )

    # boto3生成S3请求签名时需要区域信息。
    #
    # 本地RustFS并不真正区分AWS区域，
    # 但客户端仍需要一个合法值。
    storage_region: str = "us-east-1"

    # 单个知识库文件最大允许20MB。
    #
    # 1024 * 1024表示1MB，
    # 再乘20就是20MB。
    document_max_file_size_bytes: int = (
        20 * 1024 * 1024
    )

    # Qdrant的HTTP REST接口地址。
    #
    # 本地Docker容器通过6333端口提供REST接口。
    qdrant_url: str = (
        "http://127.0.0.1:6333"
    )

    # 保存知识库文本块向量的Collection名称。
    #
    # 可以把Collection近似理解成Qdrant中的一张向量表。
    qdrant_collection_name: str = (
        "enterprise_support_document_chunks"
    )

    # 是否优先使用gRPC接口。
    #
    # false：
    #     使用6333端口的REST接口。
    #
    # true：
    #     优先使用6334端口的gRPC接口。
    #
    # 当前开发阶段使用REST，方便调试。
    qdrant_prefer_grpc: bool = False

    # 连接和请求Qdrant的超时时间，单位为秒。
    qdrant_timeout_seconds: int = 10

    # Qdrant API密钥。
    #
    # 本地开发环境目前没有开启身份认证，
    # 所以默认值为None。
    #
    # 将来连接Qdrant Cloud或受保护的Qdrant服务时，
    # 可以在.env中配置QDRANT_API_KEY。
    qdrant_api_key: str | None = None

    # Embedding模型名称。
    #
    # 用来把文本块和用户问题转换成向量。
    embed_model_name: str

    # Embedding服务的API密钥。
    #
    # 这是敏感信息，只保存在.env中，
    # 不要直接写在Python代码里。
    embed_api_key: str

    # Embedding服务的OpenAI兼容接口地址。
    embed_base_url: str

    # 单次Embedding请求的超时时间，单位为秒。
    #
    # .env中没有提供时，默认使用60秒。
    embed_request_timeout_seconds: int = 60

    # Embedding请求失败后的最大重试次数。
    embed_max_retries: int = 3

    # 一次最多向Embedding服务发送多少个文本块。
    #
    # 后面批量向量化时使用。
    embed_batch_size: int = 32

    # Embedding模型实际输出的向量维度。
    #
    # Qdrant Collection的向量维度必须与它完全一致。
    qdrant_vector_size: int = 1024

    # Rerank模型名称。
    #
    # Rerank会同时读取用户问题和候选文本，
    # 重新判断每个候选是否真正能够回答问题。
    rerank_model_name: str = "qwen3-rerank"

    # 阿里云百炼Rerank接口地址。
    rerank_api_url: str = (
        "https://dashscope.aliyuncs.com/"
        "compatible-api/v1/reranks"
    )

    # Rerank服务API密钥。
    #
    # 当前与Embedding使用同一个百炼账号，
    # 但配置字段单独保留，方便以后更换服务。
    rerank_api_key: str

    # 单次Rerank请求超时时间，单位为秒。
    rerank_request_timeout_seconds: int = 30

    # Rerank请求失败后的最大重试次数。
    rerank_max_retries: int = 2

    # 一次最多允许交给Rerank多少条候选文本。
    rerank_max_documents: int = 50

    # 单条候选文本最多保留多少字符。
    #
    # 当前文本块通常只有800字符，
    # 这个限制主要用于防止未来传入过长内容。
    rerank_max_document_characters: int = 3500

# 创建配置对象：读取配置、转换类型并执行校验。
settings = Settings()

