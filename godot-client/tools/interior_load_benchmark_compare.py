"""Compare three predeclared fresh-process pairs and separate readback witnesses."""
import argparse
import json
from pathlib import Path

from interior_load_benchmark import compare_cohort, read, write


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,nargs=3,required=True)
    parser.add_argument("--native",type=Path,nargs=3,required=True)
    parser.add_argument("--raw-witness",type=Path,required=True)
    parser.add_argument("--native-witness",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    paths = [p.resolve() for p in args.raw+args.native+[args.raw_witness,args.native_witness]]
    if len(set(paths)) != 8:
        raise ValueError("eight distinct timed/witness output files required")
    result = compare_cohort([read(p) for p in args.raw],[read(p) for p in args.native],read(args.raw_witness),read(args.native_witness))
    result["inputs"] = [str(p) for p in paths]
    result["acceptance"] = {"load":"raw median >=100ms: >=20% reduction; below100ms: <=10ms regression",
                            "first_ready":"raw median >=100ms: >=10% reduction; below100ms: <=10ms regression",
                            "memory":"maximum Windows high-water RSS across candidate processes <=110% control",
                            "settle":"median through30-frame settle <=control+250ms; no queued-work benefit hidden after first-ready",
                            "content":"exact effective scene/material/full-mip/collision, deterministic-time pixels, authored ground/section parity",
                            "disk":"new33 target union <=64MiB, audited separately; excludes unchanged155 assets/old policies/scratch"}
    write(args.output,result)
    print(json.dumps(result,indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
