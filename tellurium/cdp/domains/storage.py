"""Auto-generated CDP bindings for the Storage domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class SerializedStorageKey(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SerializedStorageKey:
        return cls(val)


class StorageType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> StorageType:
        return cls(val)


@dataclass
class UsageForType:
    storage_type: StorageType
    usage: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['storageType'] = storage_type.to_json()
        d['usage'] = usage
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> UsageForType:
        return cls(
            storage_type=StorageType.from_json(data['storageType']),
            usage=float(data['usage']),
        )


@dataclass
class TrustTokens:
    issuer_origin: str
    count: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['issuerOrigin'] = issuer_origin
        d['count'] = count
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TrustTokens:
        return cls(
            issuer_origin=str(data['issuerOrigin']),
            count=float(data['count']),
        )


class InterestGroupAuctionId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> InterestGroupAuctionId:
        return cls(val)


class InterestGroupAccessType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> InterestGroupAccessType:
        return cls(val)


class InterestGroupAuctionEventType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> InterestGroupAuctionEventType:
        return cls(val)


class InterestGroupAuctionFetchType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> InterestGroupAuctionFetchType:
        return cls(val)


class SharedStorageAccessScope(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SharedStorageAccessScope:
        return cls(val)


class SharedStorageAccessMethod(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SharedStorageAccessMethod:
        return cls(val)


@dataclass
class SharedStorageEntry:
    key: str
    value: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['key'] = key
        d['value'] = value
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageEntry:
        return cls(
            key=str(data['key']),
            value=str(data['value']),
        )


@dataclass
class SharedStorageMetadata:
    creation_time: TimeSinceEpoch
    length: int
    remaining_budget: float
    bytes_used: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['creationTime'] = creation_time.to_json()
        d['length'] = length
        d['remainingBudget'] = remaining_budget
        d['bytesUsed'] = bytes_used
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageMetadata:
        return cls(
            creation_time=TimeSinceEpoch.from_json(data['creationTime']),
            length=int(data['length']),
            remaining_budget=float(data['remainingBudget']),
            bytes_used=int(data['bytesUsed']),
        )


@dataclass
class SharedStoragePrivateAggregationConfig:
    filtering_id_max_bytes: int
    aggregation_coordinator_origin: Optional[str] = None
    context_id: Optional[str] = None
    max_contributions: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['filteringIdMaxBytes'] = filtering_id_max_bytes
        if self.aggregation_coordinator_origin is not None:
            d['aggregationCoordinatorOrigin'] = self.aggregation_coordinator_origin
        if self.context_id is not None:
            d['contextId'] = self.context_id
        if self.max_contributions is not None:
            d['maxContributions'] = self.max_contributions
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStoragePrivateAggregationConfig:
        return cls(
            filtering_id_max_bytes=int(data['filteringIdMaxBytes']),
            aggregation_coordinator_origin=str(data['aggregationCoordinatorOrigin']) if 'aggregationCoordinatorOrigin' in data else None,
            context_id=str(data['contextId']) if 'contextId' in data else None,
            max_contributions=int(data['maxContributions']) if 'maxContributions' in data else None,
        )


@dataclass
class SharedStorageReportingMetadata:
    event_type: str
    reporting_url: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['eventType'] = event_type
        d['reportingUrl'] = reporting_url
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageReportingMetadata:
        return cls(
            event_type=str(data['eventType']),
            reporting_url=str(data['reportingUrl']),
        )


@dataclass
class SharedStorageUrlWithMetadata:
    url: str
    reporting_metadata: list[SharedStorageReportingMetadata]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['reportingMetadata'] = [i.to_json() for i in reporting_metadata]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageUrlWithMetadata:
        return cls(
            url=str(data['url']),
            reporting_metadata=[SharedStorageReportingMetadata.from_json(i) for i in data['reportingMetadata']],
        )


@dataclass
class SharedStorageAccessParams:
    script_source_url: Optional[str] = None
    data_origin: Optional[str] = None
    operation_name: Optional[str] = None
    operation_id: Optional[str] = None
    keep_alive: Optional[bool] = None
    private_aggregation_config: Optional[SharedStoragePrivateAggregationConfig] = None
    serialized_data: Optional[str] = None
    urls_with_metadata: Optional[list[SharedStorageUrlWithMetadata]] = None
    urn_uuid: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None
    ignore_if_present: Optional[bool] = None
    worklet_ordinal: Optional[int] = None
    worklet_target_id: Optional[TargetID] = None
    with_lock: Optional[str] = None
    batch_update_id: Optional[str] = None
    batch_size: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.script_source_url is not None:
            d['scriptSourceUrl'] = self.script_source_url
        if self.data_origin is not None:
            d['dataOrigin'] = self.data_origin
        if self.operation_name is not None:
            d['operationName'] = self.operation_name
        if self.operation_id is not None:
            d['operationId'] = self.operation_id
        if self.keep_alive is not None:
            d['keepAlive'] = self.keep_alive
        if self.private_aggregation_config is not None:
            d['privateAggregationConfig'] = self.private_aggregation_config.to_json()
        if self.serialized_data is not None:
            d['serializedData'] = self.serialized_data
        if self.urls_with_metadata is not None:
            d['urlsWithMetadata'] = [i.to_json() for i in self.urls_with_metadata]
        if self.urn_uuid is not None:
            d['urnUuid'] = self.urn_uuid
        if self.key is not None:
            d['key'] = self.key
        if self.value is not None:
            d['value'] = self.value
        if self.ignore_if_present is not None:
            d['ignoreIfPresent'] = self.ignore_if_present
        if self.worklet_ordinal is not None:
            d['workletOrdinal'] = self.worklet_ordinal
        if self.worklet_target_id is not None:
            d['workletTargetId'] = self.worklet_target_id.to_json()
        if self.with_lock is not None:
            d['withLock'] = self.with_lock
        if self.batch_update_id is not None:
            d['batchUpdateId'] = self.batch_update_id
        if self.batch_size is not None:
            d['batchSize'] = self.batch_size
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageAccessParams:
        return cls(
            script_source_url=str(data['scriptSourceUrl']) if 'scriptSourceUrl' in data else None,
            data_origin=str(data['dataOrigin']) if 'dataOrigin' in data else None,
            operation_name=str(data['operationName']) if 'operationName' in data else None,
            operation_id=str(data['operationId']) if 'operationId' in data else None,
            keep_alive=bool(data['keepAlive']) if 'keepAlive' in data else None,
            private_aggregation_config=SharedStoragePrivateAggregationConfig.from_json(data['privateAggregationConfig']) if 'privateAggregationConfig' in data else None,
            serialized_data=str(data['serializedData']) if 'serializedData' in data else None,
            urls_with_metadata=[SharedStorageUrlWithMetadata.from_json(i) for i in data['urlsWithMetadata']] if 'urlsWithMetadata' in data else None,
            urn_uuid=str(data['urnUuid']) if 'urnUuid' in data else None,
            key=str(data['key']) if 'key' in data else None,
            value=str(data['value']) if 'value' in data else None,
            ignore_if_present=bool(data['ignoreIfPresent']) if 'ignoreIfPresent' in data else None,
            worklet_ordinal=int(data['workletOrdinal']) if 'workletOrdinal' in data else None,
            worklet_target_id=TargetID.from_json(data['workletTargetId']) if 'workletTargetId' in data else None,
            with_lock=str(data['withLock']) if 'withLock' in data else None,
            batch_update_id=str(data['batchUpdateId']) if 'batchUpdateId' in data else None,
            batch_size=int(data['batchSize']) if 'batchSize' in data else None,
        )


class StorageBucketsDurability(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> StorageBucketsDurability:
        return cls(val)


@dataclass
class StorageBucket:
    storage_key: SerializedStorageKey
    name: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['storageKey'] = storage_key.to_json()
        if self.name is not None:
            d['name'] = self.name
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StorageBucket:
        return cls(
            storage_key=SerializedStorageKey.from_json(data['storageKey']),
            name=str(data['name']) if 'name' in data else None,
        )


@dataclass
class StorageBucketInfo:
    bucket: StorageBucket
    id: str
    expiration: TimeSinceEpoch
    quota: float
    persistent: bool
    durability: StorageBucketsDurability

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['bucket'] = bucket.to_json()
        d['id'] = id
        d['expiration'] = expiration.to_json()
        d['quota'] = quota
        d['persistent'] = persistent
        d['durability'] = durability.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StorageBucketInfo:
        return cls(
            bucket=StorageBucket.from_json(data['bucket']),
            id=str(data['id']),
            expiration=TimeSinceEpoch.from_json(data['expiration']),
            quota=float(data['quota']),
            persistent=bool(data['persistent']),
            durability=StorageBucketsDurability.from_json(data['durability']),
        )


@dataclass
class RelatedWebsiteSet:
    primary_sites: list[str]
    associated_sites: list[str]
    service_sites: list[str]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['primarySites'] = list(primary_sites)
        d['associatedSites'] = list(associated_sites)
        d['serviceSites'] = list(service_sites)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RelatedWebsiteSet:
        return cls(
            primary_sites=[str(i) for i in data['primarySites']],
            associated_sites=[str(i) for i in data['associatedSites']],
            service_sites=[str(i) for i in data['serviceSites']],
        )


@dataclass
class GetStorageKeyForFrameResult:
    storage_key: SerializedStorageKey

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetStorageKeyForFrameResult:
        return cls(
            storage_key=SerializedStorageKey.from_json(data['storageKey']),
        )


def get_storage_key_for_frame(frame_id: FrameId) -> tuple[T_JSON_DICT, type[GetStorageKeyForFrameResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Storage.getStorageKeyForFrame", "params": params}
    return cmd, GetStorageKeyForFrameResult


@dataclass
class GetStorageKeyResult:
    storage_key: SerializedStorageKey

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetStorageKeyResult:
        return cls(
            storage_key=SerializedStorageKey.from_json(data['storageKey']),
        )


def get_storage_key(frame_id: Optional[FrameId] = None) -> tuple[T_JSON_DICT, type[GetStorageKeyResult]]:
    params: T_JSON_DICT = {}
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Storage.getStorageKey", "params": params}
    return cmd, GetStorageKeyResult


def clear_data_for_origin(origin: str, storage_types: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    params['storageTypes'] = storage_types
    cmd: T_JSON_DICT = {"method": "Storage.clearDataForOrigin", "params": params}
    return cmd, None


def clear_data_for_storage_key(storage_key: str, storage_types: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['storageKey'] = storage_key
    params['storageTypes'] = storage_types
    cmd: T_JSON_DICT = {"method": "Storage.clearDataForStorageKey", "params": params}
    return cmd, None


@dataclass
class GetCookiesResult:
    cookies: list[Cookie]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetCookiesResult:
        return cls(
            cookies=[Cookie.from_json(i) for i in data['cookies']],
        )


def get_cookies(browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, type[GetCookiesResult]]:
    params: T_JSON_DICT = {}
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Storage.getCookies", "params": params}
    return cmd, GetCookiesResult


def set_cookies(cookies: list[CookieParam], browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['cookies'] = [i.to_json() for i in cookies]
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Storage.setCookies", "params": params}
    return cmd, None


def clear_cookies(browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Storage.clearCookies", "params": params}
    return cmd, None


@dataclass
class GetUsageAndQuotaResult:
    usage: float
    quota: float
    override_active: bool
    usage_breakdown: list[UsageForType]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetUsageAndQuotaResult:
        return cls(
            usage=float(data['usage']),
            quota=float(data['quota']),
            override_active=bool(data['overrideActive']),
            usage_breakdown=[UsageForType.from_json(i) for i in data['usageBreakdown']],
        )


def get_usage_and_quota(origin: str) -> tuple[T_JSON_DICT, type[GetUsageAndQuotaResult]]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Storage.getUsageAndQuota", "params": params}
    return cmd, GetUsageAndQuotaResult


def override_quota_for_origin(origin: str, quota_size: Optional[float] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    if quota_size is not None:
        params['quotaSize'] = quota_size
    cmd: T_JSON_DICT = {"method": "Storage.overrideQuotaForOrigin", "params": params}
    return cmd, None


def track_cache_storage_for_origin(origin: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Storage.trackCacheStorageForOrigin", "params": params}
    return cmd, None


def track_cache_storage_for_storage_key(storage_key: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['storageKey'] = storage_key
    cmd: T_JSON_DICT = {"method": "Storage.trackCacheStorageForStorageKey", "params": params}
    return cmd, None


def track_indexed_db_for_origin(origin: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Storage.trackIndexedDBForOrigin", "params": params}
    return cmd, None


def track_indexed_db_for_storage_key(storage_key: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['storageKey'] = storage_key
    cmd: T_JSON_DICT = {"method": "Storage.trackIndexedDBForStorageKey", "params": params}
    return cmd, None


def untrack_cache_storage_for_origin(origin: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Storage.untrackCacheStorageForOrigin", "params": params}
    return cmd, None


def untrack_cache_storage_for_storage_key(storage_key: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['storageKey'] = storage_key
    cmd: T_JSON_DICT = {"method": "Storage.untrackCacheStorageForStorageKey", "params": params}
    return cmd, None


def untrack_indexed_db_for_origin(origin: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['origin'] = origin
    cmd: T_JSON_DICT = {"method": "Storage.untrackIndexedDBForOrigin", "params": params}
    return cmd, None


def untrack_indexed_db_for_storage_key(storage_key: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['storageKey'] = storage_key
    cmd: T_JSON_DICT = {"method": "Storage.untrackIndexedDBForStorageKey", "params": params}
    return cmd, None


@dataclass
class GetTrustTokensResult:
    tokens: list[TrustTokens]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetTrustTokensResult:
        return cls(
            tokens=[TrustTokens.from_json(i) for i in data['tokens']],
        )


def get_trust_tokens() -> tuple[T_JSON_DICT, type[GetTrustTokensResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Storage.getTrustTokens", "params": params}
    return cmd, GetTrustTokensResult


@dataclass
class ClearTrustTokensResult:
    did_delete_tokens: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ClearTrustTokensResult:
        return cls(
            did_delete_tokens=bool(data['didDeleteTokens']),
        )


def clear_trust_tokens(issuer_origin: str) -> tuple[T_JSON_DICT, type[ClearTrustTokensResult]]:
    params: T_JSON_DICT = {}
    params['issuerOrigin'] = issuer_origin
    cmd: T_JSON_DICT = {"method": "Storage.clearTrustTokens", "params": params}
    return cmd, ClearTrustTokensResult


@dataclass
class GetInterestGroupDetailsResult:
    details: T_JSON_DICT

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetInterestGroupDetailsResult:
        return cls(
            details=data['details'],
        )


def get_interest_group_details(owner_origin: str, name: str) -> tuple[T_JSON_DICT, type[GetInterestGroupDetailsResult]]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    params['name'] = name
    cmd: T_JSON_DICT = {"method": "Storage.getInterestGroupDetails", "params": params}
    return cmd, GetInterestGroupDetailsResult


def set_interest_group_tracking(enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "Storage.setInterestGroupTracking", "params": params}
    return cmd, None


def set_interest_group_auction_tracking(enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "Storage.setInterestGroupAuctionTracking", "params": params}
    return cmd, None


@dataclass
class GetSharedStorageMetadataResult:
    metadata: SharedStorageMetadata

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetSharedStorageMetadataResult:
        return cls(
            metadata=SharedStorageMetadata.from_json(data['metadata']),
        )


def get_shared_storage_metadata(owner_origin: str) -> tuple[T_JSON_DICT, type[GetSharedStorageMetadataResult]]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    cmd: T_JSON_DICT = {"method": "Storage.getSharedStorageMetadata", "params": params}
    return cmd, GetSharedStorageMetadataResult


@dataclass
class GetSharedStorageEntriesResult:
    entries: list[SharedStorageEntry]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetSharedStorageEntriesResult:
        return cls(
            entries=[SharedStorageEntry.from_json(i) for i in data['entries']],
        )


def get_shared_storage_entries(owner_origin: str) -> tuple[T_JSON_DICT, type[GetSharedStorageEntriesResult]]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    cmd: T_JSON_DICT = {"method": "Storage.getSharedStorageEntries", "params": params}
    return cmd, GetSharedStorageEntriesResult


def set_shared_storage_entry(owner_origin: str, key: str, value: str, ignore_if_present: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    params['key'] = key
    params['value'] = value
    if ignore_if_present is not None:
        params['ignoreIfPresent'] = ignore_if_present
    cmd: T_JSON_DICT = {"method": "Storage.setSharedStorageEntry", "params": params}
    return cmd, None


def delete_shared_storage_entry(owner_origin: str, key: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    params['key'] = key
    cmd: T_JSON_DICT = {"method": "Storage.deleteSharedStorageEntry", "params": params}
    return cmd, None


def clear_shared_storage_entries(owner_origin: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    cmd: T_JSON_DICT = {"method": "Storage.clearSharedStorageEntries", "params": params}
    return cmd, None


def reset_shared_storage_budget(owner_origin: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['ownerOrigin'] = owner_origin
    cmd: T_JSON_DICT = {"method": "Storage.resetSharedStorageBudget", "params": params}
    return cmd, None


def set_shared_storage_tracking(enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "Storage.setSharedStorageTracking", "params": params}
    return cmd, None


def set_storage_bucket_tracking(storage_key: str, enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['storageKey'] = storage_key
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "Storage.setStorageBucketTracking", "params": params}
    return cmd, None


def delete_storage_bucket(bucket: StorageBucket) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['bucket'] = bucket.to_json()
    cmd: T_JSON_DICT = {"method": "Storage.deleteStorageBucket", "params": params}
    return cmd, None


@dataclass
class RunBounceTrackingMitigationsResult:
    deleted_sites: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RunBounceTrackingMitigationsResult:
        return cls(
            deleted_sites=[str(i) for i in data['deletedSites']],
        )


def run_bounce_tracking_mitigations() -> tuple[T_JSON_DICT, type[RunBounceTrackingMitigationsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Storage.runBounceTrackingMitigations", "params": params}
    return cmd, RunBounceTrackingMitigationsResult


@dataclass
class GetRelatedWebsiteSetsResult:
    sets: list[RelatedWebsiteSet]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetRelatedWebsiteSetsResult:
        return cls(
            sets=[RelatedWebsiteSet.from_json(i) for i in data['sets']],
        )


def get_related_website_sets() -> tuple[T_JSON_DICT, type[GetRelatedWebsiteSetsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Storage.getRelatedWebsiteSets", "params": params}
    return cmd, GetRelatedWebsiteSetsResult


def set_protected_audience_k_anonymity(owner: str, name: str, hashes: list[str]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['owner'] = owner
    params['name'] = name
    params['hashes'] = list(hashes)
    cmd: T_JSON_DICT = {"method": "Storage.setProtectedAudienceKAnonymity", "params": params}
    return cmd, None


@dataclass
class CacheStorageContentUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.cacheStorageContentUpdated")
    origin: str
    storage_key: str
    bucket_id: str
    cache_name: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CacheStorageContentUpdated:
        return cls(
            origin=str(data['origin']),
            storage_key=str(data['storageKey']),
            bucket_id=str(data['bucketId']),
            cache_name=str(data['cacheName']),
        )


@dataclass
class CacheStorageListUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.cacheStorageListUpdated")
    origin: str
    storage_key: str
    bucket_id: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CacheStorageListUpdated:
        return cls(
            origin=str(data['origin']),
            storage_key=str(data['storageKey']),
            bucket_id=str(data['bucketId']),
        )


@dataclass
class IndexedDBContentUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.indexedDBContentUpdated")
    origin: str
    storage_key: str
    bucket_id: str
    database_name: str
    object_store_name: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> IndexedDBContentUpdated:
        return cls(
            origin=str(data['origin']),
            storage_key=str(data['storageKey']),
            bucket_id=str(data['bucketId']),
            database_name=str(data['databaseName']),
            object_store_name=str(data['objectStoreName']),
        )


@dataclass
class IndexedDBListUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.indexedDBListUpdated")
    origin: str
    storage_key: str
    bucket_id: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> IndexedDBListUpdated:
        return cls(
            origin=str(data['origin']),
            storage_key=str(data['storageKey']),
            bucket_id=str(data['bucketId']),
        )


@dataclass
class InterestGroupAccessed:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.interestGroupAccessed")
    access_time: TimeSinceEpoch
    type: InterestGroupAccessType
    owner_origin: str
    name: str
    component_seller_origin: Optional[str] = None
    bid: Optional[float] = None
    bid_currency: Optional[str] = None
    unique_auction_id: Optional[InterestGroupAuctionId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InterestGroupAccessed:
        return cls(
            access_time=TimeSinceEpoch.from_json(data['accessTime']),
            type=InterestGroupAccessType.from_json(data['type']),
            owner_origin=str(data['ownerOrigin']),
            name=str(data['name']),
            component_seller_origin=str(data['componentSellerOrigin']) if 'componentSellerOrigin' in data else None,
            bid=float(data['bid']) if 'bid' in data else None,
            bid_currency=str(data['bidCurrency']) if 'bidCurrency' in data else None,
            unique_auction_id=InterestGroupAuctionId.from_json(data['uniqueAuctionId']) if 'uniqueAuctionId' in data else None,
        )


@dataclass
class InterestGroupAuctionEventOccurred:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.interestGroupAuctionEventOccurred")
    event_time: TimeSinceEpoch
    type: InterestGroupAuctionEventType
    unique_auction_id: InterestGroupAuctionId
    parent_auction_id: Optional[InterestGroupAuctionId] = None
    auction_config: Optional[T_JSON_DICT] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InterestGroupAuctionEventOccurred:
        return cls(
            event_time=TimeSinceEpoch.from_json(data['eventTime']),
            type=InterestGroupAuctionEventType.from_json(data['type']),
            unique_auction_id=InterestGroupAuctionId.from_json(data['uniqueAuctionId']),
            parent_auction_id=InterestGroupAuctionId.from_json(data['parentAuctionId']) if 'parentAuctionId' in data else None,
            auction_config=data['auctionConfig'] if 'auctionConfig' in data else None,
        )


@dataclass
class InterestGroupAuctionNetworkRequestCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.interestGroupAuctionNetworkRequestCreated")
    type: InterestGroupAuctionFetchType
    request_id: RequestId
    auctions: list[InterestGroupAuctionId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InterestGroupAuctionNetworkRequestCreated:
        return cls(
            type=InterestGroupAuctionFetchType.from_json(data['type']),
            request_id=RequestId.from_json(data['requestId']),
            auctions=[InterestGroupAuctionId.from_json(i) for i in data['auctions']],
        )


@dataclass
class SharedStorageAccessed:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.sharedStorageAccessed")
    access_time: TimeSinceEpoch
    scope: SharedStorageAccessScope
    method: SharedStorageAccessMethod
    main_frame_id: FrameId
    owner_origin: str
    owner_site: str
    params: SharedStorageAccessParams

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageAccessed:
        return cls(
            access_time=TimeSinceEpoch.from_json(data['accessTime']),
            scope=SharedStorageAccessScope.from_json(data['scope']),
            method=SharedStorageAccessMethod.from_json(data['method']),
            main_frame_id=FrameId.from_json(data['mainFrameId']),
            owner_origin=str(data['ownerOrigin']),
            owner_site=str(data['ownerSite']),
            params=SharedStorageAccessParams.from_json(data['params']),
        )


@dataclass
class SharedStorageWorkletOperationExecutionFinished:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.sharedStorageWorkletOperationExecutionFinished")
    finished_time: TimeSinceEpoch
    execution_time: int
    method: SharedStorageAccessMethod
    operation_id: str
    worklet_target_id: TargetID
    main_frame_id: FrameId
    owner_origin: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SharedStorageWorkletOperationExecutionFinished:
        return cls(
            finished_time=TimeSinceEpoch.from_json(data['finishedTime']),
            execution_time=int(data['executionTime']),
            method=SharedStorageAccessMethod.from_json(data['method']),
            operation_id=str(data['operationId']),
            worklet_target_id=TargetID.from_json(data['workletTargetId']),
            main_frame_id=FrameId.from_json(data['mainFrameId']),
            owner_origin=str(data['ownerOrigin']),
        )


@dataclass
class StorageBucketCreatedOrUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.storageBucketCreatedOrUpdated")
    bucket_info: StorageBucketInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StorageBucketCreatedOrUpdated:
        return cls(
            bucket_info=StorageBucketInfo.from_json(data['bucketInfo']),
        )


@dataclass
class StorageBucketDeleted:
    EVENT_NAME: str = field(init=False, repr=False, default="Storage.storageBucketDeleted")
    bucket_id: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StorageBucketDeleted:
        return cls(
            bucket_id=str(data['bucketId']),
        )

