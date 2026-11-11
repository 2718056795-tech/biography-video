#!/usr/bin/env python3
"""Verify the shipped series renderer, profile and font lock; no media or history certification."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def inspect(root=ROOT):
    manifest_path=root/'assets/series/series_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    errors=[]
    for relative,expected in manifest['locked_files'].items():
        path=root/relative
        if not path.is_file():
            errors.append({'file':relative,'error':'missing'})
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            errors.append({'file':relative,'error':'changed from released series master'})
    return {'technical_status':'passed' if not errors else 'failed','profile_id':manifest['profile_id'],
            'checked_files':len(manifest['locked_files']),'errors':errors,
            'scope':'Released layout code, coordinates and font bytes only. Per-project colors, backgrounds, source research and animation art are intentionally variable.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=inspect()
    if args.report:
        protected=json.loads((ROOT/'assets/series/series_manifest.json').read_text())['locked_files']
        destinations=[ROOT/name for name in protected]+[ROOT/'assets/series/series_manifest.json']
        if any(args.report.resolve()==p.resolve() or (args.report.exists() and p.exists() and args.report.samefile(p)) for p in destinations):
            parser.error('报告不得覆盖固定母版或字库')
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if not result['errors'] else 1)


if __name__=='__main__':main()
