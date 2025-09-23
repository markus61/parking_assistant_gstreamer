import argparse
from library.pipeline import create_pipeline, create_sdp_params

def configure(flavor: str) -> str:
    if not flavor:
        flavor = "pipeline"
    if not flavor in ("pipeline", "sdp_params"):
        raise ValueError("Invalid parameter to configure(): " + flavor)

    ap = argparse.ArgumentParser(description="Build GStreamer pipeline from INI profiles.")
    ap.add_argument("--ini", help="Path to pipelines.ini", default="config/pipelines.ini")
    ap.add_argument("--profile", help="Profile name (e.g., dev, prod)", default="prod")
    args = ap.parse_args()
    if flavor == "pipeline":
        return create_pipeline(args)
    elif flavor == "sdp_params":
        return create_sdp_params(args)
