#!/usr/bin/env python3
import argparse, configparser
from pathlib import Path
import ipaddress

def is_multicast_ip(ip):
    network = ipaddress.ip_network('224.0.0.0/4')
    return ipaddress.ip_address(ip) in network

def parse_props(props_s: str) -> dict:
    """Parse 'k=v;k2=v2' into dict with simple type inference."""
    if not props_s:
        return {}
    out = {}
    for kv in props_s.split(";"):
        kv = kv.strip()
        if not kv:
            continue
        k, _, v = kv.partition("=")
        v = v.strip()
        if v.lower() in ("true", "false"):
            out[k.strip()] = (v.lower() == "true")
        else:
            try:
                out[k.strip()] = int(v) if v.isdigit() else float(v)
            except ValueError:
                out[k.strip()] = v
    return out

def gst_props_str(d: dict) -> str:
    """Render dict to 'k=v k2="str"' suitable for GStreamer props."""
    parts = []
    for k, v in d.items():
        if isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}={v}")
        else:
            # Quote strings; escape quotes if present
            s = str(v).replace('"', r'\"')
            parts.append(f'{k}="{s}"')
    return " ".join(parts)

def render_block(template: str, ctx: dict) -> str:
    """Simple {var} formatting using ctx dict."""
    return template.format(**ctx).strip()

def build_source_fragment(section: configparser.SectionProxy, idx: int, ctx: dict) -> str:
    kind = section.get("kind", fallback="v4l2src").strip()
    name = section.name.split(":",1)[1]  # e.g., source:cam0 -> cam0

    chain = []
    if kind == "v4l2src":
        device = section.get("device", fallback="/dev/video0")
        chain.append(f'v4l2src device={device} name={name}')
    elif kind == "testsrc":
        pattern = section.getint("pattern", fallback=0)
        chain.append(f'videotestsrc pattern={pattern} is-live=true name={name}')
    elif kind == "filesrc":
        location = section.get("device")  # reuse "device" for path
        chain.append(f'filesrc location="{location}" name={name} ! decodebin')
    elif kind == "appsrc":
        chain.append(f'appsrc name={name} is-live=true format=time')
    else:
        raise ValueError(f"Unknown source kind: {kind}")

    caps = section.get("caps", fallback="").strip()
    extra = section.get("extra", fallback="").strip()
    if caps:
        chain.append(f'! {render_block(caps, ctx)}')
    if extra:
        chain.append(f'! {render_block(extra, ctx)}')

    # Standard per-source safety
    chain.append('! queue ! videoconvert ! queue')

    if ctx.get("has_mixer", False):
        chain.append(f'! mix.sink_{idx}')

    return " ".join(chain)

def maybe_crop_block(ctx: dict) -> str:
    # Build videocrop or return "" if no crop vars provided
    L = ctx.get("crop_left")
    T = ctx.get("crop_top")
    R = ctx.get("crop_right")
    B = ctx.get("crop_bottom")
    if any(v is not None for v in (L, T, R, B)):
        L = int(L or 0); T = int(T or 0); R = int(R or 0); B = int(B or 0)
        return f"videocrop left={L} top={T} right={R} bottom={B} ! queue"
    return ""

