"""Export an offline fixed-mesh/skin candidate from a sampled creature GLB."""
from pathlib import Path
import argparse
import json
from video_motion.asset import digest
from video_motion.creature_bake_fit import bake


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--iterations', type=int, default=6)
    parser.add_argument('--allow-step-exceptions', action='store_true')
    parser.add_argument('--original-skin', action='store_true')
    args = parser.parse_args()
    if args.expected_sha256 and digest(args.source) != args.expected_sha256:
        raise ValueError('Selected sampled source changed')
    result = bake(args.source, args.output, iterations=args.iterations, report=args.report,
                  fit_skin=not args.original_skin, allow_step_exceptions=args.allow_step_exceptions)
    print(json.dumps({k: result[k] for k in ('status', 'sha256', 'raw_bytes', 'source_sha256')}))
