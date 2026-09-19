"""
proto_engine.py - Pure-Python varint and Protobuf wire-format encoder/decoder.
Zero external dependencies. Does not require `google.protobuf`.
"""

from typing import Tuple, List, Dict, Any, Optional

def encode_varint(n: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    res = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            res.append(b | 0x80)
        else:
            res.append(b)
            break
    return bytes(res)

def decode_varint(data: bytes, pos: int) -> Tuple[int, int]:
    """Decode a varint from data starting at pos. Returns (value, next_pos)."""
    res = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, pos

def update_trajectory_metadata_bytes(val: bytes, new_uri_str: str, project_id_str: str) -> bytes:
    """
    Updates TrajectoryMetadata protobuf bytes:
    - subfield 1: workspace item (subfield 1 = uri)
    - subfield 7: uri string
    - subfield 18: project_id string
    """
    m_pos = 0
    new_m = bytearray()
    has_18 = False
    has_7 = False
    has_1 = False
    
    nb = new_uri_str.encode('utf-8') if new_uri_str else b""
    pb = project_id_str.encode('utf-8') if project_id_str else b""

    while m_pos < len(val):
        m_start = m_pos
        m_tag, m_pos = decode_varint(val, m_pos)
        m_fn = m_tag >> 3
        m_wt = m_tag & 7
        if m_wt == 2:
            m_sz, m_pos = decode_varint(val, m_pos)
            m_val = val[m_pos:m_pos+m_sz]
            m_pos += m_sz
            if m_fn == 1: # workspace item inside metadata
                has_1 = True
                sub_pos = 0
                new_sub = bytearray()
                while sub_pos < len(m_val):
                    s_start = sub_pos
                    s_tag, sub_pos = decode_varint(m_val, sub_pos)
                    s_fn = s_tag >> 3
                    s_wt = s_tag & 7
                    if s_wt == 2:
                        s_sz, sub_pos = decode_varint(m_val, sub_pos)
                        s_val = m_val[sub_pos:sub_pos+s_sz]
                        sub_pos += s_sz
                        if s_fn == 1:
                            new_sub.extend(encode_varint(s_tag) + encode_varint(len(nb)) + nb)
                        else:
                            new_sub.extend(m_val[s_start:sub_pos])
                    elif s_wt == 0:
                        _, sub_pos = decode_varint(m_val, sub_pos)
                        new_sub.extend(m_val[s_start:sub_pos])
                    elif s_wt == 1:
                        new_sub.extend(m_val[s_start:sub_pos+8])
                        sub_pos += 8
                    elif s_wt == 5:
                        new_sub.extend(m_val[s_start:sub_pos+4])
                        sub_pos += 4
                new_m.extend(encode_varint(m_tag) + encode_varint(len(new_sub)) + new_sub)
            elif m_fn == 7: # uri string
                has_7 = True
                new_m.extend(encode_varint(m_tag) + encode_varint(len(nb)) + nb)
            elif m_fn == 18: # project_id
                has_18 = True
                new_m.extend(encode_varint(m_tag) + encode_varint(len(pb)) + pb)
            else:
                new_m.extend(val[m_start:m_pos])
        elif m_wt == 0:
            _, m_pos = decode_varint(val, m_pos)
            new_m.extend(val[m_start:m_pos])
        elif m_wt == 1:
            new_m.extend(val[m_start:m_pos+8])
            m_pos += 8
        elif m_wt == 5:
            new_m.extend(val[m_start:m_pos+4])
            m_pos += 4

    # Insert subfields if they were not in the original blob
    if not has_7 and new_uri_str:
        t7 = encode_varint((7 << 3) | 2)
        new_m.extend(t7 + encode_varint(len(nb)) + nb)
        
    if not has_1 and new_uri_str:
        # Create workspace item with subfield 1 = uri
        ws_sub = encode_varint((1 << 3) | 2) + encode_varint(len(nb)) + nb
        t1 = encode_varint((1 << 3) | 2)
        new_m.extend(t1 + encode_varint(len(ws_sub)) + ws_sub)
        
    if not has_18 and project_id_str:
        t18 = encode_varint((18 << 3) | 2)
        new_m.extend(t18 + encode_varint(len(pb)) + pb)
        
    return bytes(new_m)

def update_raw_summary(raw_data: bytes, new_uri_str: str, project_id_str: str) -> bytes:
    """
    Updates CascadeTrajectorySummary protobuf bytes:
    - field 9: workspace item (subfield 1 = uri)
    - field 17: TrajectoryMetadata (updated via update_trajectory_metadata_bytes)
    """
    pos = 0
    new_raw = bytearray()
    nb = new_uri_str.encode('utf-8') if new_uri_str else b""
    
    while pos < len(raw_data):
        start = pos
        tag, pos = decode_varint(raw_data, pos)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            val, pos = decode_varint(raw_data, pos)
            new_raw.extend(raw_data[start:pos])
        elif wt == 2:
            sz, pos = decode_varint(raw_data, pos)
            val = raw_data[pos:pos+sz]
            pos += sz
            if fn == 9: # Workspace item
                w_pos = 0
                new_w = bytearray()
                while w_pos < len(val):
                    w_start = w_pos
                    w_tag, w_pos = decode_varint(val, w_pos)
                    w_fn = w_tag >> 3
                    w_wt = w_tag & 7
                    if w_wt == 2:
                        w_sz, w_pos = decode_varint(val, w_pos)
                        w_val = val[w_pos:w_pos+w_sz]
                        w_pos += w_sz
                        if w_fn == 1:
                            new_w.extend(encode_varint(w_tag) + encode_varint(len(nb)) + nb)
                        else:
                            new_w.extend(val[w_start:w_pos])
                    elif w_wt == 0:
                        _, w_pos = decode_varint(val, w_pos)
                        new_w.extend(val[w_start:w_pos])
                    elif w_wt == 1:
                        new_w.extend(val[w_start:w_pos+8])
                        w_pos += 8
                    elif w_wt == 5:
                        new_w.extend(val[w_start:w_pos+4])
                        w_pos += 4
                new_raw.extend(encode_varint(tag) + encode_varint(len(new_w)) + new_w)
            elif fn == 17: # TrajectoryMetadata
                new_m = update_trajectory_metadata_bytes(val, new_uri_str, project_id_str)
                new_raw.extend(encode_varint(tag) + encode_varint(len(new_m)) + new_m)
            else:
                new_raw.extend(raw_data[start:pos])
        elif wt == 1:
            new_raw.extend(raw_data[start:pos+8])
            pos += 8
        elif wt == 5:
            new_raw.extend(raw_data[start:pos+4])
            pos += 4
    return bytes(new_raw)

def extract_summary_metadata(raw_data: bytes) -> Dict[str, Any]:
    """Extracts title, step_count, project_id, and workspace uri from raw_summary bytes."""
    meta = {"title": "", "step_count": 0, "project_id": "", "workspace_uri": ""}
    pos = 0
    while pos < len(raw_data):
        tag, pos = decode_varint(raw_data, pos)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            val, pos = decode_varint(raw_data, pos)
            if fn == 2:
                meta["step_count"] = val
        elif wt == 2:
            sz, pos = decode_varint(raw_data, pos)
            val = raw_data[pos:pos+sz]
            pos += sz
            if fn == 1:
                try:
                    meta["title"] = val.decode("utf-8")
                except Exception:
                    pass
            elif fn == 9:
                # workspace item
                w_pos = 0
                while w_pos < len(val):
                    w_tag, w_pos = decode_varint(val, w_pos)
                    w_fn = w_tag >> 3
                    w_wt = w_tag & 7
                    if w_wt == 2:
                        w_sz, w_pos = decode_varint(val, w_pos)
                        w_val = val[w_pos:w_pos+w_sz]
                        w_pos += w_sz
                        if w_fn == 1:
                            try:
                                meta["workspace_uri"] = w_val.decode("utf-8")
                            except Exception:
                                pass
                    elif w_wt == 0:
                        _, w_pos = decode_varint(val, w_pos)
                    elif w_wt == 1:
                        w_pos += 8
                    elif w_wt == 5:
                        w_pos += 4
            elif fn == 17:
                # TrajectoryMetadata
                m_pos = 0
                while m_pos < len(val):
                    m_tag, m_pos = decode_varint(val, m_pos)
                    m_fn = m_tag >> 3
                    m_wt = m_tag & 7
                    if m_wt == 2:
                        m_sz, m_pos = decode_varint(val, m_pos)
                        m_val = val[m_pos:m_pos+m_sz]
                        m_pos += m_sz
                        if m_fn == 18:
                            try:
                                meta["project_id"] = m_val.decode("utf-8")
                            except Exception:
                                pass
                        elif m_fn == 7 and not meta["workspace_uri"]:
                            try:
                                meta["workspace_uri"] = m_val.decode("utf-8")
                            except Exception:
                                pass
                    elif m_wt == 0:
                        _, m_pos = decode_varint(val, m_pos)
                    elif m_wt == 1:
                        m_pos += 8
                    elif m_wt == 5:
                        m_pos += 4
        elif wt == 1:
            pos += 8
        elif wt == 5:
            pos += 4
    return meta

def update_agyhub_pb(pb_bytes: bytes, cid: str, summary_bytes: bytes) -> bytes:
    """
    Updates or inserts (CID, summary_bytes) in agyhub_summaries_proto.pb wire bytes.
    """
    pos = 0
    length = len(pb_bytes)
    items: List[Tuple[str, bytes]] = []
    while pos < length:
        tag, pos = decode_varint(pb_bytes, pos)
        sz, pos = decode_varint(pb_bytes, pos)
        item_bytes = pb_bytes[pos:pos+sz]
        pos += sz
        
        ipos = 0
        item_cid = None
        item_sbytes = None
        while ipos < len(item_bytes):
            itag, ipos = decode_varint(item_bytes, ipos)
            ifn = itag >> 3
            iwt = itag & 0x07
            if iwt == 2:
                isz, ipos = decode_varint(item_bytes, ipos)
                ival = item_bytes[ipos:ipos+isz]
                ipos += isz
                if ifn == 1:
                    item_cid = ival.decode('utf-8', errors='ignore')
                elif ifn == 2:
                    item_sbytes = ival
            elif iwt == 0:
                _, ipos = decode_varint(item_bytes, ipos)
            elif iwt == 1:
                ipos += 8
            elif iwt == 5:
                ipos += 4
        if item_cid and item_sbytes:
            items.append((item_cid, item_sbytes))

    tag_item = encode_varint((1 << 3) | 2)
    tag_cid = encode_varint((1 << 3) | 2)
    tag_summary = encode_varint((2 << 3) | 2)

    found = False
    rebuilt = bytearray()
    for icid, sbytes in items:
        if icid == cid:
            sbytes = summary_bytes
            found = True
        cid_bytes = icid.encode('utf-8')
        inner = bytearray()
        inner.extend(tag_cid + encode_varint(len(cid_bytes)) + cid_bytes)
        inner.extend(tag_summary + encode_varint(len(sbytes)) + sbytes)
        rebuilt.extend(tag_item + encode_varint(len(inner)) + inner)

    if not found:
        cid_bytes = cid.encode('utf-8')
        inner = bytearray()
        inner.extend(tag_cid + encode_varint(len(cid_bytes)) + cid_bytes)
        inner.extend(tag_summary + encode_varint(len(summary_bytes)) + summary_bytes)
        rebuilt.extend(tag_item + encode_varint(len(inner)) + inner)

    return bytes(rebuilt)
