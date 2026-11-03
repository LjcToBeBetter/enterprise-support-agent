"""
object_storage.py

主要功能：
    创建S3客户端并连接RustFS对象存储。

主要部件：
    ObjectStorage：
        保存S3客户端和Bucket名称；
        检查知识库Bucket是否存在；
        Bucket不存在时自动创建。

    object_storage：
        项目统一使用的对象存储实例。
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from enterprise_support_agent.config import (
    settings,
)


class ObjectStorage:
    """S3兼容对象存储客户端。"""

    def __init__(self) -> None:
        """
        根据项目配置创建S3客户端。

        创建对象时只准备客户端配置，
        还不会立刻发送网络请求。
        """

        # 保存知识库使用的Bucket名称。
        self.bucket_name = (
            settings.storage_bucket
        )

        # boto3.client("s3")创建S3客户端对象。
        #
        # 后面通过这个客户端调用：
        # head_bucket、create_bucket、
        # put_object、get_object等S3操作。
        self.client = boto3.client(
            "s3",

            # 指定请求发送到本地RustFS，
            # 而不是发送到AWS云。
            endpoint_url=(
                settings.storage_endpoint_url
            ),

            # RustFS访问账号。
            aws_access_key_id=(
                settings.storage_access_key
            ),

            # RustFS访问密码。
            aws_secret_access_key=(
                settings.storage_secret_key
            ),

            # boto3生成请求签名时使用的区域。
            region_name=(
                settings.storage_region
            ),

            # 规定使用S3版本4签名，
            # 并使用路径形式访问Bucket。
            #
            # 请求地址类似：
            # http://127.0.0.1:9000/
            # enterprise-knowledge/object-key
            config=Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": "path"
                },
            ),
        )

    def ensure_bucket_exists(self) -> None:
        """
        检查知识库Bucket是否存在。

        Bucket存在：
            不进行修改。

        Bucket不存在：
            自动创建Bucket。

        其他错误：
            继续抛出，让启动过程明确失败。
        """

        try:
            # head_bucket()只检查Bucket是否存在以及
            # 当前账号是否有权访问，不会读取其中的文件。
            self.client.head_bucket(
                Bucket=self.bucket_name
            )

        except ClientError as error:
            # 从S3错误响应中取得错误代码。
            error_code = str(
                error.response
                .get("Error", {})
                .get("Code", "")
            )

            # 这些错误表示Bucket不存在。
            if error_code in {
                "404",
                "NoSuchBucket",
                "NotFound",
            }:
                # create_bucket()创建新的Bucket。
                self.client.create_bucket(
                    Bucket=self.bucket_name
                )

                return

            # 如果是密码错误、连接权限不足等其他问题，
            # 不应该伪装成Bucket不存在，直接继续抛出。
            raise

    def upload_bytes(
        self,
        object_key: str,
        file_content: bytes,
        content_type: str,
    ) -> None:
        """
        将文件内容上传到对象存储。

        接收：
            object_key：
                文件在Bucket中的唯一位置。

            file_content：
                文件的二进制内容。

            content_type：
                文件的MIME类型，例如application/pdf。

        返回：
            没有返回值。

        异常：
            上传失败时，boto3会抛出异常。
        """

        # put_object()按照S3接口规则上传一个对象。
        self.client.put_object(
            # 文件保存到哪个Bucket。
            Bucket=self.bucket_name,

            # 文件在Bucket中的唯一位置。
            Key=object_key,

            # 真正需要保存的文件二进制内容。
            Body=file_content,

            # 文件的MIME类型。
            ContentType=content_type,
        )

    def delete_object(
        self,
        object_key: str,
    ) -> None:
        """
        从对象存储中删除一个文件。

        接收：
            object_key：
                需要删除的文件位置。

        返回：
            没有返回值。
        """

        # delete_object()按照Bucket和object_key
        # 删除指定对象。
        self.client.delete_object(
            Bucket=self.bucket_name,
            Key=object_key,
        )

    def download_bytes(
        self,
        object_key: str,
    ) -> bytes:
        """
        从对象存储读取完整文件内容。

        接收：
            object_key：
                文件在Bucket中的唯一位置。

        返回：
            文件的二进制内容。

        异常：
            下载失败时，boto3会抛出异常。
        """

        # get_object()根据Bucket和object_key
        # 从RustFS取得对象。
        response = self.client.get_object(
            Bucket=self.bucket_name,
            Key=object_key,
        )

        # Body不是普通bytes，
        # 而是boto3提供的流式读取对象。
        response_body = response["Body"]

        try:
            # read()读取完整文件内容，
            # 返回bytes类型。
            return response_body.read()

        finally:
            # 无论读取成功还是失败，
            # 都关闭响应流并释放网络连接。
            response_body.close()

# 创建项目统一使用的对象存储实例。
#
# 这里只创建客户端对象，
# 不会马上访问RustFS。
object_storage = ObjectStorage()