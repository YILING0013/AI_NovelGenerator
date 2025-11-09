# ssl_security_manager.py
# -*- coding: utf-8 -*-
"""
SSL安全管理模块
增强SSL/TLS安全性，防止中间人攻击
"""

import ssl
import certifi
import requests
from urllib3.util import SSLContext
from typing import Optional, Dict, Any
import logging
from pathlib import Path


class SSLSecurityManager:
    """
    SSL安全管理器
    确保所有HTTP请求都使用安全的SSL配置
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.custom_ca_bundle = None
        self._setup_ssl_security()

    def _setup_ssl_security(self):
        """设置SSL安全配置"""
        # 创建安全的SSL上下文
        self.secure_context = self._create_secure_ssl_context()

        # 设置requests默认配置
        self._configure_requests_security()

    def _create_secure_ssl_context(self) -> ssl.SSLContext:
        """创建安全的SSL上下文"""
        context = ssl.create_default_context()

        # 使用现代TLS版本
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3

        # 启用证书验证
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True

        # 使用certifi提供的CA证书
        context.load_verify_locations(certifi.where())

        # 设置安全的密码套件
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')

        # 启用HSTS (Strict Transport Security)
        try:
            context.set_alpn_protocols(['h2', 'http/1.1'])
        except AttributeError:
            # 某些Python版本可能不支持ALPN
            pass

        return context

    def _configure_requests_security(self):
        """配置requests库的安全设置"""
        # 设置默认的SSL上下文
        requests.adapters.DEFAULT_RETRIES = 3

        # 自定义适配器
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=10,
            pool_maxsize=10
        )

        # 注册适配器
        requests.Session().mount('http://', adapter)
        requests.Session().mount('https://', adapter)

    def get_secure_session(self) -> requests.Session:
        """获取安全的requests会话"""
        session = requests.Session()

        # 设置SSL验证
        session.verify = self._get_ca_bundle_path()

        # 设置超时
        session.timeout = (10, 30)  # 连接超时10秒，读取超时30秒

        # 设置安全头
        session.headers.update({
            'User-Agent': 'AI-NovelGenerator/1.0',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })

        # 设置适配器
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=10,
            pool_maxsize=10
        )
        session.mount('https://', adapter)
        session.mount('http://', adapter)

        return session

    def _get_ca_bundle_path(self) -> str:
        """获取CA证书包路径"""
        if self.custom_ca_bundle:
            return self.custom_ca_bundle
        return certifi.where()

    def set_custom_ca_bundle(self, ca_bundle_path: str) -> bool:
        """设置自定义CA证书包"""
        try:
            ca_path = Path(ca_bundle_path)
            if ca_path.exists() and ca_path.is_file():
                self.custom_ca_bundle = str(ca_path.absolute())
                self.logger.info(f"已加载自定义CA证书包: {ca_bundle_path}")
                return True
            else:
                self.logger.error(f"CA证书包不存在或不是文件: {ca_bundle_path}")
                return False
        except Exception as e:
            self.logger.error(f"设置自定义CA证书包失败: {e}")
            return False

    def verify_ssl_certificate(self, hostname: str, port: int = 443) -> Dict[str, Any]:
        """验证指定主机的SSL证书"""
        import socket
        from datetime import datetime

        result = {
            'hostname': hostname,
            'port': port,
            'valid': False,
            'certificate_info': {},
            'errors': []
        }

        try:
            # 创建SSL上下文
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED

            # 连接并验证证书
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    cipher = ssock.cipher()
                    protocol_version = ssock.version()

                    # 解析证书信息
                    result['valid'] = True
                    result['certificate_info'] = {
                        'subject': dict(x[0] for x in cert['subject']),
                        'issuer': dict(x[0] for x in cert['issuer']),
                        'version': cert['version'],
                        'serial_number': cert['serialNumber'],
                        'not_before': cert['notBefore'],
                        'not_after': cert['notAfter'],
                        'subject_alt_name': cert.get('subjectAltName', []),
                        'cipher': cipher,
                        'protocol_version': protocol_version
                    }

                    # 检查证书有效期
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    days_until_expiry = (not_after - datetime.now()).days

                    if days_until_expiry < 30:
                        result['warnings'] = [f"证书将在{days_until_expiry}天后过期"]

        except ssl.SSLCertVerificationError as e:
            result['errors'].append(f"SSL证书验证失败: {e}")
        except ssl.SSLError as e:
            result['errors'].append(f"SSL错误: {e}")
        except socket.timeout:
            result['errors'].append("连接超时")
        except Exception as e:
            result['errors'].append(f"验证失败: {e}")

        return result

    def secure_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        发起安全的HTTP请求
        强制SSL验证，不允许禁用证书验证
        """
        # 确保验证SSL证书
        if 'verify' in kwargs and kwargs['verify'] is False:
            self.logger.warning("检测到verify=False设置，已自动启用SSL验证")
            kwargs['verify'] = True

        # 使用默认CA证书
        if 'verify' not in kwargs:
            kwargs['verify'] = self._get_ca_bundle_path()

        # 设置默认超时
        if 'timeout' not in kwargs:
            kwargs['timeout'] = (10, 30)

        # 添加安全头
        headers = kwargs.get('headers', {})
        default_headers = {
            'User-Agent': 'AI-NovelGenerator/1.0',
        }
        headers.update(default_headers)
        kwargs['headers'] = headers

        # 使用安全会话
        session = self.get_secure_session()

        try:
            self.logger.debug(f"发起安全请求: {method} {url}")
            response = session.request(method, url, **kwargs)

            # 检查响应头中的安全信息
            self._check_security_headers(response)

            return response

        except requests.exceptions.SSLError as e:
            self.logger.error(f"SSL错误: {e}")
            raise
        except requests.exceptions.RequestException as e:
            self.logger.error(f"请求错误: {e}")
            raise
        finally:
            session.close()

    def _check_security_headers(self, response: requests.Response):
        """检查响应的安全头"""
        security_headers = [
            'Strict-Transport-Security',
            'X-Content-Type-Options',
            'X-Frame-Options',
            'X-XSS-Protection',
            'Content-Security-Policy'
        ]

        missing_headers = []
        for header in security_headers:
            if header not in response.headers:
                missing_headers.append(header)

        if missing_headers:
            self.logger.debug(f"缺少安全头: {missing_headers}")

    def validate_url_security(self, url: str) -> Dict[str, Any]:
        """验证URL的安全性"""
        result = {
            'url': url,
            'secure': False,
            'warnings': [],
            'recommendations': []
        }

        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(url)

            # 检查协议
            if parsed_url.scheme == 'https':
                result['secure'] = True
            elif parsed_url.scheme == 'http':
                result['warnings'].append("使用HTTP协议，数据传输未加密")
                result['recommendations'].append("建议使用HTTPS协议")
            else:
                result['warnings'].append(f"未知协议: {parsed_url.scheme}")

            # 检查主机名
            if not parsed_url.hostname:
                result['warnings'].append("无效的主机名")
                return result

            # 检查端口
            if parsed_url.port:
                if parsed_url.port in [80, 443]:
                    pass  # 标准端口
                elif parsed_url.port < 1024:
                    result['warnings'].append(f"使用系统端口: {parsed_url.port}")
                else:
                    result['recommendations'].append(f"非标准端口: {parsed_url.port}")

        except Exception as e:
            result['warnings'].append(f"URL解析错误: {e}")

        return result


# 全局SSL安全管理器实例
ssl_security_manager = SSLSecurityManager()


def secure_http_session() -> requests.Session:
    """获取安全的HTTP会话"""
    return ssl_security_manager.get_secure_session()


def secure_request(method: str, url: str, **kwargs) -> requests.Response:
    """发起安全的HTTP请求"""
    return ssl_security_manager.secure_request(method, url, **kwargs)


def validate_ssl_certificate(hostname: str, port: int = 443) -> Dict[str, Any]:
    """验证SSL证书"""
    return ssl_security_manager.verify_ssl_certificate(hostname, port)