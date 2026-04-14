"""Auto-generated CDP bindings for the Fetch domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class RequestId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> RequestId:
        return cls(val)


class RequestStage(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> RequestStage:
        return cls(val)


@dataclass
class RequestPattern:
    url_pattern: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    request_stage: Optional[RequestStage] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.url_pattern is not None:
            d['urlPattern'] = self.url_pattern
        if self.resource_type is not None:
            d['resourceType'] = self.resource_type.to_json()
        if self.request_stage is not None:
            d['requestStage'] = self.request_stage.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestPattern:
        return cls(
            url_pattern=str(data['urlPattern']) if 'urlPattern' in data else None,
            resource_type=ResourceType.from_json(data['resourceType']) if 'resourceType' in data else None,
            request_stage=RequestStage.from_json(data['requestStage']) if 'requestStage' in data else None,
        )


@dataclass
class HeaderEntry:
    name: str
    value: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['value'] = value
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> HeaderEntry:
        return cls(
            name=str(data['name']),
            value=str(data['value']),
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


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Fetch.disable", "params": params}
    return cmd, None


def enable(patterns: Optional[list[RequestPattern]] = None, handle_auth_requests: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if patterns is not None:
        params['patterns'] = [i.to_json() for i in patterns]
    if handle_auth_requests is not None:
        params['handleAuthRequests'] = handle_auth_requests
    cmd: T_JSON_DICT = {"method": "Fetch.enable", "params": params}
    return cmd, None


def fail_request(request_id: RequestId, error_reason: ErrorReason) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    params['errorReason'] = error_reason.to_json()
    cmd: T_JSON_DICT = {"method": "Fetch.failRequest", "params": params}
    return cmd, None


def fulfill_request(request_id: RequestId, response_code: int, response_headers: Optional[list[HeaderEntry]] = None, binary_response_headers: Optional[str] = None, body: Optional[str] = None, response_phrase: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    params['responseCode'] = response_code
    if response_headers is not None:
        params['responseHeaders'] = [i.to_json() for i in response_headers]
    if binary_response_headers is not None:
        params['binaryResponseHeaders'] = binary_response_headers
    if body is not None:
        params['body'] = body
    if response_phrase is not None:
        params['responsePhrase'] = response_phrase
    cmd: T_JSON_DICT = {"method": "Fetch.fulfillRequest", "params": params}
    return cmd, None


def continue_request(request_id: RequestId, url: Optional[str] = None, method: Optional[str] = None, post_data: Optional[str] = None, headers: Optional[list[HeaderEntry]] = None, intercept_response: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    if url is not None:
        params['url'] = url
    if method is not None:
        params['method'] = method
    if post_data is not None:
        params['postData'] = post_data
    if headers is not None:
        params['headers'] = [i.to_json() for i in headers]
    if intercept_response is not None:
        params['interceptResponse'] = intercept_response
    cmd: T_JSON_DICT = {"method": "Fetch.continueRequest", "params": params}
    return cmd, None


def continue_with_auth(request_id: RequestId, auth_challenge_response: AuthChallengeResponse) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    params['authChallengeResponse'] = auth_challenge_response.to_json()
    cmd: T_JSON_DICT = {"method": "Fetch.continueWithAuth", "params": params}
    return cmd, None


def continue_response(request_id: RequestId, response_code: Optional[int] = None, response_phrase: Optional[str] = None, response_headers: Optional[list[HeaderEntry]] = None, binary_response_headers: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    if response_code is not None:
        params['responseCode'] = response_code
    if response_phrase is not None:
        params['responsePhrase'] = response_phrase
    if response_headers is not None:
        params['responseHeaders'] = [i.to_json() for i in response_headers]
    if binary_response_headers is not None:
        params['binaryResponseHeaders'] = binary_response_headers
    cmd: T_JSON_DICT = {"method": "Fetch.continueResponse", "params": params}
    return cmd, None


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
    cmd: T_JSON_DICT = {"method": "Fetch.getResponseBody", "params": params}
    return cmd, GetResponseBodyResult


@dataclass
class TakeResponseBodyAsStreamResult:
    stream: StreamHandle

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TakeResponseBodyAsStreamResult:
        return cls(
            stream=StreamHandle.from_json(data['stream']),
        )


def take_response_body_as_stream(request_id: RequestId) -> tuple[T_JSON_DICT, type[TakeResponseBodyAsStreamResult]]:
    params: T_JSON_DICT = {}
    params['requestId'] = request_id.to_json()
    cmd: T_JSON_DICT = {"method": "Fetch.takeResponseBodyAsStream", "params": params}
    return cmd, TakeResponseBodyAsStreamResult


@dataclass
class RequestPaused:
    EVENT_NAME: str = field(init=False, repr=False, default="Fetch.requestPaused")
    request_id: RequestId
    request: Request
    frame_id: FrameId
    resource_type: ResourceType
    response_error_reason: Optional[ErrorReason] = None
    response_status_code: Optional[int] = None
    response_status_text: Optional[str] = None
    response_headers: Optional[list[HeaderEntry]] = None
    network_id: Optional[RequestId] = None
    redirected_request_id: Optional[RequestId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestPaused:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            request=Request.from_json(data['request']),
            frame_id=FrameId.from_json(data['frameId']),
            resource_type=ResourceType.from_json(data['resourceType']),
            response_error_reason=ErrorReason.from_json(data['responseErrorReason']) if 'responseErrorReason' in data else None,
            response_status_code=int(data['responseStatusCode']) if 'responseStatusCode' in data else None,
            response_status_text=str(data['responseStatusText']) if 'responseStatusText' in data else None,
            response_headers=[HeaderEntry.from_json(i) for i in data['responseHeaders']] if 'responseHeaders' in data else None,
            network_id=RequestId.from_json(data['networkId']) if 'networkId' in data else None,
            redirected_request_id=RequestId.from_json(data['redirectedRequestId']) if 'redirectedRequestId' in data else None,
        )


@dataclass
class AuthRequired:
    EVENT_NAME: str = field(init=False, repr=False, default="Fetch.authRequired")
    request_id: RequestId
    request: Request
    frame_id: FrameId
    resource_type: ResourceType
    auth_challenge: AuthChallenge

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AuthRequired:
        return cls(
            request_id=RequestId.from_json(data['requestId']),
            request=Request.from_json(data['request']),
            frame_id=FrameId.from_json(data['frameId']),
            resource_type=ResourceType.from_json(data['resourceType']),
            auth_challenge=AuthChallenge.from_json(data['authChallenge']),
        )

