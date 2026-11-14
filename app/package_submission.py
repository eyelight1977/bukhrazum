"""Build a source-only delivery from an accepted source fingerprint."""
from pathlib import Path
import argparse, hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[1]

ROOT_FILES=['README.md','Dockerfile','.dockerignore','.gitignore','requirements.txt','package.json','package-lock.json','run_local.sh','THIRD_PARTY_NOTICES.md']
RELEASE_DOCS=['architecture.md','use_cases.md','acceptance.md','арифметика_и_источники.md','review.md']

def code_files():
    paths=[ROOT/p for p in ['Dockerfile','requirements.txt','package.json','package-lock.json','run_local.sh']]
    paths += [p for p in (ROOT/'app').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    return sorted(paths)
def fingerprint():
    digest=hashlib.sha256()
    for p in code_files():digest.update(str(p.relative_to(ROOT)).encode());digest.update(p.read_bytes())
    return digest.hexdigest()
def release_files():
    paths=[ROOT/p for p in ROOT_FILES]+[ROOT/'docs'/p for p in RELEASE_DOCS]
    paths += [p for p in (ROOT/'app').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    paths += [p for p in (ROOT/'tests').glob('test_*.py')]
    paths += [ROOT/'tests/synthetic_examples.py']
    paths += [p for p in (ROOT/'examples').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return sorted(set(paths))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    paths=release_files()
    assert all(p.is_file() and not p.is_symlink() for p in paths)
    assert not any(any(part in {'work','results','данные','подготовка','node_modules','.env'} for part in p.relative_to(ROOT).parts) for p in paths)
    if args.check:
        print(json.dumps({'files':len(paths),'code_fingerprint':fingerprint(),'excluded':['user documents','working copies','results','answer workbook','internal journal','private preparation']},indent=2));return
    report_path=ROOT/'results/docker_acceptance.json'
    if not report_path.exists():raise SystemExit('Комплект не собран: обязательная Docker-приёмка ещё не выполнена')
    report=json.loads(report_path.read_text())
    if not report.get('passed') or report.get('code_fingerprint')!=fingerprint():raise SystemExit('Комплект не собран: нет приёмки текущей версии кода')
    directory=ROOT/'submission';directory.mkdir(exist_ok=True)
    target=directory/('bukhrazum-prototype-'+fingerprint()[:12]+'.zip')
    public_acceptance={k:report[k] for k in ['passed','code_fingerprint','clean_build','restart_persistence','source_data_not_in_image','architecture','synthetic_examples'] if k in report}
    manifest={'code_fingerprint':fingerprint(),'docker_acceptance':public_acceptance,'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    if target.exists():raise SystemExit('Архив с этим отпечатком уже существует; прежний архив не перезаписан')
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in paths:z.write(p,str(p.relative_to(ROOT)))
        z.writestr('SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for name,digest in manifest['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
        assert len(z.namelist())==len(paths)+1
    (directory/'delivery_manifest.json').write_text(json.dumps({'archive':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),**manifest},ensure_ascii=False,indent=2))
    print(json.dumps({'archive':str(target),'files':len(paths),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