def build_pipeline_from_ini(ini_path: Path, profile: str) -> str:
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ini_path)

    # Globals/context
    g = cp["globals"] if cp.has_section("globals") else {}
    ctx = {
        "width": int(g.get("width", 3840)),
        "height": int(g.get("height", 2160)),
        "fps": int(g.get("fps", 30)),
    }
    # Optional crop knobs (integers or absent)
    for k in ("crop_left","crop_top","crop_right","crop_bottom"):
        if k in g:
            ctx[k] = int(g.get(k))

    # Derived values handy in templates
    ctx["half_width"] = ctx["width"] // 2
    ctx["half_height"] = ctx["height"] // 2
    ctx["maybe_crop"] = maybe_crop_block(ctx)

    # Pipeline profile
    psec = f"pipeline:{profile}"
    if not cp.has_section(psec):
        raise ValueError(f"Missing section [{psec}] in {ini_path}")
    P = cp[psec]

    # Collect blocks lists by name
    def list_from_csv(key):
        if key not in P or not P.get(key).strip():
            return []
        return [s.strip() for s in P.get(key).split(",") if s.strip()]

    source_names = list_from_csv("sources")
    pre_names    = list_from_csv("pre")
    post_names   = list_from_csv("post")
    mix_name     = P.get("mix", fallback="").strip() or None
    enc_name     = P.get("encode").strip()
    sink_name    = P.get("sink").strip()

    ctx["has_mixer"] = bool(mix_name) and len(source_names) >= 1

    fragments = []

    # 1) Sources
    for idx, sname in enumerate(source_names):
        ssec = f"source:{sname}"
        if not cp.has_section(ssec):
            raise ValueError(f"Missing section [{ssec}]")
        frag = build_source_fragment(cp[ssec], idx, ctx)
        # Append per-source pre blocks immediately after
        for bname in pre_names:
            bsec = f"block:{bname}"
            if not cp.has_section(bsec):
                raise ValueError(f"Missing section [{bsec}]")
            frag += " ! " + render_block(cp[bsec].get("template", ""), ctx)
        fragments.append(frag)

    # 2) Mixer (optional)
    if mix_name:
        msec = f"block:{mix_name}"
        if not cp.has_section(msec):
            raise ValueError(f"Missing section [{msec}]")
        fragments.append(render_block(cp[msec].get("template", ""), ctx))

    # 3) Post blocks
    for bname in post_names:
        bsec = f"block:{bname}"
        if not cp.has_section(bsec):
            raise ValueError(f"Missing section [{bsec}]")
        rendered = render_block(cp[bsec].get("template", ""), ctx)
        if rendered:
            fragments.append(rendered)

    # 4) Encode
    esec = f"encode:{enc_name}"
    if not cp.has_section(esec):
        raise ValueError(f"Missing section [{esec}]")
    enc_elem = cp[esec].get("element", fallback="v4l2h265enc").strip()
    enc_props = gst_props_str(parse_props(cp[esec].get("props", fallback="")))
    enc_str = f"{enc_elem} name=enc"
    if enc_props:
        enc_str += " " + enc_props
    fragments.append(enc_str)

    postparse = cp[esec].get("postparse", fallback="").strip()
    if postparse:
        fragments.append(render_block(postparse, ctx))
    pay = cp[esec].get("pay", fallback="").strip()
    if pay:
        fragments.append(render_block(pay, ctx))

    # 5) Sink
    ssec = f"sink:{sink_name}"
    if not cp.has_section(ssec):
        raise ValueError(f"Missing section [{ssec}]")
    addr = cp[ssec].get("addr", fallback="239.255.0.10").strip()
    port = cp[ssec].getint("port", fallback=5004)
    iface = cp[ssec].get("iface", fallback="0.0.0.0").strip()
    extra = cp[ssec].get("extra", fallback="").strip()
    sink_str = f'udpsink host={addr} port={port}'
    if is_multicast_ip(addr):
        sink_str += f" auto-multicast=true multicast-iface={iface} mttl=16"
    if extra:
        sink_str += " " + render_block(extra, ctx)
    fragments.append(sink_str)

    # Join fragments; normalize whitespace
    pipeline = " ! ".join(fragments)
    return " ".join(pipeline.split())

def create_pipeline(args):
    return build_pipeline_from_ini(Path(args.ini), args.profile)

def create_sdp_params(args):
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(args.ini)
    psec = f"pipeline:{args.profile}"
    if not cp.has_section(psec):
        raise ValueError(f"Missing section [{psec}] in {args.ini}")
    P = cp[psec]
    sink_name = P.get("sink").strip()
    if not sink_name:
        raise ValueError(f"No sink defined in profile {args.profile}")
    ssec = f"sink:{sink_name}"
    if not cp.has_section(ssec):
        raise ValueError(f"Missing section [{ssec}]")
    enc_name = P.get("encode").strip()
    if not enc_name:
        raise ValueError(f"No encode defined in profile {args.profile}")
    pay_str = cp[f"encode:{enc_name}"].get("pay", "").strip()
    if not pay_str:
        raise ValueError(f"No payloader defined in encode:{enc_name}")
    pt_value = pay_str.split('pt=')[1].strip()
    addr = cp[ssec].get("addr", fallback="239.255.0.10").strip()
    port = cp[ssec].getint("port", fallback=5004)
    pt = int(pt_value) if pt_value.isdigit() else 96
    codec = "H265" if "h265" in pay_str.lower() else "H264"
    return {"addr": addr, "port": port, "pt": pt, "codec": codec}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build GStreamer pipeline from INI profiles.")
    ap.add_argument("--ini", help="Path to pipelines.ini", default="config/pipelines.ini")
    ap.add_argument("--profile", help="Profile name (e.g., dev, prod)", default="prod")
    args = ap.parse_args()
    print(create_pipeline(args))
