import os
import time
import uuid

def uuid7():
    """Generates an RFC 9562 compliant UUID v7."""
    timestamp_ms = int(time.time() * 1000)
    timestamp_bytes = timestamp_ms.to_bytes(6, byteorder='big')
    
    random_bytes = os.urandom(10)
    
    # Set version 7 in byte 6 (0111xxxx)
    b6 = (random_bytes[0] & 0x0F) | 0x70
    # Set variant 1 in byte 8 (10xxxxxx)
    b8 = (random_bytes[1] & 0x3F) | 0x80
    
    uuid_bytes = (
        timestamp_bytes +
        bytes([b6, random_bytes[2], b8]) +
        random_bytes[3:]
    )
    return uuid.UUID(bytes=uuid_bytes)

def uuid_to_bin(val):
    """Converts standard UUID string or object to 16 bytes."""
    if not val:
        return None
    if isinstance(val, uuid.UUID):
        return val.bytes
    if isinstance(val, bytes):
        if len(val) == 16:
            return val
        val = val.decode('utf-8', errors='ignore')
    if isinstance(val, int):
        return uuid.UUID(int=val).bytes
    if isinstance(val, str):
        if val.isdigit():
            return uuid.UUID(int=int(val)).bytes
        try:
            return uuid.UUID(val).bytes
        except ValueError:
            import hashlib
            return hashlib.md5(val.encode('utf-8')).digest()
    return uuid.UUID(val).bytes

def bin_to_uuid(val):
    """Converts 16 bytes binary to UUID object."""
    if not val:
        return None
    if isinstance(val, uuid.UUID):
        return val
    if isinstance(val, bytes) and len(val) == 16:
        return uuid.UUID(bytes=val)
    try:
        if isinstance(val, int):
            return uuid.UUID(int=val)
        if isinstance(val, str) and val.isdigit():
            return uuid.UUID(int=int(val))
        return uuid.UUID(str(val))
    except Exception:
        import hashlib
        h = hashlib.md5(str(val).encode('utf-8')).digest()
        return uuid.UUID(bytes=h)
