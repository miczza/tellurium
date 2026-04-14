"""Auto-generated CDP bindings for the Network domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class ResourceType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ResourceType:
        return cls(val)


class LoaderId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> LoaderId:
        return cls(val)


class RequestId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> RequestId:
        return cls(val)


class InterceptionId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> InterceptionId:
        return cls(val)


class ErrorReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ErrorReason:
        return cls(val)


class TimeSinceEpoch(float):
    """CDP type alias."""

    def to_json(self) -> float:
        return float(self)

    @classmethod
    def from_json(cls, val: float) -> TimeSinceEpoch:
        return cls(val)


class MonotonicTime(float):
    """CDP type alias."""

    def to_json(self) -> float:
        return float(self)

    @classmethod
    def from_json(cls, val: float) -> MonotonicTime:
        return cls(val)


@dataclass
class Headers:
    pass

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Headers:
        return cls()


class ConnectionType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ConnectionType:
        return cls(val)


class CookieSameSite(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CookieSameSite:
        return cls(val)


class CookiePriority(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CookiePriority:
        return cls(val)


class CookieSourceScheme(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CookieSourceScheme:
        return cls(val)


@dataclass
class ResourceTiming:
    request_time: float
    proxy_start: float
    proxy_end: float
    dns_start: float
    dns_end: float
    connect_start: float
    connect_end: float
    ssl_start: float
    ssl_end: float
    worker_start: float
    worker_ready: float
    worker_fetch_start: float
    worker_respond_with_settled: float
    send_start: float
    send_end: float
    push_start: float
    push_end: float
    receive_headers_start: float
    receive_headers_end: float
    worker_router_evaluation_start: Optional[float] = None
    worker_cache_lookup_start: Optional[float] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['requestTime'] = request_time
        d['proxyStart'] = proxy_start
        d['proxyEnd'] = proxy_end
        d['dnsStart'] = dns_start
        d['dnsEnd'] = dns_end
        d['connectStart'] = connect_start
        d['connectEnd'] = connect_end
        d['sslStart'] = ssl_start
        d['sslEnd'] = ssl_end
        d['workerStart'] = worker_start
        d['workerReady'] = worker_ready
        d['workerFetchStart'] = worker_fetch_start
        d['workerRespondWithSettled'] = worker_respond_with_settled
        d['sendStart'] = send_start
        d['sendEnd'] = send_end
        d['pushStart'] = push_start
        d['pushEnd'] = push_end
        d['receiveHeadersStart'] = receive_headers_start
        d['receiveHeadersEnd'] = receive_headers_end
        if self.worker_router_evaluation_start is not None:
            d['workerRouterEvaluationStart'] = self.worker_router_evaluation_start
        if self.worker_cache_lookup_start is not None:
            d['workerCacheLookupStart'] = self.worker_cache_lookup_start
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ResourceTiming:
        return cls(
            request_time=float(data['requestTime']),
            proxy_start=float(data['proxyStart']),
            proxy_end=float(data['proxyEnd']),
            dns_start=float(data['dnsStart']),
            dns_end=float(data['dnsEnd']),
            connect_start=float(data['connectStart']),
            connect_end=float(data['connectEnd']),
            ssl_start=float(data['sslStart']),
            ssl_end=float(data['sslEnd']),
            worker_start=float(data['workerStart']),
            worker_ready=float(data['workerReady']),
            worker_fetch_start=float(data['workerFetchStart']),
            worker_respond_with_settled=float(data['workerRespondWithSettled']),
            send_start=float(data['sendStart']),
            send_end=float(data['sendEnd']),
            push_start=float(data['pushStart']),
            push_end=float(data['pushEnd']),
            receive_headers_start=float(data['receiveHeadersStart']),
            receive_headers_end=float(data['receiveHeadersEnd']),
            worker_router_evaluation_start=float(data['workerRouterEvaluationStart']) if 'workerRouterEvaluationStart' in data else None,
            worker_cache_lookup_start=float(data['workerCacheLookupStart']) if 'workerCacheLookupStart' in data else None,
        )


class ResourcePriority(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ResourcePriority:
        return cls(val)


class RenderBlockingBehavior(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> RenderBlockingBehavior:
        return cls(val)


@dataclass
class PostDataEntry:
    bytes: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.bytes is not None:
            d['bytes'] = self.bytes
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PostDataEntry:
        return cls(
            bytes=str(data['bytes']) if 'bytes' in data else None,
        )


@dataclass
class Request:
    url: str
    method: str
    headers: Headers
    initial_priority: ResourcePriority
    referrer_policy: str
    url_fragment: Optional[str] = None
    post_data: Optional[str] = None
    has_post_data: Optional[bool] = None
    post_data_entries: Optional[list[PostDataEntry]] = None
    mixed_content_type: Optional[MixedContentType] = None
    is_link_preload: Optional[bool] = None
    trust_token_params: Optional[TrustTokenParams] = None
    is_same_site: Optional[bool] = None
    is_ad_related: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['method'] = method
        d['headers'] = headers.to_json()
        d['initialPriority'] = initial_priority.to_json()
        d['referrerPolicy'] = referrer_policy
        if self.url_fragment is not None:
            d['urlFragment'] = self.url_fragment
        if self.post_data is not None:
            d['postData'] = self.post_data
        if self.has_post_data is not None:
            d['hasPostData'] = self.has_post_data
        if self.post_data_entries is not None:
            d['postDataEntries'] = [i.to_json() for i in self.post_data_entries]
        if self.mixed_content_type is not None:
            d['mixedContentType'] = self.mixed_content_type.to_json()
        if self.is_link_preload is not None:
            d['isLinkPreload'] = self.is_link_preload
        if self.trust_token_params is not None:
            d['trustTokenParams'] = self.trust_token_params.to_json()
        if self.is_same_site is not None:
            d['isSameSite'] = self.is_same_site
        if self.is_ad_related is not None:
            d['isAdRelated'] = self.is_ad_related
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Request:
        return cls(
            url=str(data['url']),
            method=str(data['method']),
            headers=Headers.from_json(data['headers']),
            initial_priority=ResourcePriority.from_json(data['initialPriority']),
            referrer_policy=str(data['referrerPolicy']),
            url_fragment=str(data['urlFragment']) if 'urlFragment' in data else None,
            post_data=str(data['postData']) if 'postData' in data else None,
            has_post_data=bool(data['hasPostData']) if 'hasPostData' in data else None,
            post_data_entries=[PostDataEntry.from_json(i) for i in data['postDataEntries']] if 'postDataEntries' in data else None,
            mixed_content_type=MixedContentType.from_json(data['mixedContentType']) if 'mixedContentType' in data else None,
            is_link_preload=bool(data['isLinkPreload']) if 'isLinkPreload' in data else None,
            trust_token_params=TrustTokenParams.from_json(data['trustTokenParams']) if 'trustTokenParams' in data else None,
            is_same_site=bool(data['isSameSite']) if 'isSameSite' in data else None,
            is_ad_related=bool(data['isAdRelated']) if 'isAdRelated' in data else None,
        )


@dataclass
class SignedCertificateTimestamp:
    status: str
    origin: str
    log_description: str
    log_id: str
    timestamp: float
    hash_algorithm: str
    signature_algorithm: str
    signature_data: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['status'] = status
        d['origin'] = origin
        d['logDescription'] = log_description
        d['logId'] = log_id
        d['timestamp'] = timestamp
        d['hashAlgorithm'] = hash_algorithm
        d['signatureAlgorithm'] = signature_algorithm
        d['signatureData'] = signature_data
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SignedCertificateTimestamp:
        return cls(
            status=str(data['status']),
            origin=str(data['origin']),
            log_description=str(data['logDescription']),
            log_id=str(data['logId']),
            timestamp=float(data['timestamp']),
            hash_algorithm=str(data['hashAlgorithm']),
            signature_algorithm=str(data['signatureAlgorithm']),
            signature_data=str(data['signatureData']),
        )


@dataclass
class SecurityDetails:
    protocol: str
    key_exchange: str
    cipher: str
    certificate_id: CertificateId
    subject_name: str
    san_list: list[str]
    issuer: str
    valid_from: TimeSinceEpoch
    valid_to: TimeSinceEpoch
    signed_certificate_timestamp_list: list[SignedCertificateTimestamp]
    certificate_transparency_compliance: CertificateTransparencyCompliance
    encrypted_client_hello: bool
    key_exchange_group: Optional[str] = None
    mac: Optional[str] = None
    server_signature_algorithm: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['protocol'] = protocol
        d['keyExchange'] = key_exchange
        d['cipher'] = cipher
        d['certificateId'] = certificate_id.to_json()
        d['subjectName'] = subject_name
        d['sanList'] = list(san_list)
        d['issuer'] = issuer
        d['validFrom'] = valid_from.to_json()
        d['validTo'] = valid_to.to_json()
        d['signedCertificateTimestampList'] = [i.to_json() for i in signed_certificate_timestamp_list]
        d['certificateTransparencyCompliance'] = certificate_transparency_compliance.to_json()
        d['encryptedClientHello'] = encrypted_client_hello
        if self.key_exchange_group is not None:
            d['keyExchangeGroup'] = self.key_exchange_group
        if self.mac is not None:
            d['mac'] = self.mac
        if self.server_signature_algorithm is not None:
            d['serverSignatureAlgorithm'] = self.server_signature_algorithm
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SecurityDetails:
        return cls(
            protocol=str(data['protocol']),
            key_exchange=str(data['keyExchange']),
            cipher=str(data['cipher']),
            certificate_id=CertificateId.from_json(data['certificateId']),
            subject_name=str(data['subjectName']),
            san_list=[str(i) for i in data['sanList']],
            issuer=str(data['issuer']),
            valid_from=TimeSinceEpoch.from_json(data['validFrom']),
            valid_to=TimeSinceEpoch.from_json(data['validTo']),
            signed_certificate_timestamp_list=[SignedCertificateTimestamp.from_json(i) for i in data['signedCertificateTimestampList']],
            certificate_transparency_compliance=CertificateTransparencyCompliance.from_json(data['certificateTransparencyCompliance']),
            encrypted_client_hello=bool(data['encryptedClientHello']),
            key_exchange_group=str(data['keyExchangeGroup']) if 'keyExchangeGroup' in data else None,
            mac=str(data['mac']) if 'mac' in data else None,
            server_signature_algorithm=int(data['serverSignatureAlgorithm']) if 'serverSignatureAlgorithm' in data else None,
        )


class CertificateTransparencyCompliance(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CertificateTransparencyCompliance:
        return cls(val)


class BlockedReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> BlockedReason:
        return cls(val)


class CorsError(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CorsError:
        return cls(val)


@dataclass
class CorsErrorStatus:
    cors_error: CorsError
    failed_parameter: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['corsError'] = cors_error.to_json()
        d['failedParameter'] = failed_parameter
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CorsErrorStatus:
        return cls(
            cors_error=CorsError.from_json(data['corsError']),
            failed_parameter=str(data['failedParameter']),
        )


class ServiceWorkerResponseSource(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ServiceWorkerResponseSource:
        return cls(val)


@dataclass
class TrustTokenParams:
    operation: TrustTokenOperationType
    refresh_policy: str
    issuers: Optional[list[str]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['operation'] = operation.to_json()
        d['refreshPolicy'] = refresh_policy
        if self.issuers is not None:
            d['issuers'] = list(self.issuers)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TrustTokenParams:
        return cls(
            operation=TrustTokenOperationType.from_json(data['operation']),
            refresh_policy=str(data['refreshPolicy']),
            issuers=[str(i) for i in data['issuers']] if 'issuers' in data else None,
        )


class TrustTokenOperationType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> TrustTokenOperationType:
        return cls(val)


class AlternateProtocolUsage(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AlternateProtocolUsage:
        return cls(val)


class ServiceWorkerRouterSource(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ServiceWorkerRouterSource:
        return cls(val)


@dataclass
class ServiceWorkerRouterInfo:
    rule_id_matched: Optional[int] = None
    matched_source_type: Optional[ServiceWorkerRouterSource] = None
    actual_source_type: Optional[ServiceWorkerRouterSource] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.rule_id_matched is not None:
            d['ruleIdMatched'] = self.rule_id_matched
        if self.matched_source_type is not None:
            d['matchedSourceType'] = self.matched_source_type.to_json()
        if self.actual_source_type is not None:
            d['actualSourceType'] = self.actual_source_type.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ServiceWorkerRouterInfo:
        return cls(
            rule_id_matched=int(data['ruleIdMatched']) if 'ruleIdMatched' in data else None,
            matched_source_type=ServiceWorkerRouterSource.from_json(data['matchedSourceType']) if 'matchedSourceType' in data else None,
            actual_source_type=ServiceWorkerRouterSource.from_json(data['actualSourceType']) if 'actualSourceType' in data else None,
        )


@dataclass
class Response:
    url: str
    status: int
    status_text: str
    headers: Headers
    mime_type: str
    charset: str
    connection_reused: bool
    connection_id: float
    encoded_data_length: float
    security_state: SecurityState
    headers_text: Optional[str] = None
    request_headers: Optional[Headers] = None
    request_headers_text: Optional[str] = None
    remote_ip_address: Optional[str] = None
    remote_port: Optional[int] = None
    from_disk_cache: Optional[bool] = None
    from_service_worker: Optional[bool] = None
    from_prefetch_cache: Optional[bool] = None
    from_early_hints: Optional[bool] = None
    service_worker_router_info: Optional[ServiceWorkerRouterInfo] = None
    timing: Optional[ResourceTiming] = None
    service_worker_response_source: Optional[ServiceWorkerResponseSource] = None
    response_time: Optional[TimeSinceEpoch] = None
    cache_storage_cache_name: Optional[str] = None
    protocol: Optional[str] = None
    alternate_protocol_usage: Optional[AlternateProtocolUsage] = None
    security_details: Optional[SecurityDetails] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['status'] = status
        d['statusText'] = status_text
        d['headers'] = headers.to_json()
        d['mimeType'] = mime_type
        d['charset'] = charset
        d['connectionReused'] = connection_reused
        d['connectionId'] = connection_id
        d['encodedDataLength'] = encoded_data_length
        d['securityState'] = security_state.to_json()
        if self.headers_text is not None:
            d['headersText'] = self.headers_text
        if self.request_headers is not None:
            d['requestHeaders'] = self.request_headers.to_json()
        if self.request_headers_text is not None:
            d['requestHeadersText'] = self.request_headers_text
        if self.remote_ip_address is not None:
            d['remoteIPAddress'] = self.remote_ip_address
        if self.remote_port is not None:
            d['remotePort'] = self.remote_port
        if self.from_disk_cache is not None:
            d['fromDiskCache'] = self.from_disk_cache
        if self.from_service_worker is not None:
            d['fromServiceWorker'] = self.from_service_worker
        if self.from_prefetch_cache is not None:
            d['fromPrefetchCache'] = self.from_prefetch_cache
        if self.from_early_hints is not None:
            d['fromEarlyHints'] = self.from_early_hints
        if self.service_worker_router_info is not None:
            d['serviceWorkerRouterInfo'] = self.service_worker_router_info.to_json()
        if self.timing is not None:
            d['timing'] = self.timing.to_json()
        if self.service_worker_response_source is not None:
            d['serviceWorkerResponseSource'] = self.service_worker_response_source.to_json()
        if self.response_time is not None:
            d['responseTime'] = self.response_time.to_json()
        if self.cache_storage_cache_name is not None:
            d['cacheStorageCacheName'] = self.cache_storage_cache_name
        if self.protocol is not None:
            d['protocol'] = self.protocol
        if self.alternate_protocol_usage is not None:
            d['alternateProtocolUsage'] = self.alternate_protocol_usage.to_json()
        if self.security_details is not None:
            d['securityDetails'] = self.security_details.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Response:
        return cls(
            url=str(data['url']),
            status=int(data['status']),
            status_text=str(data['statusText']),
            headers=Headers.from_json(data['headers']),
            mime_type=str(data['mimeType']),
            charset=str(data['charset']),
            connection_reused=bool(data['connectionReused']),
            connection_id=float(data['connectionId']),
            encoded_data_length=float(data['encodedDataLength']),
            security_state=SecurityState.from_json(data['securityState']),
            headers_text=str(data['headersText']) if 'headersText' in data else None,
            request_headers=Headers.from_json(data['requestHeaders']) if 'requestHeaders' in data else None,
            request_headers_text=str(data['requestHeadersText']) if 'requestHeadersText' in data else None,
            remote_ip_address=str(data['remoteIPAddress']) if 'remoteIPAddress' in data else None,
            remote_port=int(data['remotePort']) if 'remotePort' in data else None,
            from_disk_cache=bool(data['fromDiskCache']) if 'fromDiskCache' in data else None,
            from_service_worker=bool(data['fromServiceWorker']) if 'fromServiceWorker' in data else None,
            from_prefetch_cache=bool(data['fromPrefetchCache']) if 'fromPrefetchCache' in data else None,
            from_early_hints=bool(data['fromEarlyHints']) if 'fromEarlyHints' in data else None,
            service_worker_router_info=ServiceWorkerRouterInfo.from_json(data['serviceWorkerRouterInfo']) if 'serviceWorkerRouterInfo' in data else None,
            timing=ResourceTiming.from_json(data['timing']) if 'timing' in data else None,
            service_worker_response_source=ServiceWorkerResponseSource.from_json(data['serviceWorkerResponseSource']) if 'serviceWorkerResponseSource' in data else None,
            response_time=TimeSinceEpoch.from_json(data['responseTime']) if 'responseTime' in data else None,
            cache_storage_cache_name=str(data['cacheStorageCacheName']) if 'cacheStorageCacheName' in data else None,
            protocol=str(data['protocol']) if 'protocol' in data else None,
            alternate_protocol_usage=AlternateProtocolUsage.from_json(data['alternateProtocolUsage']) if 'alternateProtocolUsage' in data else None,
            security_details=SecurityDetails.from_json(data['securityDetails']) if 'securityDetails' in data else None,
        )


@dataclass
class WebSocketRequest:
    headers: Headers

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['headers'] = headers.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketRequest:
        return cls(
            headers=Headers.from_json(data['headers']),
        )


@dataclass
class WebSocketResponse:
    status: int
    status_text: str
    headers: Headers
    headers_text: Optional[str] = None
    request_headers: Optional[Headers] = None
    request_headers_text: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['status'] = status
        d['statusText'] = status_text
        d['headers'] = headers.to_json()
        if self.headers_text is not None:
            d['headersText'] = self.headers_text
        if self.request_headers is not None:
            d['requestHeaders'] = self.request_headers.to_json()
        if self.request_headers_text is not None:
            d['requestHeadersText'] = self.request_headers_text
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketResponse:
        return cls(
            status=int(data['status']),
            status_text=str(data['statusText']),
            headers=Headers.from_json(data['headers']),
            headers_text=str(data['headersText']) if 'headersText' in data else None,
            request_headers=Headers.from_json(data['requestHeaders']) if 'requestHeaders' in data else None,
            request_headers_text=str(data['requestHeadersText']) if 'requestHeadersText' in data else None,
        )


@dataclass
class WebSocketFrame:
    opcode: float
    mask: bool
    payload_data: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['opcode'] = opcode
        d['mask'] = mask
        d['payloadData'] = payload_data
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketFrame:
        return cls(
            opcode=float(data['opcode']),
            mask=bool(data['mask']),
            payload_data=str(data['payloadData']),
        )


@dataclass
class CachedResource:
    url: str
    type: ResourceType
    body_size: float
    response: Optional[Response] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['type'] = type.to_json()
        d['bodySize'] = body_size
        if self.response is not None:
            d['response'] = self.response.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CachedResource:
        return cls(
            url=str(data['url']),
            type=ResourceType.from_json(data['type']),
            body_size=float(data['bodySize']),
            response=Response.from_json(data['response']) if 'response' in data else None,
        )


@dataclass
class Initiator:
    type: str
    stack: Optional[StackTrace] = None
    url: Optional[str] = None
    line_number: Optional[float] = None
    column_number: Optional[float] = None
    request_id: Optional[RequestId] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type
        if self.stack is not None:
            d['stack'] = self.stack.to_json()
        if self.url is not None:
            d['url'] = self.url
        if self.line_number is not None:
            d['lineNumber'] = self.line_number
        if self.column_number is not None:
            d['columnNumber'] = self.column_number
        if self.request_id is not None:
            d['requestId'] = self.request_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Initiator:
        return cls(
            type=str(data['type']),
            stack=StackTrace.from_json(data['stack']) if 'stack' in data else None,
            url=str(data['url']) if 'url' in data else None,
            line_number=float(data['lineNumber']) if 'lineNumber' in data else None,
            column_number=float(data['columnNumber']) if 'columnNumber' in data else None,
            request_id=RequestId.from_json(data['requestId']) if 'requestId' in data else None,
        )


@dataclass
class CookiePartitionKey:
    top_level_site: str
    has_cross_site_ancestor: bool

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['topLevelSite'] = top_level_site
        d['hasCrossSiteAncestor'] = has_cross_site_ancestor
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CookiePartitionKey:
        return cls(
            top_level_site=str(data['topLevelSite']),
            has_cross_site_ancestor=bool(data['hasCrossSiteAncestor']),
        )


@dataclass
class Cookie:
    name: str
    value: str
    domain: str
    path: str
    expires: float
    size: int
    http_only: bool
    secure: bool
    session: bool
    priority: CookiePriority
    source_scheme: CookieSourceScheme
    source_port: int
    same_site: Optional[CookieSameSite] = None
    partition_key: Optional[CookiePartitionKey] = None
    partition_key_opaque: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['value'] = value
        d['domain'] = domain
        d['path'] = path
        d['expires'] = expires
        d['size'] = size
        d['httpOnly'] = http_only
        d['secure'] = secure
        d['session'] = session
        d['priority'] = priority.to_json()
        d['sourceScheme'] = source_scheme.to_json()
        d['sourcePort'] = source_port
        if self.same_site is not None:
            d['sameSite'] = self.same_site.to_json()
        if self.partition_key is not None:
            d['partitionKey'] = self.partition_key.to_json()
        if self.partition_key_opaque is not None:
            d['partitionKeyOpaque'] = self.partition_key_opaque
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Cookie:
        return cls(
            name=str(data['name']),
            value=str(data['value']),
            domain=str(data['domain']),
            path=str(data['path']),
            expires=float(data['expires']),
            size=int(data['size']),
            http_only=bool(data['httpOnly']),
            secure=bool(data['secure']),
            session=bool(data['session']),
            priority=CookiePriority.from_json(data['priority']),
            source_scheme=CookieSourceScheme.from_json(data['sourceScheme']),
            source_port=int(data['sourcePort']),
            same_site=CookieSameSite.from_json(data['sameSite']) if 'sameSite' in data else None,
            partition_key=CookiePartitionKey.from_json(data['partitionKey']) if 'partitionKey' in data else None,
            partition_key_opaque=bool(data['partitionKeyOpaque']) if 'partitionKeyOpaque' in data else None,
        )


class SetCookieBlockedReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SetCookieBlockedReason:
        return cls(val)


class CookieBlockedReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CookieBlockedReason:
        return cls(val)


class CookieExemptionReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CookieExemptionReason:
        return cls(val)


@dataclass
class BlockedSetCookieWithReason:
    blocked_reasons: list[SetCookieBlockedReason]
    cookie_line: str
    cookie: Optional[Cookie] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['blockedReasons'] = [i.to_json() for i in blocked_reasons]
        d['cookieLine'] = cookie_line
        if self.cookie is not None:
            d['cookie'] = self.cookie.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BlockedSetCookieWithReason:
        return cls(
            blocked_reasons=[SetCookieBlockedReason.from_json(i) for i in data['blockedReasons']],
            cookie_line=str(data['cookieLine']),
            cookie=Cookie.from_json(data['cookie']) if 'cookie' in data else None,
        )


@dataclass
class ExemptedSetCookieWithReason:
    exemption_reason: CookieExemptionReason
    cookie_line: str
    cookie: Cookie

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['exemptionReason'] = exemption_reason.to_json()
        d['cookieLine'] = cookie_line
        d['cookie'] = cookie.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExemptedSetCookieWithReason:
        return cls(
            exemption_reason=CookieExemptionReason.from_json(data['exemptionReason']),
            cookie_line=str(data['cookieLine']),
            cookie=Cookie.from_json(data['cookie']),
        )


@dataclass
class AssociatedCookie:
    cookie: Cookie
    blocked_reasons: list[CookieBlockedReason]
    exemption_reason: Optional[CookieExemptionReason] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['cookie'] = cookie.to_json()
        d['blockedReasons'] = [i.to_json() for i in blocked_reasons]
        if self.exemption_reason is not None:
            d['exemptionReason'] = self.exemption_reason.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AssociatedCookie:
        return cls(
            cookie=Cookie.from_json(data['cookie']),
            blocked_reasons=[CookieBlockedReason.from_json(i) for i in data['blockedReasons']],
            exemption_reason=CookieExemptionReason.from_json(data['exemptionReason']) if 'exemptionReason' in data else None,
        )


@dataclass
class CookieParam:
    name: str
    value: str
    url: Optional[str] = None
    domain: Optional[str] = None
    path: Optional[str] = None
    secure: Optional[bool] = None
    http_only: Optional[bool] = None
    same_site: Optional[CookieSameSite] = None
    expires: Optional[TimeSinceEpoch] = None
    priority: Optional[CookiePriority] = None
    source_scheme: Optional[CookieSourceScheme] = None
    source_port: Optional[int] = None
    partition_key: Optional[CookiePartitionKey] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['value'] = value
        if self.url is not None:
            d['url'] = self.url
        if self.domain is not None:
            d['domain'] = self.domain
        if self.path is not None:
            d['path'] = self.path
        if self.secure is not None:
            d['secure'] = self.secure
        if self.http_only is not None:
            d['httpOnly'] = self.http_only
        if self.same_site is not None:
            d['sameSite'] = self.same_site.to_json()
        if self.expires is not None:
            d['expires'] = self.expires.to_json()
        if self.priority is not None:
            d['priority'] = self.priority.to_json()
        if self.source_scheme is not None:
            d['sourceScheme'] = self.source_scheme.to_json()
        if self.source_port is not None:
            d['sourcePort'] = self.source_port
        if self.partition_key is not None:
            d['partitionKey'] = self.partition_key.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CookieParam:
        return cls(
            name=str(data['name']),
            value=str(data['value']),
            url=str(data['url']) if 'url' in data else None,
            domain=str(data['domain']) if 'domain' in data else None,
            path=str(data['path']) if 'path' in data else None,
            secure=bool(data['secure']) if 'secure' in data else None,
            http_only=bool(data['httpOnly']) if 'httpOnly' in data else None,
            same_site=CookieSameSite.from_json(data['sameSite']) if 'sameSite' in data else None,
            expires=TimeSinceEpoch.from_json(data['expires']) if 'expires' in data else None,
            priority=CookiePriority.from_json(data['priority']) if 'priority' in data else None,
            source_scheme=CookieSourceScheme.from_json(data['sourceScheme']) if 'sourceScheme' in data else None,
            source_port=int(data['sourcePort']) if 'sourcePort' in data else None,
            partition_key=CookiePartitionKey.from_json(data['partitionKey']) if 'partitionKey' in data else None,
        )


@dataclass
class AuthChallenge:
    origin: str
    scheme: str
    realm: str
    source: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['origin'] = origin
        d['scheme'] = scheme
        d['realm'] = realm
        if self.source is not None:
            d['source'] = self.source
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AuthChallenge:
        return cls(
            origin=str(data['origin']),
            scheme=str(data['scheme']),
            realm=str(data['realm']),
            source=str(data['source']) if 'source' in data else None,
        )


@dataclass
class AuthChallengeResponse:
    response: str
    username: Optional[str] = None
    password: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['response'] = response
        if self.username is not None:
            d['username'] = self.username
        if self.password is not None:
            d['password'] = self.password
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AuthChallengeResponse:
        return cls(
            response=str(data['response']),
            username=str(data['username']) if 'username' in data else None,
            password=str(data['password']) if 'password' in data else None,
        )


class InterceptionStage(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> InterceptionStage:
        return cls(val)


@dataclass
class RequestPattern:
    url_pattern: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    interception_stage: Optional[InterceptionStage] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.url_pattern is not None:
            d['urlPattern'] = self.url_pattern
        if self.resource_type is not None:
            d['resourceType'] = self.resource_type.to_json()
        if self.interception_stage is not None:
            d['interceptionStage'] = self.interception_stage.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestPattern:
        return cls(
            url_pattern=str(data['urlPattern']) if 'urlPattern' in data else None,
            resource_type=ResourceType.from_json(data['resourceType']) if 'resourceType' in data else None,
            interception_stage=InterceptionStage.from_json(data['interceptionStage']) if 'interceptionStage' in data else None,
        )


@dataclass
class SignedExchangeSignature:
    label: str
    signature: str
    integrity: str
    validity_url: str
    date: int
    expires: int
    cert_url: Optional[str] = None
    cert_sha256: Optional[str] = None
    certificates: Optional[list[str]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['label'] = label
        d['signature'] = signature
        d['integrity'] = integrity
        d['validityUrl'] = validity_url
        d['date'] = date
        d['expires'] = expires
        if self.cert_url is not None:
            d['certUrl'] = self.cert_url
        if self.cert_sha256 is not None:
            d['certSha256'] = self.cert_sha256
        if self.certificates is not None:
            d['certificates'] = list(self.certificates)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SignedExchangeSignature:
        return cls(
            label=str(data['label']),
            signature=str(data['signature']),
            integrity=str(data['integrity']),
            validity_url=str(data['validityUrl']),
            date=int(data['date']),
            expires=int(data['expires']),
            cert_url=str(data['certUrl']) if 'certUrl' in data else None,
            cert_sha256=str(data['certSha256']) if 'certSha256' in data else None,
            certificates=[str(i) for i in data['certificates']] if 'certificates' in data else None,
        )


@dataclass
class SignedExchangeHeader:
    request_url: str
    response_code: int
    response_headers: Headers
    signatures: list[SignedExchangeSignature]
    header_integrity: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['requestUrl'] = request_url
        d['responseCode'] = response_code
        d['responseHeaders'] = response_headers.to_json()
        d['signatures'] = [i.to_json() for i in signatures]
        d['headerIntegrity'] = header_integrity
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SignedExchangeHeader:
        return cls(
            request_url=str(data['requestUrl']),
            response_code=int(data['responseCode']),
            response_headers=Headers.from_json(data['responseHeaders']),
            signatures=[SignedExchangeSignature.from_json(i) for i in data['signatures']],
            header_integrity=str(data['headerIntegrity']),
        )


class SignedExchangeErrorField(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SignedExchangeErrorField:
        return cls(val)


@dataclass
class SignedExchangeError:
    message: str
    signature_index: Optional[int] = None
    error_field: Optional[SignedExchangeErrorField] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['message'] = message
        if self.signature_index is not None:
            d['signatureIndex'] = self.signature_index
        if self.error_field is not None:
            d['errorField'] = self.error_field.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SignedExchangeError:
        return cls(
            message=str(data['message']),
            signature_index=int(data['signatureIndex']) if 'signatureIndex' in data else None,
            error_field=SignedExchangeErrorField.from_json(data['errorField']) if 'errorField' in data else None,
        )


@dataclass
class SignedExchangeInfo:
    outer_response: Response
    has_extra_info: bool
    header: Optional[SignedExchangeHeader] = None
    security_details: Optional[SecurityDetails] = None
    errors: Optional[list[SignedExchangeError]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['outerResponse'] = outer_response.to_json()
        d['hasExtraInfo'] = has_extra_info
        if self.header is not None:
            d['header'] = self.header.to_json()
        if self.security_details is not None:
            d['securityDetails'] = self.security_details.to_json()
        if self.errors is not None:
            d['errors'] = [i.to_json() for i in self.errors]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SignedExchangeInfo:
        return cls(
            outer_response=Response.from_json(data['outerResponse']),
            has_extra_info=bool(data['hasExtraInfo']),
            header=SignedExchangeHeader.from_json(data['header']) if 'header' in data else None,
            security_details=SecurityDetails.from_json(data['securityDetails']) if 'securityDetails' in data else None,
            errors=[SignedExchangeError.from_json(i) for i in data['errors']] if 'errors' in data else None,
        )


class ContentEncoding(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ContentEncoding:
        return cls(val)


@dataclass
class NetworkConditions:
    url_pattern: str
    latency: float
    download_throughput: float
    upload_throughput: float
    connection_type: Optional[ConnectionType] = None
    packet_loss: Optional[float] = None
    packet_queue_length: Optional[int] = None
    packet_reordering: Optional[bool] = None
    offline: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['urlPattern'] = url_pattern
        d['latency'] = latency
        d['downloadThroughput'] = download_throughput
        d['uploadThroughput'] = upload_throughput
        if self.connection_type is not None:
            d['connectionType'] = self.connection_type.to_json()
        if self.packet_loss is not None:
            d['packetLoss'] = self.packet_loss
        if self.packet_queue_length is not None:
            d['packetQueueLength'] = self.packet_queue_length
        if self.packet_reordering is not None:
            d['packetReordering'] = self.packet_reordering
        if self.offline is not None:
            d['offline'] = self.offline
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> NetworkConditions:
        return cls(
            url_pattern=str(data['urlPattern']),
            latency=float(data['latency']),
            download_throughput=float(data['downloadThroughput']),
            upload_throughput=float(data['uploadThroughput']),
            connection_type=ConnectionType.from_json(data['connectionType']) if 'connectionType' in data else None,
            packet_loss=float(data['packetLoss']) if 'packetLoss' in data else None,
            packet_queue_length=int(data['packetQueueLength']) if 'packetQueueLength' in data else None,
            packet_reordering=bool(data['packetReordering']) if 'packetReordering' in data else None,
            offline=bool(data['offline']) if 'offline' in data else None,
        )


@dataclass
class BlockPattern:
    url_pattern: str
    block: bool

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['urlPattern'] = url_pattern
        d['block'] = block
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BlockPattern:
        return cls(
            url_pattern=str(data['urlPattern']),
            block=bool(data['block']),
        )


class DirectSocketDnsQueryType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> DirectSocketDnsQueryType:
        return cls(val)


@dataclass
class DirectTCPSocketOptions:
    no_delay: bool
    keep_alive_delay: Optional[float] = None
    send_buffer_size: Optional[float] = None
    receive_buffer_size: Optional[float] = None
    dns_query_type: Optional[DirectSocketDnsQueryType] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['noDelay'] = no_delay
        if self.keep_alive_delay is not None:
            d['keepAliveDelay'] = self.keep_alive_delay
        if self.send_buffer_size is not None:
            d['sendBufferSize'] = self.send_buffer_size
        if self.receive_buffer_size is not None:
            d['receiveBufferSize'] = self.receive_buffer_size
        if self.dns_query_type is not None:
            d['dnsQueryType'] = self.dns_query_type.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketOptions:
        return cls(
            no_delay=bool(data['noDelay']),
            keep_alive_delay=float(data['keepAliveDelay']) if 'keepAliveDelay' in data else None,
            send_buffer_size=float(data['sendBufferSize']) if 'sendBufferSize' in data else None,
            receive_buffer_size=float(data['receiveBufferSize']) if 'receiveBufferSize' in data else None,
            dns_query_type=DirectSocketDnsQueryType.from_json(data['dnsQueryType']) if 'dnsQueryType' in data else None,
        )


@dataclass
class DirectUDPSocketOptions:
    remote_addr: Optional[str] = None
    remote_port: Optional[int] = None
    local_addr: Optional[str] = None
    local_port: Optional[int] = None
    dns_query_type: Optional[DirectSocketDnsQueryType] = None
    send_buffer_size: Optional[float] = None
    receive_buffer_size: Optional[float] = None
    multicast_loopback: Optional[bool] = None
    multicast_time_to_live: Optional[int] = None
    multicast_allow_address_sharing: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.remote_addr is not None:
            d['remoteAddr'] = self.remote_addr
        if self.remote_port is not None:
            d['remotePort'] = self.remote_port
        if self.local_addr is not None:
            d['localAddr'] = self.local_addr
        if self.local_port is not None:
            d['localPort'] = self.local_port
        if self.dns_query_type is not None:
            d['dnsQueryType'] = self.dns_query_type.to_json()
        if self.send_buffer_size is not None:
            d['sendBufferSize'] = self.send_buffer_size
        if self.receive_buffer_size is not None:
            d['receiveBufferSize'] = self.receive_buffer_size
        if self.multicast_loopback is not None:
            d['multicastLoopback'] = self.multicast_loopback
        if self.multicast_time_to_live is not None:
            d['multicastTimeToLive'] = self.multicast_time_to_live
        if self.multicast_allow_address_sharing is not None:
            d['multicastAllowAddressSharing'] = self.multicast_allow_address_sharing
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketOptions:
        return cls(
            remote_addr=str(data['remoteAddr']) if 'remoteAddr' in data else None,
            remote_port=int(data['remotePort']) if 'remotePort' in data else None,
            local_addr=str(data['localAddr']) if 'localAddr' in data else None,
            local_port=int(data['localPort']) if 'localPort' in data else None,
            dns_query_type=DirectSocketDnsQueryType.from_json(data['dnsQueryType']) if 'dnsQueryType' in data else None,
            send_buffer_size=float(data['sendBufferSize']) if 'sendBufferSize' in data else None,
            receive_buffer_size=float(data['receiveBufferSize']) if 'receiveBufferSize' in data else None,
            multicast_loopback=bool(data['multicastLoopback']) if 'multicastLoopback' in data else None,
            multicast_time_to_live=int(data['multicastTimeToLive']) if 'multicastTimeToLive' in data else None,
            multicast_allow_address_sharing=bool(data['multicastAllowAddressSharing']) if 'multicastAllowAddressSharing' in data else None,
        )


@dataclass
class DirectUDPMessage:
    data: str
    remote_addr: Optional[str] = None
    remote_port: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['data'] = data
        if self.remote_addr is not None:
            d['remoteAddr'] = self.remote_addr
        if self.remote_port is not None:
            d['remotePort'] = self.remote_port
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPMessage:
        return cls(
            data=str(data['data']),
            remote_addr=str(data['remoteAddr']) if 'remoteAddr' in data else None,
            remote_port=int(data['remotePort']) if 'remotePort' in data else None,
        )


class LocalNetworkAccessRequestPolicy(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> LocalNetworkAccessRequestPolicy:
        return cls(val)


class IPAddressSpace(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> IPAddressSpace:
        return cls(val)


@dataclass
class ConnectTiming:
    request_time: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['requestTime'] = request_time
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ConnectTiming:
        return cls(
            request_time=float(data['requestTime']),
        )


@dataclass
class ClientSecurityState:
    initiator_is_secure_context: bool
    initiator_ip_address_space: IPAddressSpace
    local_network_access_request_policy: LocalNetworkAccessRequestPolicy

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['initiatorIsSecureContext'] = initiator_is_secure_context
        d['initiatorIPAddressSpace'] = initiator_ip_address_space.to_json()
        d['localNetworkAccessRequestPolicy'] = local_network_access_request_policy.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ClientSecurityState:
        return cls(
            initiator_is_secure_context=bool(data['initiatorIsSecureContext']),
            initiator_ip_address_space=IPAddressSpace.from_json(data['initiatorIPAddressSpace']),
            local_network_access_request_policy=LocalNetworkAccessRequestPolicy.from_json(data['localNetworkAccessRequestPolicy']),
        )


@dataclass
class AdScriptIdentifier:
    script_id: ScriptId
    debugger_id: UniqueDebuggerId
    name: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['scriptId'] = script_id.to_json()
        d['debuggerId'] = debugger_id.to_json()
        d['name'] = name
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AdScriptIdentifier:
        return cls(
            script_id=ScriptId.from_json(data['scriptId']),
            debugger_id=UniqueDebuggerId.from_json(data['debuggerId']),
            name=str(data['name']),
        )


@dataclass
class AdAncestry:
    ancestry_chain: list[AdScriptIdentifier]
    root_script_filterlist_rule: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['ancestryChain'] = [i.to_json() for i in ancestry_chain]
        if self.root_script_filterlist_rule is not None:
            d['rootScriptFilterlistRule'] = self.root_script_filterlist_rule
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AdAncestry:
        return cls(
            ancestry_chain=[AdScriptIdentifier.from_json(i) for i in data['ancestryChain']],
            root_script_filterlist_rule=str(data['rootScriptFilterlistRule']) if 'rootScriptFilterlistRule' in data else None,
        )


@dataclass
class AdProvenance:
    filterlist_rule: Optional[str] = None
    ad_script_ancestry: Optional[AdAncestry] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.filterlist_rule is not None:
            d['filterlistRule'] = self.filterlist_rule
        if self.ad_script_ancestry is not None:
            d['adScriptAncestry'] = self.ad_script_ancestry.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AdProvenance:
        return cls(
            filterlist_rule=str(data['filterlistRule']) if 'filterlistRule' in data else None,
            ad_script_ancestry=AdAncestry.from_json(data['adScriptAncestry']) if 'adScriptAncestry' in data else None,
        )


class CrossOriginOpenerPolicyValue(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CrossOriginOpenerPolicyValue:
        return cls(val)


@dataclass
class CrossOriginOpenerPolicyStatus:
    value: CrossOriginOpenerPolicyValue
    report_only_value: CrossOriginOpenerPolicyValue
    reporting_endpoint: Optional[str] = None
    report_only_reporting_endpoint: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['value'] = value.to_json()
        d['reportOnlyValue'] = report_only_value.to_json()
        if self.reporting_endpoint is not None:
            d['reportingEndpoint'] = self.reporting_endpoint
        if self.report_only_reporting_endpoint is not None:
            d['reportOnlyReportingEndpoint'] = self.report_only_reporting_endpoint
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CrossOriginOpenerPolicyStatus:
        return cls(
            value=CrossOriginOpenerPolicyValue.from_json(data['value']),
            report_only_value=CrossOriginOpenerPolicyValue.from_json(data['reportOnlyValue']),
            reporting_endpoint=str(data['reportingEndpoint']) if 'reportingEndpoint' in data else None,
            report_only_reporting_endpoint=str(data['reportOnlyReportingEndpoint']) if 'reportOnlyReportingEndpoint' in data else None,
        )


class CrossOriginEmbedderPolicyValue(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CrossOriginEmbedderPolicyValue:
        return cls(val)


@dataclass
class CrossOriginEmbedderPolicyStatus:
    value: CrossOriginEmbedderPolicyValue
    report_only_value: CrossOriginEmbedderPolicyValue
    reporting_endpoint: Optional[str] = None
    report_only_reporting_endpoint: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['value'] = value.to_json()
        d['reportOnlyValue'] = report_only_value.to_json()
        if self.reporting_endpoint is not None:
            d['reportingEndpoint'] = self.reporting_endpoint
        if self.report_only_reporting_endpoint is not None:
            d['reportOnlyReportingEndpoint'] = self.report_only_reporting_endpoint
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CrossOriginEmbedderPolicyStatus:
        return cls(
            value=CrossOriginEmbedderPolicyValue.from_json(data['value']),
            report_only_value=CrossOriginEmbedderPolicyValue.from_json(data['reportOnlyValue']),
            reporting_endpoint=str(data['reportingEndpoint']) if 'reportingEndpoint' in data else None,
            report_only_reporting_endpoint=str(data['reportOnlyReportingEndpoint']) if 'reportOnlyReportingEndpoint' in data else None,
        )


class ContentSecurityPolicySource(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ContentSecurityPolicySource:
        return cls(val)


@dataclass
class ContentSecurityPolicyStatus:
    effective_directives: str
    is_enforced: bool
    source: ContentSecurityPolicySource

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['effectiveDirectives'] = effective_directives
        d['isEnforced'] = is_enforced
        d['source'] = source.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ContentSecurityPolicyStatus:
        return cls(
            effective_directives=str(data['effectiveDirectives']),
            is_enforced=bool(data['isEnforced']),
            source=ContentSecurityPolicySource.from_json(data['source']),
        )


@dataclass
class SecurityIsolationStatus:
    coop: Optional[CrossOriginOpenerPolicyStatus] = None
    coep: Optional[CrossOriginEmbedderPolicyStatus] = None
    csp: Optional[list[ContentSecurityPolicyStatus]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.coop is not None:
            d['coop'] = self.coop.to_json()
        if self.coep is not None:
            d['coep'] = self.coep.to_json()
        if self.csp is not None:
            d['csp'] = [i.to_json() for i in self.csp]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SecurityIsolationStatus:
        return cls(
            coop=CrossOriginOpenerPolicyStatus.from_json(data['coop']) if 'coop' in data else None,
            coep=CrossOriginEmbedderPolicyStatus.from_json(data['coep']) if 'coep' in data else None,
            csp=[ContentSecurityPolicyStatus.from_json(i) for i in data['csp']] if 'csp' in data else None,
        )


class ReportStatus(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ReportStatus:
        return cls(val)


class ReportId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ReportId:
        return cls(val)


@dataclass
class ReportingApiReport:
    id: ReportId
    initiator_url: str
    destination: str
    type: str
    timestamp: TimeSinceEpoch
    depth: int
    completed_attempts: int
    body: T_JSON_DICT
    status: ReportStatus

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['id'] = id.to_json()
        d['initiatorUrl'] = initiator_url
        d['destination'] = destination
        d['type'] = type
        d['timestamp'] = timestamp.to_json()
        d['depth'] = depth
        d['completedAttempts'] = completed_attempts
        d['body'] = body
        d['status'] = status.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ReportingApiReport:
        return cls(
            id=ReportId.from_json(data['id']),
            initiator_url=str(data['initiatorUrl']),
            destination=str(data['destination']),
            type=str(data['type']),
            timestamp=TimeSinceEpoch.from_json(data['timestamp']),
            depth=int(data['depth']),
            completed_attempts=int(data['completedAttempts']),
            body=data['body'],
            status=ReportStatus.from_json(data['status']),
        )


@dataclass
class ReportingApiEndpoint:
    url: str
    group_name: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['groupName'] = group_name
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ReportingApiEndpoint:
        return cls(
            url=str(data['url']),
            group_name=str(data['groupName']),
        )


@dataclass
class DeviceBoundSessionKey:
    site: str
    id: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['site'] = site
        d['id'] = id
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionKey:
        return cls(
            site=str(data['site']),
            id=str(data['id']),
        )


@dataclass
class DeviceBoundSessionWithUsage:
    session_key: DeviceBoundSessionKey
    usage: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['sessionKey'] = session_key.to_json()
        d['usage'] = usage
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionWithUsage:
        return cls(
            session_key=DeviceBoundSessionKey.from_json(data['sessionKey']),
            usage=str(data['usage']),
        )


@dataclass
class DeviceBoundSessionCookieCraving:
    name: str
    domain: str
    path: str
    secure: bool
    http_only: bool
    same_site: Optional[CookieSameSite] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['domain'] = domain
        d['path'] = path
        d['secure'] = secure
        d['httpOnly'] = http_only
        if self.same_site is not None:
            d['sameSite'] = self.same_site.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionCookieCraving:
        return cls(
            name=str(data['name']),
            domain=str(data['domain']),
            path=str(data['path']),
            secure=bool(data['secure']),
            http_only=bool(data['httpOnly']),
            same_site=CookieSameSite.from_json(data['sameSite']) if 'sameSite' in data else None,
        )


@dataclass
class DeviceBoundSessionUrlRule:
    rule_type: str
    host_pattern: str
    path_prefix: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['ruleType'] = rule_type
        d['hostPattern'] = host_pattern
        d['pathPrefix'] = path_prefix
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionUrlRule:
        return cls(
            rule_type=str(data['ruleType']),
            host_pattern=str(data['hostPattern']),
            path_prefix=str(data['pathPrefix']),
        )


@dataclass
class DeviceBoundSessionInclusionRules:
    origin: str
    include_site: bool
    url_rules: list[DeviceBoundSessionUrlRule]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['origin'] = origin
        d['includeSite'] = include_site
        d['urlRules'] = [i.to_json() for i in url_rules]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionInclusionRules:
        return cls(
            origin=str(data['origin']),
            include_site=bool(data['includeSite']),
            url_rules=[DeviceBoundSessionUrlRule.from_json(i) for i in data['urlRules']],
        )


@dataclass
class DeviceBoundSession:
    key: DeviceBoundSessionKey
    refresh_url: str
    inclusion_rules: DeviceBoundSessionInclusionRules
    cookie_cravings: list[DeviceBoundSessionCookieCraving]
    expiry_date: TimeSinceEpoch
    allowed_refresh_initiators: list[str]
    cached_challenge: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['key'] = key.to_json()
        d['refreshUrl'] = refresh_url
        d['inclusionRules'] = inclusion_rules.to_json()
        d['cookieCravings'] = [i.to_json() for i in cookie_cravings]
        d['expiryDate'] = expiry_date.to_json()
        d['allowedRefreshInitiators'] = list(allowed_refresh_initiators)
        if self.cached_challenge is not None:
            d['cachedChallenge'] = self.cached_challenge
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSession:
        return cls(
            key=DeviceBoundSessionKey.from_json(data['key']),
            refresh_url=str(data['refreshUrl']),
            inclusion_rules=DeviceBoundSessionInclusionRules.from_json(data['inclusionRules']),
            cookie_cravings=[DeviceBoundSessionCookieCraving.from_json(i) for i in data['cookieCravings']],
            expiry_date=TimeSinceEpoch.from_json(data['expiryDate']),
            allowed_refresh_initiators=[str(i) for i in data['allowedRefreshInitiators']],
            cached_challenge=str(data['cachedChallenge']) if 'cachedChallenge' in data else None,
        )


class DeviceBoundSessionEventId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> DeviceBoundSessionEventId:
        return cls(val)


class DeviceBoundSessionFetchResult(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> DeviceBoundSessionFetchResult:
        return cls(val)


@dataclass
class DeviceBoundSessionFailedRequest:
    request_url: str
    net_error: Optional[str] = None
    response_error: Optional[int] = None
    response_error_body: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['requestUrl'] = request_url
        if self.net_error is not None:
            d['netError'] = self.net_error
        if self.response_error is not None:
            d['responseError'] = self.response_error
        if self.response_error_body is not None:
            d['responseErrorBody'] = self.response_error_body
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionFailedRequest:
        return cls(
            request_url=str(data['requestUrl']),
            net_error=str(data['netError']) if 'netError' in data else None,
            response_error=int(data['responseError']) if 'responseError' in data else None,
            response_error_body=str(data['responseErrorBody']) if 'responseErrorBody' in data else None,
        )


@dataclass
class CreationEventDetails:
    fetch_result: DeviceBoundSessionFetchResult
    new_session: Optional[DeviceBoundSession] = None
    failed_request: Optional[DeviceBoundSessionFailedRequest] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['fetchResult'] = fetch_result.to_json()
        if self.new_session is not None:
            d['newSession'] = self.new_session.to_json()
        if self.failed_request is not None:
            d['failedRequest'] = self.failed_request.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CreationEventDetails:
        return cls(
            fetch_result=DeviceBoundSessionFetchResult.from_json(data['fetchResult']),
            new_session=DeviceBoundSession.from_json(data['newSession']) if 'newSession' in data else None,
            failed_request=DeviceBoundSessionFailedRequest.from_json(data['failedRequest']) if 'failedRequest' in data else None,
        )


@dataclass
class RefreshEventDetails:
    refresh_result: str
    was_fully_proactive_refresh: bool
    fetch_result: Optional[DeviceBoundSessionFetchResult] = None
    new_session: Optional[DeviceBoundSession] = None
    failed_request: Optional[DeviceBoundSessionFailedRequest] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['refreshResult'] = refresh_result
        d['wasFullyProactiveRefresh'] = was_fully_proactive_refresh
        if self.fetch_result is not None:
            d['fetchResult'] = self.fetch_result.to_json()
        if self.new_session is not None:
            d['newSession'] = self.new_session.to_json()
        if self.failed_request is not None:
            d['failedRequest'] = self.failed_request.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RefreshEventDetails:
        return cls(
            refresh_result=str(data['refreshResult']),
            was_fully_proactive_refresh=bool(data['wasFullyProactiveRefresh']),
            fetch_result=DeviceBoundSessionFetchResult.from_json(data['fetchResult']) if 'fetchResult' in data else None,
            new_session=DeviceBoundSession.from_json(data['newSession']) if 'newSession' in data else None,
            failed_request=DeviceBoundSessionFailedRequest.from_json(data['failedRequest']) if 'failedRequest' in data else None,
        )


@dataclass
class TerminationEventDetails:
    deletion_reason: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['deletionReason'] = deletion_reason
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TerminationEventDetails:
        return cls(
            deletion_reason=str(data['deletionReason']),
        )


@dataclass
class ChallengeEventDetails:
    challenge_result: str
    challenge: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['challengeResult'] = challenge_result
        d['challenge'] = challenge
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ChallengeEventDetails:
        return cls(
            challenge_result=str(data['challengeResult']),
            challenge=str(data['challenge']),
        )


@dataclass
class LoadNetworkResourcePageResult:
    success: bool
    net_error: Optional[float] = None
    net_error_name: Optional[str] = None
    http_status_code: Optional[float] = None
    stream: Optional[StreamHandle] = None
    headers: Optional[Headers] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['success'] = success
        if self.net_error is not None:
            d['netError'] = self.net_error
        if self.net_error_name is not None:
            d['netErrorName'] = self.net_error_name
        if self.http_status_code is not None:
            d['httpStatusCode'] = self.http_status_code
        if self.stream is not None:
            d['stream'] = self.stream.to_json()
        if self.headers is not None:
            d['headers'] = self.headers.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadNetworkResourcePageResult:
        return cls(
            success=bool(data['success']),
            net_error=float(data['netError']) if 'netError' in data else None,
            net_error_name=str(data['netErrorName']) if 'netErrorName' in data else None,
            http_status_code=float(data['httpStatusCode']) if 'httpStatusCode' in data else None,
            stream=StreamHandle.from_json(data['stream']) if 'stream' in data else None,
            headers=Headers.from_json(data['headers']) if 'headers' in data else None,
        )


@dataclass
class LoadNetworkResourceOptions:
    disable_cache: bool
    include_credentials: bool

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['disableCache'] = disable_cache
        d['includeCredentials'] = include_credentials
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadNetworkResourceOptions:
        return cls(
            disable_cache=bool(data['disableCache']),
            include_credentials=bool(data['includeCredentials']),
        )


def set_accepted_encodings(encodings: list[ContentEncoding]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['encodings'] = [i.to_json() for i in encodings]
    cmd: T_JSON_DICT = {"method": "Network.setAcceptedEncodings", "params": params}
    return cmd, None


def clear_accepted_encodings_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.clearAcceptedEncodingsOverride", "params": params}
    return cmd, None


@dataclass
class CanClearBrowserCacheResult:
    result: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CanClearBrowserCacheResult:
        return cls(
            result=bool(data['result']),
        )


def can_clear_browser_cache() -> tuple[T_JSON_DICT, type[CanClearBrowserCacheResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.canClearBrowserCache", "params": params}
    return cmd, CanClearBrowserCacheResult


@dataclass
class CanClearBrowserCookiesResult:
    result: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CanClearBrowserCookiesResult:
        return cls(
            result=bool(data['result']),
        )


def can_clear_browser_cookies() -> tuple[T_JSON_DICT, type[CanClearBrowserCookiesResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.canClearBrowserCookies", "params": params}
    return cmd, CanClearBrowserCookiesResult


@dataclass
class CanEmulateNetworkConditionsResult:
    result: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CanEmulateNetworkConditionsResult:
        return cls(
            result=bool(data['result']),
        )


def can_emulate_network_conditions() -> tuple[T_JSON_DICT, type[CanEmulateNetworkConditionsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.canEmulateNetworkConditions", "params": params}
    return cmd, CanEmulateNetworkConditionsResult


def clear_browser_cache() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.clearBrowserCache", "params": params}
    return cmd, None


def clear_browser_cookies() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.clearBrowserCookies", "params": params}
    return cmd, None


def continue_intercepted_request(interception_id: InterceptionId, error_reason: Optional[ErrorReason] = None, raw_response: Optional[str] = None, url: Optional[str] = None, method: Optional[str] = None, post_data: Optional[str] = None, headers: Optional[Headers] = None, auth_challenge_response: Optional[AuthChallengeResponse] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['interceptionId'] = interception_id.to_json()
    if error_reason is not None:
        params['errorReason'] = error_reason.to_json()
    if raw_response is not None:
        params['rawResponse'] = raw_response
    if url is not None:
        params['url'] = url
    if method is not None:
        params['method'] = method
    if post_data is not None:
        params['postData'] = post_data
    if headers is not None:
        params['headers'] = headers.to_json()
    if auth_challenge_response is not None:
        params['authChallengeResponse'] = auth_challenge_response.to_json()
    cmd: T_JSON_DICT = {"method": "Network.continueInterceptedRequest", "params": params}
    return cmd, None


def delete_cookies(name: str, url: Optional[str] = None, domain: Optional[str] = None, path: Optional[str] = None, partition_key: Optional[CookiePartitionKey] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['name'] = name
    if url is not None:
        params['url'] = url
    if domain is not None:
        params['domain'] = domain
    if path is not None:
        params['path'] = path
    if partition_key is not None:
        params['partitionKey'] = partition_key.to_json()
    cmd: T_JSON_DICT = {"method": "Network.deleteCookies", "params": params}
    return cmd, None


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.disable", "params": params}
    return cmd, None


def emulate_network_conditions(offline: bool, latency: float, download_throughput: float, upload_throughput: float, connection_type: Optional[ConnectionType] = None, packet_loss: Optional[float] = None, packet_queue_length: Optional[int] = None, packet_reordering: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['offline'] = offline
    params['latency'] = latency
    params['downloadThroughput'] = download_throughput
    params['uploadThroughput'] = upload_throughput
    if connection_type is not None:
        params['connectionType'] = connection_type.to_json()
    if packet_loss is not None:
        params['packetLoss'] = packet_loss
    if packet_queue_length is not None:
        params['packetQueueLength'] = packet_queue_length
    if packet_reordering is not None:
        params['packetReordering'] = packet_reordering
    cmd: T_JSON_DICT = {"method": "Network.emulateNetworkConditions", "params": params}
    return cmd, None


@dataclass
class EmulateNetworkConditionsByRuleResult:
    rule_ids: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> EmulateNetworkConditionsByRuleResult:
        return cls(
            rule_ids=[str(i) for i in data['ruleIds']],
        )


def emulate_network_conditions_by_rule(matched_network_conditions: list[NetworkConditions], offline: Optional[bool] = None, emulate_offline_service_worker: Optional[bool] = None) -> tuple[T_JSON_DICT, type[EmulateNetworkConditionsByRuleResult]]:
    params: T_JSON_DICT = {}
    params['matchedNetworkConditions'] = [i.to_json() for i in matched_network_conditions]
    if offline is not None:
        params['offline'] = offline
    if emulate_offline_service_worker is not None:
        params['emulateOfflineServiceWorker'] = emulate_offline_service_worker
    cmd: T_JSON_DICT = {"method": "Network.emulateNetworkConditionsByRule", "params": params}
    return cmd, EmulateNetworkConditionsByRuleResult


def override_network_state(offline: bool, latency: float, download_throughput: float, upload_throughput: float, connection_type: Optional[ConnectionType] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['offline'] = offline
    params['latency'] = latency
    params['downloadThroughput'] = download_throughput
    params['uploadThroughput'] = upload_throughput
    if connection_type is not None:
        params['connectionType'] = connection_type.to_json()
    cmd: T_JSON_DICT = {"method": "Network.overrideNetworkState", "params": params}
    return cmd, None


def enable(max_total_buffer_size: Optional[int] = None, max_resource_buffer_size: Optional[int] = None, max_post_data_size: Optional[int] = None, report_direct_socket_traffic: Optional[bool] = None, enable_durable_messages: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if max_total_buffer_size is not None:
        params['maxTotalBufferSize'] = max_total_buffer_size
    if max_resource_buffer_size is not None:
        params['maxResourceBufferSize'] = max_resource_buffer_size
    if max_post_data_size is not None:
        params['maxPostDataSize'] = max_post_data_size
    if report_direct_socket_traffic is not None:
        params['reportDirectSocketTraffic'] = report_direct_socket_traffic
    if enable_durable_messages is not None:
        params['enableDurableMessages'] = enable_durable_messages
    cmd: T_JSON_DICT = {"method": "Network.enable", "params": params}
    return cmd, None


def configure_durable_messages(max_total_buffer_size: Optional[int] = None, max_resource_buffer_size: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if max_total_buffer_size is not None:
        params['maxTotalBufferSize'] = max_total_buffer_size
    if max_resource_buffer_size is not None:
        params['maxResourceBufferSize'] = max_resource_buffer_size
    cmd: T_JSON_DICT = {"method": "Network.configureDurableMessages", "params": params}
    return cmd, None


@dataclass
class GetAllCookiesResult:
    cookies: list[Cookie]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAllCookiesResult:
        return cls(
            cookies=[Cookie.from_json(i) for i in data['cookies']],
        )


def get_all_cookies() -> tuple[T_JSON_DICT, type[GetAllCookiesResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Network.getAllCookies", "params": params}
    return cmd, GetAllCookiesResult


@dataclass
class GetCertificateResult:
    table_names: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetCertificateResult:
        return cls(
            table_names=[str(i) for i in data['tableNames']],
        )


def get_certificate(origin: str) -> tuple[T_JSON_DICT, type[GetCertificateResult]]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Network.getCertificate", "params": params}
    return cmd, GetCertificateResult


@dataclass
class GetCookiesResult:
    cookies: list[Cookie]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetCookiesResult:
        return cls(
            cookies=[Cookie.from_json(i) for i in data['cookies']],
        )


def get_cookies(urls: Optional[list[str]] = None) -> tuple[T_JSON_DICT, type[GetCookiesResult]]:
    params: T_JSON_DICT = {}
    if urls is not None:
        params['urls'] = list(urls)
    cmd: T_JSON_DICT = {"method": "Network.getCookies", "params": params}
    return cmd, GetCookiesResult


@dataclass
class GetResponseBodyResult:
    body: str
    base64_encoded: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetResponseBodyResult:
        return cls(
            body=str(data['body']),
            base64_encoded=bool(data['base64Encoded']),
        )


def get_response_body(request_id: RequestId) -> tuple[T_JSON_DICT, type[GetResponseBodyResult]]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.getResponseBody", "params": params}
    return cmd, GetResponseBodyResult


@dataclass
class GetRequestPostDataResult:
    post_data: str
    base64_encoded: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetRequestPostDataResult:
        return cls(
            post_data=str(data['postData']),
            base64_encoded=bool(data['base64Encoded']),
        )


def get_request_post_data(request_id: RequestId) -> tuple[T_JSON_DICT, type[GetRequestPostDataResult]]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.getRequestPostData", "params": params}
    return cmd, GetRequestPostDataResult


@dataclass
class GetResponseBodyForInterceptionResult:
    body: str
    base64_encoded: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetResponseBodyForInterceptionResult:
        return cls(
            body=str(data['body']),
            base64_encoded=bool(data['base64Encoded']),
        )


def get_response_body_for_interception(interception_id: InterceptionId) -> tuple[T_JSON_DICT, type[GetResponseBodyForInterceptionResult]]:
    params: T_JSON_DICT = {}
    params['interceptionId'] = interception_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.getResponseBodyForInterception", "params": params}
    return cmd, GetResponseBodyForInterceptionResult


@dataclass
class TakeResponseBodyForInterceptionAsStreamResult:
    stream: StreamHandle

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TakeResponseBodyForInterceptionAsStreamResult:
        return cls(
            stream=StreamHandle.from_json(data['stream']),
        )


def take_response_body_for_interception_as_stream(interception_id: InterceptionId) -> tuple[T_JSON_DICT, type[TakeResponseBodyForInterceptionAsStreamResult]]:
    params: T_JSON_DICT = {}
    params['interceptionId'] = interception_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.takeResponseBodyForInterceptionAsStream", "params": params}
    return cmd, TakeResponseBodyForInterceptionAsStreamResult


def replay_xhr(request_id: RequestId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.replayXHR", "params": params}
    return cmd, None


@dataclass
class SearchInResponseBodyResult:
    result: list[SearchMatch]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SearchInResponseBodyResult:
        return cls(
            result=[SearchMatch.from_json(i) for i in data['result']],
        )


def search_in_response_body(request_id: RequestId, query: str, case_sensitive: Optional[bool] = None, is_regex: Optional[bool] = None) -> tuple[T_JSON_DICT, type[SearchInResponseBodyResult]]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    params['query'] = query
    if case_sensitive is not None:
        params['caseSensitive'] = case_sensitive
    if is_regex is not None:
        params['isRegex'] = is_regex
    cmd: T_JSON_DICT = {"method": "Network.searchInResponseBody", "params": params}
    return cmd, SearchInResponseBodyResult


def set_blocked_ur_ls(url_patterns: Optional[list[BlockPattern]] = None, urls: Optional[list[str]] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if url_patterns is not None:
        params['urlPatterns'] = [i.to_json() for i in url_patterns]
    if urls is not None:
        params['urls'] = list(urls)
    cmd: T_JSON_DICT = {"method": "Network.setBlockedURLs", "params": params}
    return cmd, None


def set_bypass_service_worker(bypass: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['bypass'] = bypass
    cmd: T_JSON_DICT = {"method": "Network.setBypassServiceWorker", "params": params}
    return cmd, None


def set_cache_disabled(cache_disabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['cacheDisabled'] = cache_disabled
    cmd: T_JSON_DICT = {"method": "Network.setCacheDisabled", "params": params}
    return cmd, None


@dataclass
class SetCookieResult:
    success: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SetCookieResult:
        return cls(
            success=bool(data['success']),
        )


def set_cookie(name: str, value: str, url: Optional[str] = None, domain: Optional[str] = None, path: Optional[str] = None, secure: Optional[bool] = None, http_only: Optional[bool] = None, same_site: Optional[CookieSameSite] = None, expires: Optional[TimeSinceEpoch] = None, priority: Optional[CookiePriority] = None, source_scheme: Optional[CookieSourceScheme] = None, source_port: Optional[int] = None, partition_key: Optional[CookiePartitionKey] = None) -> tuple[T_JSON_DICT, type[SetCookieResult]]:
    params: T_JSON_DICT = {}
    params['name'] = name
    params['value'] = value
    if url is not None:
        params['url'] = url
    if domain is not None:
        params['domain'] = domain
    if path is not None:
        params['path'] = path
    if secure is not None:
        params['secure'] = secure
    if http_only is not None:
        params['httpOnly'] = http_only
    if same_site is not None:
        params['sameSite'] = same_site.to_json()
    if expires is not None:
        params['expires'] = expires.to_json()
    if priority is not None:
        params['priority'] = priority.to_json()
    if source_scheme is not None:
        params['sourceScheme'] = source_scheme.to_json()
    if source_port is not None:
        params['sourcePort'] = source_port
    if partition_key is not None:
        params['partitionKey'] = partition_key.to_json()
    cmd: T_JSON_DICT = {"method": "Network.setCookie", "params": params}
    return cmd, SetCookieResult


def set_cookies(cookies: list[CookieParam]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['cookies'] = [i.to_json() for i in cookies]
    cmd: T_JSON_DICT = {"method": "Network.setCookies", "params": params}
    return cmd, None


def set_extra_http_headers(headers: Headers) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['headers'] = headers.to_json()
    cmd: T_JSON_DICT = {"method": "Network.setExtraHTTPHeaders", "params": params}
    return cmd, None


def set_attach_debug_stack(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Network.setAttachDebugStack", "params": params}
    return cmd, None


def set_request_interception(patterns: list[RequestPattern]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['patterns'] = [i.to_json() for i in patterns]
    cmd: T_JSON_DICT = {"method": "Network.setRequestInterception", "params": params}
    return cmd, None


def set_user_agent_override(user_agent: str, accept_language: Optional[str] = None, platform: Optional[str] = None, user_agent_metadata: Optional[UserAgentMetadata] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['userAgent'] = user_agent
    if accept_language is not None:
        params['acceptLanguage'] = accept_language
    if platform is not None:
        params['platform'] = platform
    if user_agent_metadata is not None:
        params['userAgentMetadata'] = user_agent_metadata.to_json()
    cmd: T_JSON_DICT = {"method": "Network.setUserAgentOverride", "params": params}
    return cmd, None


@dataclass
class StreamResourceContentResult:
    buffered_data: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StreamResourceContentResult:
        return cls(
            buffered_data=str(data['bufferedData']),
        )


def stream_resource_content(request_id: RequestId) -> tuple[T_JSON_DICT, type[StreamResourceContentResult]]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.streamResourceContent", "params": params}
    return cmd, StreamResourceContentResult


@dataclass
class GetSecurityIsolationStatusResult:
    status: SecurityIsolationStatus

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetSecurityIsolationStatusResult:
        return cls(
            status=SecurityIsolationStatus.from_json(data['status']),
        )


def get_security_isolation_status(frame_id: Optional[FrameId] = None) -> tuple[T_JSON_DICT, type[GetSecurityIsolationStatusResult]]:
    params: T_JSON_DICT = {}
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.getSecurityIsolationStatus", "params": params}
    return cmd, GetSecurityIsolationStatusResult


def enable_reporting_api(enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "Network.enableReportingApi", "params": params}
    return cmd, None


def enable_device_bound_sessions(enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "Network.enableDeviceBoundSessions", "params": params}
    return cmd, None


@dataclass
class FetchSchemefulSiteResult:
    schemeful_site: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FetchSchemefulSiteResult:
        return cls(
            schemeful_site=str(data['schemefulSite']),
        )


def fetch_schemeful_site(origin: str) -> tuple[T_JSON_DICT, type[FetchSchemefulSiteResult]]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Network.fetchSchemefulSite", "params": params}
    return cmd, FetchSchemefulSiteResult


@dataclass
class LoadNetworkResourceResult:
    resource: LoadNetworkResourcePageResult

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadNetworkResourceResult:
        return cls(
            resource=LoadNetworkResourcePageResult.from_json(data['resource']),
        )


def load_network_resource(url: str, options: LoadNetworkResourceOptions, frame_id: Optional[FrameId] = None) -> tuple[T_JSON_DICT, type[LoadNetworkResourceResult]]:
    params: T_JSON_DICT = {}
    params['url'] = url
    params['options'] = options.to_json()
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Network.loadNetworkResource", "params": params}
    return cmd, LoadNetworkResourceResult


def set_cookie_controls(enable_third_party_cookie_restriction: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enableThirdPartyCookieRestriction'] = enable_third_party_cookie_restriction
    cmd: T_JSON_DICT = {"method": "Network.setCookieControls", "params": params}
    return cmd, None


@dataclass
class DataReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.dataReceived")
    request_id: RequestId
    timestamp: MonotonicTime
    data_length: int
    encoded_data_length: int
    data: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DataReceived:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            data_length=int(data['dataLength']),
            encoded_data_length=int(data['encodedDataLength']),
            data=str(data['data']) if 'data' in data else None,
        )


@dataclass
class EventSourceMessageReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.eventSourceMessageReceived")
    request_id: RequestId
    timestamp: MonotonicTime
    event_name: str
    event_id: str
    data: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> EventSourceMessageReceived:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            event_name=str(data['eventName']),
            event_id=str(data['eventId']),
            data=str(data['data']),
        )


@dataclass
class LoadingFailed:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.loadingFailed")
    request_id: RequestId
    timestamp: MonotonicTime
    type: ResourceType
    error_text: str
    canceled: Optional[bool] = None
    blocked_reason: Optional[BlockedReason] = None
    cors_error_status: Optional[CorsErrorStatus] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadingFailed:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            type=ResourceType.from_json(data['type']),
            error_text=str(data['errorText']),
            canceled=bool(data['canceled']) if 'canceled' in data else None,
            blocked_reason=BlockedReason.from_json(data['blockedReason']) if 'blockedReason' in data else None,
            cors_error_status=CorsErrorStatus.from_json(data['corsErrorStatus']) if 'corsErrorStatus' in data else None,
        )


@dataclass
class LoadingFinished:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.loadingFinished")
    request_id: RequestId
    timestamp: MonotonicTime
    encoded_data_length: float

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadingFinished:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            encoded_data_length=float(data['encodedDataLength']),
        )


@dataclass
class RequestIntercepted:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.requestIntercepted")
    interception_id: InterceptionId
    request: Request
    frame_id: FrameId
    resource_type: ResourceType
    is_navigation_request: bool
    is_download: Optional[bool] = None
    redirect_url: Optional[str] = None
    auth_challenge: Optional[AuthChallenge] = None
    response_error_reason: Optional[ErrorReason] = None
    response_status_code: Optional[int] = None
    response_headers: Optional[Headers] = None
    request_id: Optional[RequestId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestIntercepted:
        return cls(
            interception_id=InterceptionId.from_json(data['interceptionId']),
            request=Request.from_json(data['request']),
            frame_id=FrameId.from_json(data['frameId']),
            resource_type=ResourceType.from_json(data['resourceType']),
            is_navigation_request=bool(data['isNavigationRequest']),
            is_download=bool(data['isDownload']) if 'isDownload' in data else None,
            redirect_url=str(data['redirectUrl']) if 'redirectUrl' in data else None,
            auth_challenge=AuthChallenge.from_json(data['authChallenge']) if 'authChallenge' in data else None,
            response_error_reason=ErrorReason.from_json(data['responseErrorReason']) if 'responseErrorReason' in data else None,
            response_status_code=int(data['responseStatusCode']) if 'responseStatusCode' in data else None,
            response_headers=Headers.from_json(data['responseHeaders']) if 'responseHeaders' in data else None,
            request_id=RequestId.from_json(data['requestId']) if 'requestId' in data else None,
        )


@dataclass
class RequestServedFromCache:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.requestServedFromCache")
    request_id: RequestId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestServedFromCache:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
        )


@dataclass
class RequestWillBeSent:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.requestWillBeSent")
    request_id: RequestId
    loader_id: LoaderId
    document_url: str
    request: Request
    timestamp: MonotonicTime
    wall_time: TimeSinceEpoch
    initiator: Initiator
    redirect_has_extra_info: bool
    redirect_response: Optional[Response] = None
    type: Optional[ResourceType] = None
    frame_id: Optional[FrameId] = None
    has_user_gesture: Optional[bool] = None
    render_blocking_behavior: Optional[RenderBlockingBehavior] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestWillBeSent:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            loader_id=LoaderId.from_json(data['loaderId']),
            document_url=str(data['documentURL']),
            request=Request.from_json(data['request']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            wall_time=TimeSinceEpoch.from_json(data['wallTime']),
            initiator=Initiator.from_json(data['initiator']),
            redirect_has_extra_info=bool(data['redirectHasExtraInfo']),
            redirect_response=Response.from_json(data['redirectResponse']) if 'redirectResponse' in data else None,
            type=ResourceType.from_json(data['type']) if 'type' in data else None,
            frame_id=FrameId.from_json(data['frameId']) if 'frameId' in data else None,
            has_user_gesture=bool(data['hasUserGesture']) if 'hasUserGesture' in data else None,
            render_blocking_behavior=RenderBlockingBehavior.from_json(data['renderBlockingBehavior']) if 'renderBlockingBehavior' in data else None,
        )


@dataclass
class ResourceChangedPriority:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.resourceChangedPriority")
    request_id: RequestId
    new_priority: ResourcePriority
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ResourceChangedPriority:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            new_priority=ResourcePriority.from_json(data['newPriority']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class SignedExchangeReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.signedExchangeReceived")
    request_id: RequestId
    info: SignedExchangeInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SignedExchangeReceived:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            info=SignedExchangeInfo.from_json(data['info']),
        )


@dataclass
class ResponseReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.responseReceived")
    request_id: RequestId
    loader_id: LoaderId
    timestamp: MonotonicTime
    type: ResourceType
    response: Response
    has_extra_info: bool
    frame_id: Optional[FrameId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ResponseReceived:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            loader_id=LoaderId.from_json(data['loaderId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            type=ResourceType.from_json(data['type']),
            response=Response.from_json(data['response']),
            has_extra_info=bool(data['hasExtraInfo']),
            frame_id=FrameId.from_json(data['frameId']) if 'frameId' in data else None,
        )


@dataclass
class WebSocketClosed:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketClosed")
    request_id: RequestId
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketClosed:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class WebSocketCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketCreated")
    request_id: RequestId
    url: str
    initiator: Optional[Initiator] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketCreated:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            url=str(data['url']),
            initiator=Initiator.from_json(data['initiator']) if 'initiator' in data else None,
        )


@dataclass
class WebSocketFrameError:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketFrameError")
    request_id: RequestId
    timestamp: MonotonicTime
    error_message: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketFrameError:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            error_message=str(data['errorMessage']),
        )


@dataclass
class WebSocketFrameReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketFrameReceived")
    request_id: RequestId
    timestamp: MonotonicTime
    response: WebSocketFrame

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketFrameReceived:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            response=WebSocketFrame.from_json(data['response']),
        )


@dataclass
class WebSocketFrameSent:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketFrameSent")
    request_id: RequestId
    timestamp: MonotonicTime
    response: WebSocketFrame

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketFrameSent:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            response=WebSocketFrame.from_json(data['response']),
        )


@dataclass
class WebSocketHandshakeResponseReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketHandshakeResponseReceived")
    request_id: RequestId
    timestamp: MonotonicTime
    response: WebSocketResponse

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketHandshakeResponseReceived:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            response=WebSocketResponse.from_json(data['response']),
        )


@dataclass
class WebSocketWillSendHandshakeRequest:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webSocketWillSendHandshakeRequest")
    request_id: RequestId
    timestamp: MonotonicTime
    wall_time: TimeSinceEpoch
    request: WebSocketRequest

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebSocketWillSendHandshakeRequest:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            wall_time=TimeSinceEpoch.from_json(data['wallTime']),
            request=WebSocketRequest.from_json(data['request']),
        )


@dataclass
class WebTransportCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webTransportCreated")
    transport_id: RequestId
    url: str
    timestamp: MonotonicTime
    initiator: Optional[Initiator] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebTransportCreated:
        return cls(
            transport_id=RequestId.from_json(data['transportId']),
            url=str(data['url']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            initiator=Initiator.from_json(data['initiator']) if 'initiator' in data else None,
        )


@dataclass
class WebTransportConnectionEstablished:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webTransportConnectionEstablished")
    transport_id: RequestId
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebTransportConnectionEstablished:
        return cls(
            transport_id=RequestId.from_json(data['transportId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class WebTransportClosed:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.webTransportClosed")
    transport_id: RequestId
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebTransportClosed:
        return cls(
            transport_id=RequestId.from_json(data['transportId']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectTCPSocketCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directTCPSocketCreated")
    identifier: RequestId
    remote_addr: str
    remote_port: int
    options: DirectTCPSocketOptions
    timestamp: MonotonicTime
    initiator: Optional[Initiator] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketCreated:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            remote_addr=str(data['remoteAddr']),
            remote_port=int(data['remotePort']),
            options=DirectTCPSocketOptions.from_json(data['options']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            initiator=Initiator.from_json(data['initiator']) if 'initiator' in data else None,
        )


@dataclass
class DirectTCPSocketOpened:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directTCPSocketOpened")
    identifier: RequestId
    remote_addr: str
    remote_port: int
    timestamp: MonotonicTime
    local_addr: Optional[str] = None
    local_port: Optional[int] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketOpened:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            remote_addr=str(data['remoteAddr']),
            remote_port=int(data['remotePort']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            local_addr=str(data['localAddr']) if 'localAddr' in data else None,
            local_port=int(data['localPort']) if 'localPort' in data else None,
        )


@dataclass
class DirectTCPSocketAborted:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directTCPSocketAborted")
    identifier: RequestId
    error_message: str
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketAborted:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            error_message=str(data['errorMessage']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectTCPSocketClosed:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directTCPSocketClosed")
    identifier: RequestId
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketClosed:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectTCPSocketChunkSent:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directTCPSocketChunkSent")
    identifier: RequestId
    data: str
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketChunkSent:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            data=str(data['data']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectTCPSocketChunkReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directTCPSocketChunkReceived")
    identifier: RequestId
    data: str
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectTCPSocketChunkReceived:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            data=str(data['data']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectUDPSocketJoinedMulticastGroup:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketJoinedMulticastGroup")
    identifier: RequestId
    ip_address: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketJoinedMulticastGroup:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            ip_address=str(data['IPAddress']),
        )


@dataclass
class DirectUDPSocketLeftMulticastGroup:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketLeftMulticastGroup")
    identifier: RequestId
    ip_address: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketLeftMulticastGroup:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            ip_address=str(data['IPAddress']),
        )


@dataclass
class DirectUDPSocketCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketCreated")
    identifier: RequestId
    options: DirectUDPSocketOptions
    timestamp: MonotonicTime
    initiator: Optional[Initiator] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketCreated:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            options=DirectUDPSocketOptions.from_json(data['options']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            initiator=Initiator.from_json(data['initiator']) if 'initiator' in data else None,
        )


@dataclass
class DirectUDPSocketOpened:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketOpened")
    identifier: RequestId
    local_addr: str
    local_port: int
    timestamp: MonotonicTime
    remote_addr: Optional[str] = None
    remote_port: Optional[int] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketOpened:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            local_addr=str(data['localAddr']),
            local_port=int(data['localPort']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
            remote_addr=str(data['remoteAddr']) if 'remoteAddr' in data else None,
            remote_port=int(data['remotePort']) if 'remotePort' in data else None,
        )


@dataclass
class DirectUDPSocketAborted:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketAborted")
    identifier: RequestId
    error_message: str
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketAborted:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            error_message=str(data['errorMessage']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectUDPSocketClosed:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketClosed")
    identifier: RequestId
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketClosed:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectUDPSocketChunkSent:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketChunkSent")
    identifier: RequestId
    message: DirectUDPMessage
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketChunkSent:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            message=DirectUDPMessage.from_json(data['message']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class DirectUDPSocketChunkReceived:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.directUDPSocketChunkReceived")
    identifier: RequestId
    message: DirectUDPMessage
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DirectUDPSocketChunkReceived:
        return cls(
            identifier=RequestId.from_json(data['identifier']),
            message=DirectUDPMessage.from_json(data['message']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class RequestWillBeSentExtraInfo:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.requestWillBeSentExtraInfo")
    request_id: RequestId
    associated_cookies: list[AssociatedCookie]
    headers: Headers
    connect_timing: ConnectTiming
    device_bound_session_usages: Optional[list[DeviceBoundSessionWithUsage]] = None
    client_security_state: Optional[ClientSecurityState] = None
    site_has_cookie_in_other_partition: Optional[bool] = None
    applied_network_conditions_id: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestWillBeSentExtraInfo:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            associated_cookies=[AssociatedCookie.from_json(i) for i in data['associatedCookies']],
            headers=Headers.from_json(data['headers']),
            connect_timing=ConnectTiming.from_json(data['connectTiming']),
            device_bound_session_usages=[DeviceBoundSessionWithUsage.from_json(i) for i in data['deviceBoundSessionUsages']] if 'deviceBoundSessionUsages' in data else None,
            client_security_state=ClientSecurityState.from_json(data['clientSecurityState']) if 'clientSecurityState' in data else None,
            site_has_cookie_in_other_partition=bool(data['siteHasCookieInOtherPartition']) if 'siteHasCookieInOtherPartition' in data else None,
            applied_network_conditions_id=str(data['appliedNetworkConditionsId']) if 'appliedNetworkConditionsId' in data else None,
        )


@dataclass
class ResponseReceivedExtraInfo:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.responseReceivedExtraInfo")
    request_id: RequestId
    blocked_cookies: list[BlockedSetCookieWithReason]
    headers: Headers
    resource_ip_address_space: IPAddressSpace
    status_code: int
    headers_text: Optional[str] = None
    cookie_partition_key: Optional[CookiePartitionKey] = None
    cookie_partition_key_opaque: Optional[bool] = None
    exempted_cookies: Optional[list[ExemptedSetCookieWithReason]] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ResponseReceivedExtraInfo:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            blocked_cookies=[BlockedSetCookieWithReason.from_json(i) for i in data['blockedCookies']],
            headers=Headers.from_json(data['headers']),
            resource_ip_address_space=IPAddressSpace.from_json(data['resourceIPAddressSpace']),
            status_code=int(data['statusCode']),
            headers_text=str(data['headersText']) if 'headersText' in data else None,
            cookie_partition_key=CookiePartitionKey.from_json(data['cookiePartitionKey']) if 'cookiePartitionKey' in data else None,
            cookie_partition_key_opaque=bool(data['cookiePartitionKeyOpaque']) if 'cookiePartitionKeyOpaque' in data else None,
            exempted_cookies=[ExemptedSetCookieWithReason.from_json(i) for i in data['exemptedCookies']] if 'exemptedCookies' in data else None,
        )


@dataclass
class ResponseReceivedEarlyHints:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.responseReceivedEarlyHints")
    request_id: RequestId
    headers: Headers

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ResponseReceivedEarlyHints:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            headers=Headers.from_json(data['headers']),
        )


@dataclass
class TrustTokenOperationDone:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.trustTokenOperationDone")
    status: str
    type: TrustTokenOperationType
    request_id: RequestId
    top_level_origin: Optional[str] = None
    issuer_origin: Optional[str] = None
    issued_token_count: Optional[int] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TrustTokenOperationDone:
        return cls(
            status=str(data['status']),
            type=TrustTokenOperationType.from_json(data['type']),
            request_id=RequestId.from_json(data['requestId']),
            top_level_origin=str(data['topLevelOrigin']) if 'topLevelOrigin' in data else None,
            issuer_origin=str(data['issuerOrigin']) if 'issuerOrigin' in data else None,
            issued_token_count=int(data['issuedTokenCount']) if 'issuedTokenCount' in data else None,
        )


@dataclass
class PolicyUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.policyUpdated")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PolicyUpdated:
        return cls()


@dataclass
class ReportingApiReportAdded:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.reportingApiReportAdded")
    report: ReportingApiReport

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ReportingApiReportAdded:
        return cls(
            report=ReportingApiReport.from_json(data['report']),
        )


@dataclass
class ReportingApiReportUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.reportingApiReportUpdated")
    report: ReportingApiReport

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ReportingApiReportUpdated:
        return cls(
            report=ReportingApiReport.from_json(data['report']),
        )


@dataclass
class ReportingApiEndpointsChangedForOrigin:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.reportingApiEndpointsChangedForOrigin")
    origin: str
    endpoints: list[ReportingApiEndpoint]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ReportingApiEndpointsChangedForOrigin:
        return cls(
            origin=str(data['origin']),
            endpoints=[ReportingApiEndpoint.from_json(i) for i in data['endpoints']],
        )


@dataclass
class DeviceBoundSessionsAdded:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.deviceBoundSessionsAdded")
    sessions: list[DeviceBoundSession]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionsAdded:
        return cls(
            sessions=[DeviceBoundSession.from_json(i) for i in data['sessions']],
        )


@dataclass
class DeviceBoundSessionEventOccurred:
    EVENT_NAME: str = field(init=False, repr=False, default="Network.deviceBoundSessionEventOccurred")
    event_id: DeviceBoundSessionEventId
    site: str
    succeeded: bool
    session_id: Optional[str] = None
    creation_event_details: Optional[CreationEventDetails] = None
    refresh_event_details: Optional[RefreshEventDetails] = None
    termination_event_details: Optional[TerminationEventDetails] = None
    challenge_event_details: Optional[ChallengeEventDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeviceBoundSessionEventOccurred:
        return cls(
            event_id=DeviceBoundSessionEventId.from_json(data['eventId']),
            site=str(data['site']),
            succeeded=bool(data['succeeded']),
            session_id=str(data['sessionId']) if 'sessionId' in data else None,
            creation_event_details=CreationEventDetails.from_json(data['creationEventDetails']) if 'creationEventDetails' in data else None,
            refresh_event_details=RefreshEventDetails.from_json(data['refreshEventDetails']) if 'refreshEventDetails' in data else None,
            termination_event_details=TerminationEventDetails.from_json(data['terminationEventDetails']) if 'terminationEventDetails' in data else None,
            challenge_event_details=ChallengeEventDetails.from_json(data['challengeEventDetails']) if 'challengeEventDetails' in data else None,
        )

